"""The live watcher: byte-offset tailing, one diagnosis per crash, no writes."""
from __future__ import annotations

from pathlib import Path

from mcd.watch import Tail, is_crash_line, watch

LOG = """[12:00:00] [Server thread/INFO]: Starting minecraft server version 1.20.1
[12:00:01] [Server thread/INFO]: Done (3.2s)! For help, type "help"
"""

CRASH = """[12:00:30] [Server thread/INFO]: Saving chunks for level 'ServerLevel[world]'/minecraft:overworld
[12:00:31] [Server thread/FATAL]: Unreported exception thrown!
java.lang.OutOfMemoryError: Java heap space
\tat net.minecraft.world.level.Level.tickEntities(Level.java:512)
"""


def test_tail_reads_only_new_bytes(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text("one\n", encoding="utf-8")
    tail = Tail(log, at_end=False)
    # read_new returns bytes decoded as-is, so compare after newline normalising:
    # write_text translates \\n to \\r\\n on Windows.
    assert tail.read_new().replace("\r\n", "\n") == "one\n"
    assert tail.read_new() == ""
    with log.open("a", encoding="utf-8") as fh:
        fh.write("two\n")
    assert tail.read_new().replace("\r\n", "\n") == "two\n"


def test_tail_survives_truncation(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text("x" * 100, encoding="utf-8")
    tail = Tail(log, at_end=False)
    tail.read_new()
    log.write_text("y", encoding="utf-8")            # rotated to a smaller file
    assert tail.read_new() == "y"


def test_markers_are_narrow() -> None:
    assert is_crash_line("[12:00:31] [Server thread/FATAL]: boom")
    assert is_crash_line("---- Minecraft Crash Report ----")
    assert is_crash_line("java.lang.OutOfMemoryError: Java heap space")
    assert not is_crash_line("[12:00:01] [Server thread/INFO]: Done (3.2s)!")
    assert not is_crash_line("[12:00:02] [Server thread/WARN]: Can't keep up")


def test_watch_diagnoses_once(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text(LOG + CRASH, encoding="utf-8")
    out: list[str] = []

    code = watch(log, at_end=False, once=True, iterations=5,
                 emit=out.append, sleep=lambda _s: None)

    assert code == 0
    assert len(out) == 1, out
    assert "FINDINGS" in out[0] or "oom" in out[0].lower()


def test_watch_ignores_a_quiet_log(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text(LOG, encoding="utf-8")
    out: list[str] = []
    watch(log, at_end=False, iterations=2, emit=out.append, sleep=lambda _s: None)
    assert out == []

# --- the live experience ----------------------------------------------------
def test_each_diagnosis_starts_with_a_timestamped_header(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text(LOG + CRASH, encoding="utf-8")
    out: list[str] = []
    watch(log, at_end=False, once=True, iterations=5,
          emit=out.append, sleep=lambda _s: None)
    assert len(out) == 1
    assert out[0].startswith("\n[")            # [HH:MM:SS]
    assert "crash detected" in out[0]
    assert "Unreported exception" in out[0]     # the trigger, for context


def test_rotation_drops_the_previous_file_s_window(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_text(LOG + CRASH, encoding="utf-8")   # OOM crash
    watchdog = (
        "[12:10:00] [Server thread/INFO]: tick\n"
        "[12:10:01] [Server thread/FATAL]: ServerHangWatchdog detected that a "
        "single server tick took 120.00 seconds\n"
    )
    state = {"n": 0}

    def sleep(_s: float) -> None:
        state["n"] += 1
        if state["n"] == 1:
            log.write_text(LOG + watchdog, encoding="utf-8")   # rotate

    out: list[str] = []
    watch(log, at_end=False, iterations=3, emit=out.append, sleep=sleep)
    assert len(out) == 2, out
    # The second diagnosis must not carry the OOM that was only in the file
    # before it was replaced. (What it *does* find depends on the rule set --
    # the point here is the cleared window.)
    assert "oom.heap" not in out[1]
    assert "Java heap space" not in out[1]
    assert "ServerHangWatchdog detected" in out[1]     # the new trigger
