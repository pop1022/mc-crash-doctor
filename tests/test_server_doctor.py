"""Server Doctor: a read-only snapshot, and it must stay read-only.

The risks worth pinning are the ones that only exist across files: the same rule
in two reports, lag repeated in the log, a heap ceiling that is small for the mod
count. Anything a single report already says belongs to the diagnosis, not here.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from mcd.cli import main
from mcd.model import Severity
from mcd.server import LAG_THRESHOLD, inspect

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"
OOM = GT / "crash-2026-09-08_18.01.19-server.txt"          # -Xmx2048, 266 mods
WATCHDOG = GT / "crash-2026-09-08_22.31.14-server.txt"     # -Xmx8192


def server(tmp_path: Path, *, logs: str | None = None,
           reports: list[Path] | None = None) -> Path:
    root = tmp_path / "server"
    (root / "logs").mkdir(parents=True)
    if logs is not None:
        (root / "logs" / "latest.log").write_text(logs, encoding="utf-8")
    if reports:
        (root / "crash-reports").mkdir()
        for i, r in enumerate(reports):
            shutil.copy(r, root / "crash-reports" / f"crash-2026-09-0{i + 1}_10.00.00-server.txt")
    return root


def jar(path: Path, body: dict) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("fabric.mod.json", json.dumps(body))


# --- the batch facts --------------------------------------------------------
def test_a_missing_directory_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        inspect(tmp_path / "nope")


def test_no_files_is_not_a_clean_bill_of_health(tmp_path: Path) -> None:
    rep = inspect(server(tmp_path))
    assert [r.code for r in rep.risks] == ["server.no-crash-reports"]
    assert rep.risks[0].level is Severity.INFO
    assert any("latest.log" in n for n in rep.not_checked)


def test_lag_below_the_threshold_is_not_a_risk(tmp_path: Path) -> None:
    line = "[12:00:00] [Server thread/WARN]: Can't keep up! Is the server overloaded?\n"
    rep = inspect(server(tmp_path, logs=line * (LAG_THRESHOLD - 1)))
    assert rep.by_code("server.tick-lag") == []


def test_sustained_lag_is_a_risk(tmp_path: Path) -> None:
    line = "[12:00:00] [Server thread/WARN]: Can't keep up! Is the server overloaded?\n"
    rep = inspect(server(tmp_path, logs=line * LAG_THRESHOLD))
    risk = rep.by_code("server.tick-lag")[0]
    assert risk.level is Severity.WARNING
    assert str(LAG_THRESHOLD) in risk.subject


def test_the_same_rule_twice_is_a_repeating_crash(tmp_path: Path) -> None:
    rep = inspect(server(tmp_path, reports=[OOM, OOM]))
    risk = rep.by_code("server.repeat-crash")[0]
    assert risk.subject == "oom.heap"
    assert "2 of the 2" in risk.detail
    assert risk.level is Severity.ERROR


def test_a_one_off_crash_is_not_a_pattern(tmp_path: Path) -> None:
    rep = inspect(server(tmp_path, reports=[OOM, WATCHDOG]))
    assert rep.by_code("server.repeat-crash") == []
    assert rep.crash_reports == 2


def test_a_small_heap_for_the_mod_count_is_flagged(tmp_path: Path) -> None:
    rep = inspect(server(tmp_path, reports=[OOM]))
    risk = rep.by_code("server.heap-tight")[0]
    assert "2048" in risk.detail or risk.evidence
    assert any("2048" in e for e in risk.evidence)


def test_a_generous_heap_is_not_flagged(tmp_path: Path) -> None:
    rep = inspect(server(tmp_path, reports=[WATCHDOG]))
    assert rep.by_code("server.heap-tight") == []


def test_pack_errors_are_lifted_into_the_risk_list(tmp_path: Path) -> None:
    root = server(tmp_path)
    (root / "mods").mkdir()
    jar(root / "mods" / "create.jar", {"schemaVersion": 1, "id": "create",
                                       "version": "0.5.1",
                                       "depends": {"flywheel": "*"}})
    rep = inspect(root)
    risk = next(r for r in rep.risks if r.code == "pack.missing-dependency")
    assert risk.subject == "flywheel"
    assert risk.level is Severity.ERROR


# --- the promise ------------------------------------------------------------
def test_scanning_writes_nothing(tmp_path: Path) -> None:
    root = server(tmp_path, logs="[12:00:00] [Server thread/INFO]: Done\n",
                  reports=[OOM])
    before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    inspect(root)
    after = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    assert before == after


def test_the_output_says_it_is_not_a_monitor(tmp_path: Path, capsys) -> None:
    root = server(tmp_path)
    assert main(["--server", str(root)]) == 0
    out = capsys.readouterr().out
    assert "read-only snapshot" in out
    assert "not a live monitor" in out


def test_a_broken_pack_makes_the_command_fail(tmp_path: Path) -> None:
    root = server(tmp_path)
    (root / "mods").mkdir()
    jar(root / "mods" / "create.jar", {"schemaVersion": 1, "id": "create",
                                       "version": "0.5.1",
                                       "depends": {"flywheel": "*"}})
    assert main(["--server", str(root)]) == 1
