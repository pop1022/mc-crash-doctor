"""`--timeline`: the last N seconds of a log, without guessing.

The real 2026 NeoForge log this was built against uses
`[17Oct2026 00:39:27.039] [main/INFO] ...`; older Forge/Fabric use
`[12:34:56] [Server thread/INFO]: ...`. Both are pinned here, along with the
contract that lines without a timestamp are *counted*, not silently dropped.

    pytest tests/test_timeline.py -v
"""
from __future__ import annotations

import io

from mcd.cli import main
from mcd.timeline import extract_events, render_timeline, window

OLD = """[12:34:50] [Server thread/INFO]: Starting minecraft server
[12:34:55] [Server thread/WARN]: Can't keep up! Is the server overloaded?
[12:34:59] [Server thread/ERROR]: Exception ticking world
java.lang.NullPointerException: boom
	at a.b.C.go(C.java:1)
[12:35:00] [Server thread/INFO]: Stopping server
"""

NEW = """[17Oct2026 00:39:27.039] [main/INFO] [ModDiscoverer/SCAN]: Found mod file
[17Oct2026 00:39:28.100] [main/INFO]: Loading 355 mods
[17Oct2026 00:39:29.250] [main/FATAL]: Unreported exception thrown!
"""


def test_old_forge_shape():
    events, skipped = extract_events(OLD)
    assert len(events) == 4
    assert skipped == 2                       # stack trace continuation lines
    assert events[0].clock == "12:34:50"
    assert events[0].level == "INFO" and events[0].thread == "Server thread"
    assert events[2].message.startswith("Exception ticking world")


def test_current_neoforge_shape_with_date_prefix():
    events, skipped = extract_events(NEW)
    assert len(events) == 3 and skipped == 0
    assert events[0].clock == "00:39:27.039"
    assert events[2].level == "FATAL"


def test_window_keeps_only_the_last_n_seconds():
    events, _ = extract_events(OLD)
    chosen, start = window(events, 6)         # 12:35:00 - 6s = 12:34:54
    assert [e.message for e in chosen] == [
        "Can't keep up! Is the server overloaded?",
        "Exception ticking world", "Stopping server"]
    assert start == 12 * 3600 + 34 * 60 + 54


def test_no_timestamps_is_reported_not_hidden():
    events, skipped = extract_events("just prose\nmore prose")
    chosen, _ = window(events, 60)
    buf = io.StringIO()
    render_timeline(chosen, skipped, 60, buf)
    text = buf.getvalue()
    assert events == [] and skipped == 2
    assert "no timestamped lines" in text
    assert "2 non-empty lines" in text


def test_midnight_wrap_does_not_reverse_the_window():
    text = ("[23:59:58] [main/INFO]: before\n"
            "[00:00:01] [main/INFO]: after\n"
            "[00:00:02] [main/FATAL]: crash\n")
    events, _ = extract_events(text)
    chosen, _ = window(events, 60)
    assert [e.message for e in chosen] == ["before", "after", "crash"]


def test_cli_prints_the_timeline(tmp_path, capsys):
    p = tmp_path / "latest.log"
    p.write_text(OLD, encoding="utf-8")
    assert main([str(p), "--timeline", "6"]) == 0
    out = capsys.readouterr().out
    assert "Timeline — last 6s" in out
    assert "Exception ticking world" in out
    assert "Starting minecraft server" not in out, "window cut did not apply"
    assert "without a timestamp were skipped" in out


def test_cli_rejects_invalid_combinations(tmp_path, capsys):
    p = tmp_path / "latest.log"
    p.write_text(OLD, encoding="utf-8")
    assert main([str(p), "--timeline", "0"]) == 2
    assert main([str(p), "--timeline", "5", "--json"]) == 2
    assert main(["--timeline", "5", "--pack", str(tmp_path)]) == 2


def test_default_diagnosis_is_untouched_by_the_flag(tmp_path, capsys):
    p = tmp_path / "latest.log"
    p.write_text(OLD, encoding="utf-8")
    assert main([str(p), "--text"]) == 0
    assert "Timeline" not in capsys.readouterr().out
