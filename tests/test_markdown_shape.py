"""The markdown artifact: pasted into an issue, read as a document.

Two things matter here that the terminal does not have to care about: the table
must not be split by the report's own text, and the summary must not carry the
80-character grouping key where a human sentence belongs.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from mcd.parser.report import parse_file, parse_text
from mcd.report.render import build_incident, render_markdown
from mcd.rules.engine import RuleSet, run_rules
from mcd.triage.attribution import triage

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"
WATCHDOG = GT / "crash-2026-09-08_22.42.32-server.txt"


def _md(path: Path = WATCHDOG) -> str:
    rep = parse_file(str(path))
    findings = run_rules(rep, RuleSet.load())
    buf = io.StringIO()
    render_markdown(rep, findings, triage(rep), buf)
    return buf.getvalue()


def _cells(row: str) -> int:
    body = row.strip()
    assert body.startswith("|") and body.endswith("|"), row
    return body.count("|") - body.count("\\|") - 1


def test_root_cause_row_holds_the_whole_first_line() -> None:
    rows = [ln for ln in _md().splitlines() if ln.startswith("| Root cause")]
    assert rows, "root cause row missing"
    assert "(should be max 0.05)" in rows[0]
    assert _cells(rows[0]) == 2


def test_source_is_a_basename_not_a_local_path() -> None:
    first = _md().splitlines()[2]
    assert "crash-2026-09-08_22.42.32-server.txt" in first
    assert "tests" not in first and "\\" not in first


def test_fixes_are_numbered_in_the_source() -> None:
    md = _md()
    assert "1. Look at the top stack frames" in md
    assert "2. If it happens during chunk saving" in md


def test_a_backtick_in_the_message_does_not_break_the_cell() -> None:
    text = (
        "---- Minecraft Crash Report ----\n"
        "Description: Ticking entity\n\n"
        "java.lang.RuntimeException: use @BT@value@BT@ here\n"
        "\tat a.b.C.d(C.java:1)\n\tat a.b.C.e(C.java:2)\n\n"
        "-- System Details --\nDetails:\n\tMinecraft Version: 1.21.1\n"
    ).replace("@BT@", chr(96))
    rep = parse_text(text)
    buf = io.StringIO()
    render_markdown(rep, [], None, buf)
    rows = [ln for ln in buf.getvalue().splitlines() if ln.startswith("| Root cause")]
    assert rows and chr(96) * 2 in rows[0]
    assert _cells(rows[0]) == 2


def test_the_summary_carries_the_readable_headline() -> None:
    rep = parse_file(str(WATCHDOG))
    doc = build_incident(rep, [], None)
    assert "(should be max 0.05)" in doc["summary"]["root_cause"]
    json.dumps(doc)                       # must stay serialisable
