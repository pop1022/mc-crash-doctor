"""Batch mode: twelve diagnoses and one question -- which file do I fix first.

The old epilogue said "12/12 diagnosed (7 with findings)". True, and useless.
The summary groups by the worst rule per file, keeps a confident suspect only,
and counts the files that were never reports as failed.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from mcd.cli import main

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"
OOM = GT / "crash-2026-09-08_18.01.19-server.txt"
OOM2 = GT / "crash-2026-09-08_18.39.21-server.txt"
WATCHDOG = GT / "crash-2026-09-08_22.42.32-server.txt"


def folder(tmp_path: Path) -> Path:
    d = tmp_path / "reports"
    d.mkdir()
    shutil.copy(OOM, d / "a-oom.txt")
    shutil.copy(OOM2, d / "b-oom.txt")
    shutil.copy(WATCHDOG, d / "c-watchdog.txt")
    return d


def test_reports_are_grouped_by_rule(tmp_path: Path, capsys) -> None:
    assert main([str(folder(tmp_path))]) == 0
    err = capsys.readouterr().err
    assert "-- what to fix first (3 files" in err
    assert "oom.heap" in err and "a-oom.txt, b-oom.txt" in err
    assert "hang.watchdog" in err


def test_a_confident_suspect_is_named(tmp_path: Path, capsys) -> None:
    assert main([str(folder(tmp_path))]) == 0
    err = capsys.readouterr().err
    assert "suspect: lithium 97%" in err


def test_a_weak_suspect_is_not_named(tmp_path: Path, capsys) -> None:
    # The OOM reports carry a low-confidence suspect; putting it next to
    # "increase -Xmx" would point at the wrong fix.
    assert main([str(folder(tmp_path))]) == 0
    oom_line = next(l for l in capsys.readouterr().err.splitlines()
                    if l.strip().startswith("!! oom.heap"))
    assert "suspect" not in oom_line


def test_prose_and_empty_files_are_counted_as_failed(tmp_path: Path, capsys) -> None:
    d = folder(tmp_path)
    (d / "d-prose.txt").write_text("求帮忙看看\n", encoding="utf-8")
    (d / "e-empty.txt").write_text("", encoding="utf-8")
    # Some files succeeded, so the run is not a failure; the two bad ones are
    # reported in the summary and on stderr.
    assert main([str(d)]) == 0
    err = capsys.readouterr().err
    assert "2 file(s) failed" in err
    assert "no rule matched" not in err


def test_a_single_file_prints_no_summary(tmp_path: Path, capsys) -> None:
    d = tmp_path / "one"
    d.mkdir()
    shutil.copy(OOM, d / "only.txt")
    assert main([str(d), "--text"]) == 0
    assert "what to fix first" not in capsys.readouterr().err


def test_json_batch_keeps_stdout_parseable(tmp_path: Path, capsys) -> None:
    assert main([str(folder(tmp_path)), "--json"]) == 0
    out = capsys.readouterr()
    assert len(json.loads(out.out)) == 3
    assert "what to fix first" in out.err
