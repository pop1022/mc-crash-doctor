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
import re
import sys
import time
from pathlib import Path
from typing import IO
from urllib.parse import quote

from . import __version__
from .extract import fetch_log
from .model import CrashReport, Finding, Severity
from .parser.report import parse_file, parse_text
from .report.render import (render_explain, render_json, render_markdown,
                           render_plain, render_terminal)
from .rules.engine import BUILTIN_DIR, RuleSet, run_rules
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


def diagnose(path: str | None, text: str | None = None, *, source: str = "",
             rules_dirs: list[str] | None = None,
             ruleset: RuleSet | None = None,
             trace: dict | None = None,
             lang: str = "en") \
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
    findings = run_rules(rep, rs, suspect_fn=suspects_for_rules, lang=lang)
    t = triage(rep, trace=trace)
    return rep, findings, t


def _emit(rep: CrashReport, findings: list[Finding], t: object, fmt: str,
          out: IO[str], color: bool, *, hint: bool = True) -> None:
    if fmt == "json":
        render_json(rep, findings, t, out)
    elif fmt == "markdown":
        render_markdown(rep, findings, t, out)
    elif fmt == "text":
        render_plain(rep, findings, t, out, hint=hint)
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

    ap.add_argument("--timeline", nargs="?", type=int, const=60, default=None,
                    metavar="SECONDS",
                    help="show the last SECONDS (default 60) of timestamped log "
                         "lines before the crash instead of diagnosing")
    ap.add_argument("--explain", action="store_true",
                    help="also print how the suspicion score was assembled "
                         "(weights per signal); not available with --json, "
                         "which already carries score/confidence/reasons")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--rules", action="store_true", help="list the loaded rules")
    ap.add_argument("--validate-rules", action="store_true",
                    help="check the rule packs (builtin + --rules-dir) and exit "
                         "non-zero on problems; needs no crash report")
    ap.add_argument("--no-fixtures", action="store_true",
                    help="with --validate-rules: skip the rules' expect: "
                         "assertions (for a pack whose fixtures are elsewhere)")
    ap.add_argument("--rules-dir", action="append", default=[],
                    help="extra directory of YAML rules")
    ap.add_argument("--server", metavar="DIR",
                    help="read-only risk scan of a server directory: log lag, "
                         "repeating crashes, heap, pack contradictions")
    ap.add_argument("--watch", action="store_true",
                    help="follow a live log and diagnose each crash as it lands")
    ap.add_argument("--window", type=int, default=2000, metavar="N",
                    help="with --watch: diagnose the last N lines (default 2000)")
    ap.add_argument("--lang", choices=("en", "zh"), default="en",
                    help="language of the diagnosis text (rule copy; ASCII ids stay put)")
    ap.add_argument("--feedback", action="store_true",
                    help="print a pre-filled issue link for a wrong or missing diagnosis")
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

    if args.validate_rules:
        return _validate_rules(args, sys.stdout)

    if args.server:
        from .server import inspect as server_inspect
        from .server import render as render_server
        try:
            srep = server_inspect(args.server)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        render_server(srep, sys.stdout)
        # A warning is advice; a broken pack or a repeating crash is a reason
        # for CI to stop. Mirrors pack mode, where only ERROR and above fail.
        return 1 if srep.worst.name in ("FATAL", "ERROR") else 0

    if args.watch:
        if args.json or args.markdown:
            print("error: --watch prints its diagnoses as text; drop --json/--markdown",
                  file=sys.stderr)
            return 2
        target = args.path or args.dir
        if not target:
            ap.error("--watch needs a log file")
        if not Path(target).exists():
            print(f"error: no such file: {target}", file=sys.stderr)
            return 2
        from .watch import watch
        print(f"watching {target} (window {args.window} lines, Ctrl-C to stop)",
              file=sys.stderr)
        try:
            return watch(target, window=args.window)
        except KeyboardInterrupt:
            return 130

    if args.timeline is not None:
        return _timeline_mode(args)

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
        if args.explain:
            # Silently ignoring it would look like the weights were printed
            # somewhere below; pack mode has no suspects to explain.
            print("error: --explain is for crash reports; --pack has no "
                  "attribution to explain", file=sys.stderr)
            return 2
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

    if p.is_dir():
        files = [f for f in _find_reports(p) if f.is_file()
                 and f.suffix.lower() in (".txt", ".log")]
    else:
        # An explicitly named file is not filtered by extension: a report can be
        # named anything, and "no crash reports or logs found under x.bin"
        # blamed the directory filter for a file the user pointed at.
        files = [p]
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
    rows: list[dict] = []
    started = time.time()
    for f in files:
        try:
            size = f.stat().st_size
        except OSError as e:
            failed += 1
            rows.append({"file": f.name, "failed": True})
            print(f"error reading {f}: {e}", file=sys.stderr)
            continue
        if size == 0:
            failed += 1
            rows.append({"file": f.name, "failed": True})
            print(f"error: {f.name} is empty -- nothing to diagnose",
                  file=sys.stderr)
            continue
        if size > MAX_INPUT_BYTES:
            failed += 1
            rows.append({"file": f.name, "failed": True})
            print(f"error: {f.name} is {size / 1e6:.1f} MB -- limit "
                  f"{MAX_INPUT_BYTES // 1e6:.0f} MB. Paste the crash report "
                  f"itself, not the whole log archive", file=sys.stderr)
            continue
        kind = _classify_file(f)
        if kind in _INPUT_GUIDANCE:
            failed += 1
            rows.append({"file": f.name, "failed": True})
            print(f"error: {f.name}: {_input_guidance(kind)}", file=sys.stderr)
            continue
        if len(files) > 1 and not args.json:
            print(f"\n{'─' * 74}\n {f.name}\n{'─' * 74}")
        trace = {} if args.explain else None
        try:
            rep, findings, t = diagnose(str(f), None, ruleset=ruleset,
                                        trace=trace, lang=args.lang)
        except Exception as e:  # noqa: BLE001
            failed += 1
            rows.append({"file": f.name, "failed": True})
            print(f"error parsing {f}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if findings:
            with_findings += 1
        weak = _is_weak(rep, findings)
        if weak:
            failed += 1
        rows.append({
            "file": f.name,
            "findings": findings,
            "suspect": (t.suspects[0] if getattr(t, "suspects", None) else None),
            "failed": weak,
        })
        if batch_json:
            buf = io.StringIO()
            render_json(rep, findings, t, buf)
            rendered.append(buf.getvalue())
        else:
            fmt = _fmt(args)
            _emit(rep, findings, t, fmt, out, color, hint=trace is None)
            _weak_input_note(rep, findings, out, fmt)
            if trace is not None:
                render_explain(t, trace, out, markdown=(fmt == "markdown"))
            if (getattr(args, "feedback", False) and len(files) == 1
                    and fmt != "json"):
                print("\n结论不对，或者这份报告没被覆盖？带上这条链接开 issue"
                      "（链接里只有摘要，没有你的日志）：", file=out)
                print(feedback_url(rep, findings), file=out)
        worst = max(worst, _worst(findings))

    if batch_json:
        out.write("[" + ",".join(rendered) + "]\n")

    if len(files) > 1:
        # stderr, so --json/--markdown on stdout stay machine-readable.
        ok = len(files) - failed
        print(f"mc-crash-doctor: {ok}/{len(files)} diagnosed "
              f"({with_findings} with findings), {failed} failed, "
              f"{time.time() - started:.1f}s", file=sys.stderr)
        _batch_summary(rows, sys.stderr, time.time() - started)

    # Every file failing is not success. Partial failures keep the old exit
    # contract (findings decide it) and are reported on stderr instead.
    if failed and failed == len(files):
        return 2
    return _exit(worst, args.exit_code)


def _timeline_mode(args) -> int:
    """`--timeline` is a separate question (what happened just before the
    crash?), so it returns on its own instead of mixing prose into a diagnosis
    or -- appending after a JSON document -- breaking json.load()."""
    from .timeline import (extract_events, render_timeline, trailing_lines,
                           window)

    if args.timeline < 1:
        print("error: --timeline needs a positive number of seconds",
              file=sys.stderr)
        return 2
    if args.json or args.pack or args.dir:
        print("error: --timeline takes one report (not --json / --pack / --dir)",
              file=sys.stderr)
        return 2

    if args.stdin:
        text, source = sys.stdin.read(), "<stdin>"
    elif args.url:
        text = fetch_log(args.url)
        if text is None:
            print(f"error: could not fetch {args.url}", file=sys.stderr)
            return 2
        source = args.url
    else:
        if not args.path:
            # `Path("")` is ".", which produced "no such report file: ." for a
            # flag that was simply missing its argument.
            print("error: --timeline needs a file, --stdin or --url",
                  file=sys.stderr)
            return 2
        p = Path(args.path)
        if not p.is_file():
            print(f"error: no such report file: {p}", file=sys.stderr)
            return 2
        try:
            if p.stat().st_size == 0:
                print(f"error: {p.name} is empty -- nothing to place on a "
                      f"timeline", file=sys.stderr)
                return 2
            if p.stat().st_size > MAX_INPUT_BYTES:
                print(f"error: {p.name} is {p.stat().st_size / 1e6:.1f} MB -- "
                      f"limit {MAX_INPUT_BYTES // 1e6:.0f} MB", file=sys.stderr)
                return 2
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"error: could not read {p}: {e}", file=sys.stderr)
            return 2
        source = str(p)

    events, skipped = extract_events(text)
    chosen, _ = window(events, args.timeline)
    render_timeline(chosen, skipped, args.timeline, sys.stdout, source=source,
                    trailing=trailing_lines(text))
    return 0


