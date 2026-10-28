"""Command-line interface: diagnose Minecraft crash reports and logs.

    mc-crash-doctor <file>              # pretty terminal report
    mc-crash-doctor --json <file>       # machine-readable
    mc-crash-doctor --markdown <file>   # for pasting into an issue/PR
    mc-crash-doctor --stdin             # pipe a log in
    mc-crash-doctor --dir <path>        # batch every report in a directory
    mc-crash-doctor --pack <dir>        # check a mods/ dir without a crash
    mc-crash-doctor --rules             # list the rule set

``--json`` on a single input writes one object; on a batch (more than one
file) it writes a JSON array, so the output stays ``json.load()``-able.
``--rules-dir`` is honoured by diagnosis, not just by ``--rules``.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path
from typing import IO

from . import __version__
from .extract import fetch_log
from .model import CrashReport, Finding, Severity
from .parser.report import parse_file, parse_text
from .report.render import (render_explain, render_json, render_markdown,
                           render_plain, render_terminal)
from .rules.engine import RuleSet, run_rules
from .triage.attribution import suspects_for_rules, triage

VERSION = __version__

REPORT_GLOBS = ("crash-*.txt", "*.log", "*.txt")


def _find_reports(d: Path) -> list[Path]:
    """Every report under `d`, each file once.

    REPORT_GLOBS overlaps on purpose: ``crash-*.txt`` is the conventional name,
    ``*.txt`` catches everything else. A file that matches both (i.e. most real
    crash reports) must still be counted once -- otherwise a batch run reports
    twice the findings it has and ``--exit-code`` is twice as likely to trip.
    """
    out: list[Path] = []
    sub = [d / "crash-reports", d / "logs", d]
    for base in sub:
        if not base.is_dir():
            continue
        seen: dict[Path, None] = {}
        for g in REPORT_GLOBS:
            for p in sorted(base.glob(g)):
                seen.setdefault(p, None)
        out = list(seen)
        if out:
            break  # crash-reports/ wins over a bare directory listing
    return out


def diagnose(path: str | None, text: str | None, *, source: str = "",
             rules_dirs: list[str] | None = None,
             ruleset: RuleSet | None = None,
             trace: dict | None = None) \
        -> tuple[CrashReport, list[Finding], object]:
    """Parse + run rules + triage. The one call the CLI and API share.

    ``rules_dirs`` are extra YAML rule directories (CLI ``--rules-dir``). They
    must reach :meth:`RuleSet.load`; dropping them here made the flag silently
    do nothing outside ``--rules``.

    ``ruleset`` lets a batch reuse one already-loaded set instead of asking the
    caller to reload per file. A ``RuntimeError`` from loading (PyYAML missing)
    is a property of the *environment*, not of the report being diagnosed, so a
    batch must surface it once rather than once per file.
    """
    rep = parse_text(text, source_path=source) if text is not None \
        else parse_file(path)
    rs = ruleset if ruleset is not None else RuleSet.load(rules_dirs or None)
    findings = run_rules(rep, rs, suspect_fn=suspects_for_rules)
    t = triage(rep, trace=trace)
    return rep, findings, t


def _emit(rep: CrashReport, findings: list[Finding], t: object, fmt: str,
          out: IO[str], color: bool) -> None:
    if fmt == "json":
        render_json(rep, findings, t, out)
    elif fmt == "markdown":
        render_markdown(rep, findings, t, out)
    elif fmt == "text":
        render_plain(rep, findings, t, out)
    else:
        render_terminal(rep, findings, t, out, color=color)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mc-crash-doctor",
        description="Diagnose Minecraft crash reports and logs: root cause, "
                    "suspect mod, and the fix.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("path", nargs="?", help="crash report / log file, or a server dir")
    ap.add_argument("--stdin", action="store_true", help="read the report from stdin")
    ap.add_argument("--url", help="fetch a mclo.gs paste (https://mclo.gs/xxxxx)")
    ap.add_argument("-d", "--dir", help="batch: diagnose every report under this dir")
    ap.add_argument("--pack", metavar="DIR",
                    help="Pack Doctor: check a mods/ directory against the "
                         "dependencies its jars declare (no crash report needed)")
    ap.add_argument("--side", choices=("client", "server"),
                    help="with --pack: which side this directory runs. Enables "
                         "the Fabric/Quilt `environment` check and side-scoped "
                         "dependency requirements; without it both stay listed "
                         "as not checked")

    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="JSON output")
    fmt.add_argument("--markdown", "--md", action="store_true",
                     help="Markdown output (paste into an issue)")
    fmt.add_argument("--text", action="store_true", help="plain text, no colour")

    ap.add_argument("--explain", action="store_true",
                    help="also print how the suspicion score was assembled "
                         "(weights per signal); not available with --json, "
                         "which already carries score/confidence/reasons")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--rules", action="store_true", help="list the loaded rules")
    ap.add_argument("--rules-dir", action="append", default=[],
                    help="extra directory of YAML rules")
    ap.add_argument("--exit-code", action="store_true",
                    help="exit 1 if any FATAL/ERROR finding (for CI)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args(argv)

    # An explicitly requested rule directory that does not exist is a typo, not
    # a preference: fail loudly instead of diagnosing with builtin rules only
    # while the user believes their own rules are in play.
    for d in args.rules_dir:
        if not Path(d).is_dir():
            ap.error(f"--rules-dir is not a directory: {d}")

    if args.rules:
        rs = RuleSet.load(args.rules_dir)
        print(f"{len(rs.rules)} rules loaded:")
        for r in rs.rules:
            print(f"  {r.priority:>3}  {r.id:<26} {r.severity.name:<8} {r.title}")
        return 0

    out = sys.stdout
    color = not (args.no_color or args.json or args.markdown or args.text
                 or not out.isatty())

    if args.explain and args.json:
        # The breakdown is prose; appending it after a JSON document would make
        # `json.load` fail on the tool's own output.
        print("error: --explain cannot be combined with --json "
              "(the JSON already has score, confidence and reasons)",
              file=sys.stderr)
        return 2

    # --- pack mode: a different question, so it returns before anything else
    if args.pack:
        return _pack(args.pack, _fmt(args), out, color, args.exit_code, args.side)
    if args.side:
        # Silently ignoring it would make `--side client` look applied when the
        # run was a crash diagnosis, which never reads it.
        print("error: --side only applies to --pack", file=sys.stderr)
        return 2

    # --- resolve input ---
    if args.stdin:
        text = sys.stdin.read()
        return _one(None, text, "<stdin>", args, out, color)

    if args.url:
        text = fetch_log(args.url)
        if text is None:
            print(f"error: could not fetch {args.url}", file=sys.stderr)
            return 2
        return _one(None, text, args.url, args, out, color)

    target = args.dir or args.path
    if not target:
        ap.error("need a file, --stdin, --url or --dir")
    p = Path(target)
    if not p.exists():
        print(f"error: no such file or directory: {target}", file=sys.stderr)
        return 2

    files = _find_reports(p) if p.is_dir() else [p]
    files = [f for f in files if f.is_file() and f.suffix.lower()
             in (".txt", ".log")]
    if not files:
        print(f"error: no crash reports or logs found under {target}",
              file=sys.stderr)
        return 2

    # --json on a batch must stay parseable by json.load(). Concatenated
    # top-level objects ("Extra data") are not, so emit an array instead.
    batch_json = len(files) > 1 and _fmt(args) == "json"
    rendered: list[str] = []

    # Load rules once for the whole batch. Per-file loading was 67% of a single
    # diagnosis, and a missing PyYAML used to print "error parsing <file>" once
    # per report -- blaming the reports for a broken environment.
    try:
        ruleset = RuleSet.load(args.rules_dir or None)
    except RuntimeError as e:                    # PyYAML missing
        print(f"error: {e}", file=sys.stderr)
        return 2

    worst = Severity.INFO
    failed = 0
    with_findings = 0
    started = time.time()
    for f in files:
        if len(files) > 1 and not args.json:
            print(f"\n{'─' * 74}\n {f.name}\n{'─' * 74}")
        trace = {} if args.explain else None
        try:
            rep, findings, t = diagnose(str(f), None, ruleset=ruleset,
                                        trace=trace)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"error parsing {f}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if findings:
            with_findings += 1
        if batch_json:
            buf = io.StringIO()
            render_json(rep, findings, t, buf)
            rendered.append(buf.getvalue())
        else:
            fmt = _fmt(args)
            _emit(rep, findings, t, fmt, out, color)
            if trace is not None:
                render_explain(t, trace, out, markdown=(fmt == "markdown"))
        worst = max(worst, _worst(findings))

    if batch_json:
        out.write("[" + ",".join(rendered) + "]\n")

    if len(files) > 1:
        # stderr, so --json/--markdown on stdout stay machine-readable.
        ok = len(files) - failed
        print(f"mc-crash-doctor: {ok}/{len(files)} diagnosed "
              f"({with_findings} with findings), {failed} failed, "
              f"{time.time() - started:.1f}s", file=sys.stderr)

    # Every file failing is not success. Partial failures keep the old exit
    # contract (findings decide it) and are reported on stderr instead.
    if failed and failed == len(files):
        return 2
    return _exit(worst, args.exit_code)


def _one(path: str | None, text: str, source: str,
         args: argparse.Namespace, out: IO[str], color: bool) -> int:
    """Single-input path: stdin and --url. Parse failures get a message, not a
    traceback -- the same contract the file loop already honours."""
    trace: dict = {} if args.explain else None
    try:
        rep, findings, t = diagnose(path, text, source=source,
                                    rules_dirs=args.rules_dir, trace=trace)
    except Exception as e:  # noqa: BLE001
        print(f"error parsing {source}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    fmt = _fmt(args)
    _emit(rep, findings, t, fmt, out, color)
    if trace is not None:
        render_explain(t, trace, out, markdown=(fmt == "markdown"))
    return _exit(_worst(findings), args.exit_code)


def _fmt(args: argparse.Namespace) -> str:
    if args.json:
        return "json"
    if args.markdown:
        return "markdown"
    if args.text:
        return "text"
    return "terminal"


def _pack(target: str, fmt: str, out: IO[str], color: bool,
          exit_code: bool, side: str | None = None) -> int:
    """Pack Doctor entry point; `--exit-code` maps to the worst finding."""
    from .pack.doctor import analyse
    from .pack.render import (render_pack_json, render_pack_markdown,
                              render_pack_plain)

    try:
        rep = analyse(target, side=side)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if fmt == "json":
        render_pack_json(rep, out)
    elif fmt == "markdown":
        render_pack_markdown(rep, out)
    else:
        render_pack_plain(rep, out, color=color)
    return _exit(rep.worst, exit_code)


def _worst(findings: list[Finding]) -> Severity:
    """The most severe finding, or INFO for an empty list."""
    return max((f.severity for f in findings), default=Severity.INFO)


def _exit(worst: Severity, enabled: bool) -> int:
    """Exit 1 when --exit-code is on and anything reached ERROR."""
    return 1 if enabled and worst >= Severity.ERROR else 0


if __name__ == "__main__":
    sys.exit(main())
