"""Command-line interface: diagnose Minecraft crash reports and logs.

    mc-crash-doctor <file>              # pretty terminal report
    mc-crash-doctor --json <file>       # machine-readable
    mc-crash-doctor --markdown <file>   # for pasting into an issue/PR
    mc-crash-doctor --stdin             # pipe a log in
    mc-crash-doctor --dir <path>        # batch every report in a directory
    mc-crash-doctor --rules             # list the rule set
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from .model import CrashReport, Finding, Severity
from .parser.report import parse_file, parse_text
from .report.render import (render_json, render_markdown, render_plain,
                            render_terminal)
from .rules.engine import RuleSet, run_rules
from .triage.attribution import suspects_for_rules, triage

VERSION = "0.1.0"

REPORT_GLOBS = ("crash-*.txt", "*.log", "*.txt")


def _find_reports(d: Path) -> list[Path]:
    out: list[Path] = []
    sub = [d / "crash-reports", d / "logs", d]
    for base in sub:
        if not base.is_dir():
            continue
        for g in REPORT_GLOBS:
            out.extend(sorted(base.glob(g)))
        if out:
            break  # crash-reports/ wins over a bare directory listing
    return out


def diagnose(path: str | None, text: str | None, *, source: str = "") \
        -> tuple[CrashReport, list[Finding], object]:
    """Parse + run rules + triage. The one call the CLI and API share."""
    rep = parse_text(text, source_path=source) if text is not None \
        else parse_file(path)
    ruleset = RuleSet.load()
    findings = run_rules(rep, ruleset, suspect_fn=suspects_for_rules)
    t = triage(rep)
    return rep, findings, t


def _emit(rep: CrashReport, findings: list[Finding], t, fmt: str,
          out, color: bool) -> None:
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

    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="JSON output")
    fmt.add_argument("--markdown", "--md", action="store_true",
                     help="Markdown output (paste into an issue)")
    fmt.add_argument("--text", action="store_true", help="plain text, no colour")

    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--rules", action="store_true", help="list the loaded rules")
    ap.add_argument("--rules-dir", action="append", default=[],
                    help="extra directory of YAML rules")
    ap.add_argument("--exit-code", action="store_true",
                    help="exit 1 if any FATAL/ERROR finding (for CI)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args(argv)

    if args.rules:
        rs = RuleSet.load(args.rules_dir)
        print(f"{len(rs.rules)} rules loaded:")
        for r in rs.rules:
            print(f"  {r.priority:>3}  {r.id:<26} {r.severity.name:<8} {r.title}")
        return 0

    out = sys.stdout
    color = not (args.no_color or args.json or args.markdown or args.text
                 or not out.isatty())

    # --- resolve input ---
    if args.stdin:
        text = sys.stdin.read()
        rep, findings, t = diagnose(None, text, source="<stdin>")
        _emit(rep, findings, t, _fmt(args), out, color)
        return _exit(findings, args.exit_code)

    if args.url:
        text = _fetch_url(args.url)
        if text is None:
            print(f"error: could not fetch {args.url}", file=sys.stderr)
            return 2
        rep, findings, t = diagnose(None, text, source=args.url)
        _emit(rep, findings, t, _fmt(args), out, color)
        return _exit(findings, args.exit_code)

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

    worst = Severity.INFO
    for i, f in enumerate(files):
        if len(files) > 1 and not args.json:
            print(f"\n{'─' * 74}\n {f.name}\n{'─' * 74}")
        try:
            rep, findings, t = diagnose(str(f), None)
        except Exception as e:  # noqa: BLE001
            print(f"error parsing {f}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        _emit(rep, findings, t, _fmt(args), out, color)
        for fd in findings:
            if fd.severity > worst:
                worst = fd.severity

    if args.exit_code and worst >= Severity.ERROR:
        return 1
    return 0


def _fmt(args) -> str:
    if args.json:
        return "json"
    if args.markdown:
        return "markdown"
    if args.text:
        return "text"
    return "terminal"


def _exit(findings: list[Finding], exit_code: bool) -> int:
    if exit_code and any(f.severity >= Severity.ERROR for f in findings):
        return 1
    return 0


def _fetch_url(url: str) -> str | None:
    """Fetch a log; understands mclo.gs share links and plain raw URLs."""
    import re
    import urllib.request

    m = re.search(r"mclo\.gs/(\w+)/([A-Za-z0-9]+)", url)
    if m:
        url = f"https://api.mclo.gs/1/raw/{m.group(2)}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"mc-crash-doctor/{VERSION}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read(8_000_000).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    sys.exit(main())
