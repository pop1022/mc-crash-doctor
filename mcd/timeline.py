"""A 60-second view of the log immediately before the crash.

Rules explain *what* killed the process. They cannot show *what happened just
before* -- and in a server log that is often the useful part (a chunk save, a
player joining, a mod reload). This module extracts timestamped log lines,
anchors on the last one, and keeps a window before it.

It is deliberately read-only and dumb: no parsing of levels into severities, no
guessing which line is the crash. A line without a timestamp is skipped, and the
report says how many were skipped rather than quietly dropping them.

One exception, and it is about honesty rather than inference: the lines that
follow the last timestamped entry are usually the exception text that made the
crash worth looking at, and they never carry a timestamp. Those are shown
verbatim, labelled as such -- what a log says is not something to paraphrase.

    python -m mcd latest.log --timeline 60
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TextIO

#: Two real shapes occur: `[12:34:56] [thread/INFO]: msg` (old Forge / Fabric)
#: and `[17Oct2026 00:39:27.039] [main/INFO] ...` (current NeoForge, whose
#: date prefix may even be localised). The prefix is captured but ignored --
#: only HH:MM:SS positions the event on the timeline.
_TS_LINE = re.compile(
    r"^\s*\[(?P<prefix>[^\]]*?)(?P<ts>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*"
    r"(?:\[(?P<tag>[^\]]+)\]\s*[: ]?\s*)?"
    r"(?P<msg>.*)$"
)
_TAG = re.compile(r"^(?P<thread>.*?)(?:/(?P<level>[A-Z]+))?$")


@dataclass(frozen=True)
class Event:
    second: int
    clock: str
    thread: str
    level: str
    message: str


def _to_seconds(clock: str) -> int:
    m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})", clock)
    if not m:                                  # cannot happen: regex matched it
        return 0
    h, mi, se = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + se


def extract_events(text: str) -> tuple[list[Event], int]:
    """`(events, skipped)` in file order. `skipped` counts non-empty lines with
    no timestamp, so silence is reported rather than assumed."""
    events: list[Event] = []
    skipped = 0
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = _TS_LINE.match(line)
        if not m:
            skipped += 1
            continue
        tag = m.group("tag") or ""
        tm = _TAG.match(tag)
        thread = (tm.group("thread") if tm else tag).strip()
        level = (tm.group("level") if tm else "") or ""
        events.append(Event(
            second=_to_seconds(m.group("ts")),
            clock=m.group("ts"),
            thread=thread,
            level=level.upper(),
            message=m.group("msg").strip(),
        ))
    return events, skipped


def trailing_lines(text: str, limit: int = 4) -> list[str]:
    """Non-empty lines after the last timestamped one, in file order.

    A stack trace has no clock prefix; the tail of a log is exactly where the
    exception lives. These are returned verbatim and never folded into the
    timeline, so nothing here is presented as something with a time.
    """
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    tail: list[str] = []
    for line in reversed(lines):
        if _TS_LINE.match(line):
            break
        tail.append(line)
        if len(tail) >= limit:
            break
    return list(reversed(tail))


def window(events: list[Event], seconds: int = 60) -> tuple[list[Event], int]:
    """Events in the `seconds` before the last event, plus the earliest event's
    clock. Handles a midnight wrap (a log that starts 23:59 and ends 00:01) by
    treating a large backwards jump as +24h; the window is still the last N
    seconds of the file."""
    if not events:
        return [], 0
    normalised: list[Event] = []
    day = 0
    prev = events[0].second
    for e in events:
        if e.second < prev - 3600:           # wrapped past midnight
            day += 86400
        prev = e.second
        normalised.append(Event(e.second + day, e.clock, e.thread,
                                e.level, e.message))
    end = normalised[-1].second
    start = end - max(1, seconds)
    chosen = [e for e in normalised if e.second >= start]
    return chosen, start


def render_timeline(events: list[Event], skipped: int, seconds: int,
                    out: TextIO, *, source: str = "",
                    trailing: list[str] | None = None) -> None:
    head = f"Timeline — last {seconds}s of timestamped log lines"
    out.write(head + "\n" + "=" * len(head) + "\n")
    if source:
        out.write(f"source: {source}\n")
    if not events:
        out.write("no timestamped lines found: nothing to place on a timeline.\n")
        if skipped:
            out.write(f"({skipped} non-empty lines had no [HH:MM:SS] prefix)\n")
        return
    out.write(f"{len(events)} events in window "
              f"({events[0].clock} .. {events[-1].clock})\n")
    if skipped:
        out.write(f"({skipped} non-empty lines without a timestamp were skipped)\n")
    out.write("\n")
    for e in events:
        tag = f" [{e.level}]" if e.level else ""
        who = f" ({e.thread})" if e.thread else ""
        out.write(f"{e.clock}{tag}{who}  {e.message}\n")

    if trailing:
        out.write(f"\n  after the last timestamp, verbatim "
                  f"({len(trailing)} line(s)):\n")
        for line in trailing:
            out.write(f"      {line.strip()}\n")


__all__ = ["Event", "extract_events", "trailing_lines", "window",
           "render_timeline"]
