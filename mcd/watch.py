"""Watch a live server log and diagnose a crash the moment it lands.

    mc-crash-doctor --watch logs/latest.log

Design constraints, all deliberate:

* Poll, do not depend. A file watcher library (watchdog/inotify) is a new
  dependency and behaves differently on Windows, WSL and network shares. A
  byte-offset poll every half second costs nothing on a log that is written a
  few times a minute.
* Diagnose the window, not the tail. A crash report is spread over hundreds of
  lines; the interesting context is what came BEFORE the marker, so the
  diagnosis runs on the last N lines (default 2000), not on the new bytes.
* One finding per event. After a crash is diagnosed the byte offset is already
  past it, so the same crash is never diagnosed twice. A restart of the
  watcher re-reads from the end, not from the beginning.
* Read-only. This never writes to the log, never rotates it, never touches the
  server.
"""
from __future__ import annotations

import io
import re
import time
from collections import deque
from pathlib import Path
from typing import Callable

#: Lines that mean "a crash just happened or is being written". Kept narrow on
#: purpose: a WARN-level exception in a log is noise, and firing on it trains
#: the user to ignore the watcher.
CRASH_RE = re.compile(
    r"(/FATAL\]|Unreported exception|ServerHangWatchdog detected|"
    r"A single server tick took|Encountered an unexpected exception|"
    r"---- Minecraft Crash Report ----|"
    r"java\.lang\.OutOfMemoryError)",
    re.IGNORECASE,
)


class Tail:
    """Byte-offset reader. at_end=True starts at EOF (live), False replays."""

    def __init__(self, path: str | Path, *, at_end: bool = True) -> None:
        self.path = Path(path)
        self._pos = self.path.stat().st_size if at_end else 0
        #: Set when the file shrank under us (rotation by the server, or a
        #: logrotate copy-truncate). The caller must drop its window: those
        #: lines belong to the previous file, and mixing them into the next
        #: diagnosis produces findings from a crash that is no longer on disk.
        self.rotated = False

    def read_new(self) -> str:
        try:
            size = self.path.stat().st_size
        except OSError:
            return ""
        if size < self._pos:                     # truncated or rotated: start over
            self._pos = 0
            self.rotated = True
        if size == self._pos:
            return ""
        with self.path.open("rb") as fh:
            fh.seek(self._pos)
            chunk = fh.read(size - self._pos)
        self._pos = size
        return chunk.decode("utf-8", errors="replace")


def is_crash_line(text: str) -> bool:
    return bool(CRASH_RE.search(text))


def _trigger_line(chunk: str, limit: int = 100) -> str:
    """The first line that fired, for the header. Context, not a verdict."""
    for line in chunk.splitlines():
        if CRASH_RE.search(line):
            line = line.strip()
            return line if len(line) <= limit else line[:limit - 1] + "…"
    return "(crash marker)"


def _emit_now(text: str) -> None:
    """Default emitter: flushed per diagnosis.

    print() to a pipe is block-buffered. Piping the watcher through tee showed
    nothing for minutes, and killing it threw the buffered diagnosis away --
    the exact case where someone is watching a server at 3am.
    """
    print(text, flush=True)


def watch(path: str | Path, *, window: int = 2000, poll: float = 0.5,
          once: bool = False, at_end: bool = True,
          emit: Callable[[str], None] = _emit_now,
          iterations: int | None = None,
          sleep: Callable[[float], None] = time.sleep) -> int:
    """Follow a log and diagnose each crash once. Returns an exit code."""
    from .cli import diagnose
    from .report.render import render_plain

    tail = Tail(path, at_end=at_end)
    ring: deque[str] = deque(maxlen=window)
    n = 0
    while iterations is None or n < iterations:
        n += 1
        new = tail.read_new()
        if tail.rotated:
            # The file under us was replaced. Keep the byte offset, drop the
            # window: the previous file's lines must not lend their evidence
            # to the next crash.
            ring.clear()
            tail.rotated = False
        if new:
            ring.extend(new.splitlines())
            if is_crash_line(new):
                try:
                    rep, findings, triage = diagnose(
                        None, "\n".join(ring), source=str(path))
                except Exception as e:           # noqa: BLE001 - a bad chunk is not fatal
                    emit(f"watch: could not diagnose this chunk: "
                         f"{type(e).__name__}: {e}")
                else:
                    buf = io.StringIO()
                    render_plain(rep, findings, triage, buf)
                    # One emit per crash, header included: a caller that
                    # collects chunks still gets exactly one chunk per event,
                    # and a human gets a separator between two diagnoses.
                    stamp = time.strftime("%H:%M:%S")
                    emit(f"\n[{stamp}] crash detected -- {_trigger_line(new)}\n"
                         f"{buf.getvalue()}")
                    if once:
                        return 0
        if iterations is None or n < iterations:
            sleep(poll)
    return 0