def _one(path: str | None, text: str, source: str,
         args: argparse.Namespace, out: IO[str], color: bool) -> int:
    """Single-input path: stdin and --url. Parse failures get a message, not a
    traceback -- the same contract the file loop already honours."""
    if not (text or "").strip():
        print(f"error: {source} is empty -- nothing to diagnose", file=sys.stderr)
        return 2
    from .input_kind import classify
    kind = classify(text)
    if kind in _INPUT_GUIDANCE:
        print(f"error: {source}: {_input_guidance(kind)}", file=sys.stderr)
        return 2
    trace: dict = {} if args.explain else None
    try:
        rep, findings, t = diagnose(path, text, source=source,
                                    rules_dirs=args.rules_dir, trace=trace,
                                    lang=getattr(args, "lang", "en"))
    except Exception as e:  # noqa: BLE001
        print(f"error parsing {source}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    fmt = _fmt(args)
    _emit(rep, findings, t, fmt, out, color, hint=trace is None)
    weak = _is_weak(rep, findings)
    _weak_input_note(rep, findings, out, fmt)
    if trace is not None:
        render_explain(t, trace, out, markdown=(fmt == "markdown"))
    if getattr(args, "feedback", False):
        print("\n结论不对，或者这份报告没被覆盖？带上这条链接开 issue"
              "（链接里只有摘要，没有你的日志）：", file=out)
        print(feedback_url(rep, findings), file=out)
    # A sentence is not a report: nothing was diagnosed *and* there was nothing
    # to diagnose. Exit 2 says so to a script.
    if weak:
        return 2
    return _exit(_worst(findings), args.exit_code)


#: A diagnosis can carry an absolute path, an IP or a player name. The
#: feedback link opens a public issue, so the few summary fields are scrubbed
#: here instead of trusting whatever the report contained. The log body is
#: never put in the URL at all -- the user attaches it themselves.
_SCRUB = (
    (re.compile(r"[A-Za-z]:\\\\[^\s\"']+"), "<path>"),
    (re.compile(r"/(?:home|Users|root)/[^\s\"']+"), "<path>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
)


def _scrub(value: str) -> str:
    for pat, repl in _SCRUB:
        value = pat.sub(repl, value)
    return value


def feedback_url(rep: CrashReport, findings: list[Finding]) -> str:
    """Pre-filled issue link: the summary, never the log body."""
    s = rep.system
    root = rep.root_cause.signature if rep.root_cause else (rep.description or "?")
    lines = [
        "### 引擎看到的东西",
        f"- mc-crash-doctor {VERSION}",
        f"- 平台：{(s.loader + ' ' + s.loader_version).strip() or '?'}",
        f"- 游戏：{s.minecraft_version or '?'} / Java {s.java_major or '?'}",
        f"- 模组数：{s.mod_count or len(rep.mods) or '?'}，堆上限：{s.xmx_mib or '?'} MiB",
        f"- 根因：{_scrub(root)}",
        "",
        "### 引擎给出的结论",
    ]
    for f in findings[:3]:
        lines.append(f"- {f.rule_id}（{int(f.confidence * 100)}%）：{_scrub(f.title)}")
    if not findings:
        lines.append("- 没有规则命中这份报告")
    lines += [
        "",
        "### 我不同意的地方",
        "（写清楚是哪一条：规则 id / 你认为是哪个模组 / 漏掉了什么故障）",
        "",
        "### 报告",
        "（把脱敏后的崩溃报告贴在这里。这个链接里只有摘要，没有你的日志。）",
    ]
    body = "\n".join(lines)
    head = _scrub(findings[0].title if findings else root)[:80]
    return ("https://github.com/pop1022/mc-crash-doctor/issues/new"
            "?template=wrong-diagnosis.md"
            f"&title={quote('[feedback] ' + head)}"
            f"&body={quote(body)}")


def _validate_rules(args: argparse.Namespace, out: IO[str]) -> int:
    """Check rule packs without a crash report. Exit 1 on any problem.

    Why this is a mode of its own: a rule pack is code someone else runs, and
    the failure that matters is a pack that *looks* loaded while half its rules
    were skipped. Diagnosis prints those warnings to stderr and carries on,
    which is right for a user in a hurry and wrong for CI. Here every warning is
    a failure, the counts say what loaded, and nothing is diagnosed.
    """
    rs = RuleSet.load(args.rules_dir or None, report=False)
    builtin = {r.id for r in rs.rules
               if Path(r.source).resolve().parent == BUILTIN_DIR.resolve()}
    external = [r for r in rs.rules if r.id not in builtin]
    print(f"rules: {len(rs.rules)} loaded ({len(builtin)} builtin, "
          f"{len(external)} external)", file=out)
    for d in args.rules_dir:
        n = sum(1 for r in external
                if Path(r.source).resolve().parent == Path(d).resolve())
        print(f"  {d}: {n} rule(s)", file=out)

    problems = list(rs.errors)
    if not args.no_fixtures:
        from .rules.expect import check
        fixture_problems, checked = check(rs)
        print(f"expect: {checked} assertion(s) checked", file=out)
        problems.extend(fixture_problems)

    if not problems:
        print("no problems found", file=out)
        return 0
    print(f"problems ({len(problems)}):", file=out)
    for e in problems:
        print(f"  {e}", file=out)
    return 1


#: Same ceiling as the web box. A crash report is tens of KB; a 30 MB file is
#: an archive or a rotated log, and parsing it costs seconds to say "no rule".
MAX_INPUT_BYTES = 8 * 1024 * 1024


def _looks_like_report(text: str) -> bool:
    """Heuristic, shared with the browser via mcd.input_kind.

    Used only to keep the tool from telling someone their prose "parsed cleanly
    and matched no rule" -- a true statement about a wrong question. It never
    blocks a diagnosis: a report in an unfamiliar format still gets one.
    """
    from .input_kind import looks_like_report
    return looks_like_report(text)


#: Two inputs get an answer instead of a diagnosis. Both are common, both used
#: to come out as "no rule matched this report" -- true, and useless.
_INPUT_GUIDANCE = {
    "hs_err": (
        "this is a JVM fatal-error log (hs_err_pid*.log), not a Minecraft crash report.\n"
        "  It records a native crash -- usually the graphics driver or a native\n"
        "  library -- which the Minecraft rules cannot diagnose.\n"
        "  Next: update the GPU driver. If it started after adding a mod that ships\n"
        "  native code (shaders, voice, controller), remove that mod first.\n"
        "  Share the \"Problematic frame\" line, not the whole file: it contains your\n"
        "  paths and user name."
    ),
    "exit_code": (
        "an exit code on its own cannot be diagnosed.\n"
        "  The code says the process died; the cause is in the log from the same run.\n"
        "  Next: paste logs/latest.log (server) or .minecraft/logs/latest.log (client).\n"
        "  No crash report in the folder usually means the game was killed or failed\n"
        "  to start -- latest.log still has the lines that say why."
    ),
}


def _input_guidance(kind: str) -> str:
    return _INPUT_GUIDANCE.get(kind, "")


def _classify_file(path) -> str:
    """Classify from the head of the file: both answers live in the first lines."""
    from .input_kind import classify

    try:
        with open(path, "rb") as fh:
            head = fh.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return "report"
    return classify(head)


def _is_weak(rep: CrashReport, findings: list) -> bool:
    """True when nothing matched *and* the input never looked like a report.

    Both halves matter: a real crash report with no matching rule is a gap in
    the rule set, not a user error, and must not be counted as failed.
    """
    return not findings and not _looks_like_report(rep.full_text or "")


def _weak_input_note(rep: CrashReport, findings: list, out: IO[str],
                     fmt: str) -> None:
    """Say the input is not a report when that is why nothing matched."""
    if fmt == "json" or not _is_weak(rep, findings):
        return
    if fmt == "markdown":
        out.write("_Nothing diagnosable: the input does not look like a crash "
                  "report or log._\n")
    else:
        out.write("\n  nothing diagnosable: this does not look like a crash "
                  "report or log\n")

#: One character per severity for the batch summary; the same shapes the pack
#: renderer uses, so two commands do not need two visual languages.
_SEV_MARK = {Severity.FATAL: "!!", Severity.ERROR: "x ", Severity.WARNING: "! ",
             Severity.HINT: "- ", Severity.INFO: "  "}


def _batch_summary(rows: list[dict], out: IO[str], elapsed: float) -> None:
    """What to fix first, after a multi-file run.

    A batch used to end with "12/12 diagnosed (7 with findings)": true, and no
    help at all with the actual question -- which of these twelve matters. The
    grouping below is by the worst rule per file, because a server administrator
    fixes one rule at a time, not one file at a time.
    """
    groups: dict[str, dict] = {}
    none = 0
    failed = 0
    for row in rows:
        if row["failed"]:
            failed += 1
            continue
        findings = row["findings"]
        if not findings:
            none += 1
            continue
        top = max(findings, key=lambda f: f.severity)
        g = groups.setdefault(top.rule_id, {
            "rule": top.rule_id, "sev": top.severity, "files": [],
            "suspect": None})
        g["files"].append(row["file"])
        g["sev"] = max(g["sev"], top.severity)
        # Only a confident suspect belongs in "what to fix first": an OOM group
        # with a 46% guess next to it points at the wrong fix.
        s = row.get("suspect")
        if g["suspect"] is None and s is not None and s.confidence >= 0.6:
            g["suspect"] = s

    out.write(f"\n-- what to fix first ({len(rows)} files, {elapsed:.1f}s) "
              f"----------\n")
    for g in sorted(groups.values(),
                    key=lambda g: (-g["sev"], -len(g["files"]), g["rule"])):
        shown = ", ".join(g["files"][:3])
        if len(g["files"]) > 3:
            shown += f" (+{len(g['files']) - 3})"
        suspect = ""
        if g["suspect"] is not None:
            suspect = (f"   suspect: {g['suspect'].modid} "
                       f"{g['suspect'].confidence:.0%}")
        out.write(f"{_SEV_MARK.get(g['sev'], '  ')} {g['rule']:<24} {shown}"
                  f"{suspect}\n")
    if none:
        out.write(f"   {' ' * 24} {none} file(s): no rule matched\n")
    if failed:
        out.write(f"   {' ' * 24} {failed} file(s) failed (see above)\n")


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
    if not rep.declared_mods:
        # Nothing was checked, so "no findings" must not look like success.
        return 2
    return _exit(rep.worst, exit_code)


def _worst(findings: list[Finding]) -> Severity:
    """The most severe finding, or INFO for an empty list."""
    return max((f.severity for f in findings), default=Severity.INFO)


def _exit(worst: Severity, enabled: bool) -> int:
    """Exit 1 when --exit-code is on and anything reached ERROR."""
    return 1 if enabled and worst >= Severity.ERROR else 0


if __name__ == "__main__":
    sys.exit(main())
