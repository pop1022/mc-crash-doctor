"""What kind of text did the user paste?

Diagnosis is forgiving, but three inputs are not crash reports and deserve a
specific answer instead of an empty findings list:

  hs_err      a JVM fatal-error log. Native crash, usually the graphics driver
              or a native library; Minecraft rules cannot say anything about it.
  exit_code   "exit code: 1" on its own. Not enough to diagnose -- the log from
              the same run is.
  report / log / prose   what the existing heuristics already distinguish.

Kept dependency-free so the browser bundle and the CLI can agree on the shapes.
"""
from __future__ import annotations

import re

#: The one line every HotSpot fatal-error log starts with.
_HS_ERR = re.compile(
    r"^#\s*A fatal error has been detected by the Java Runtime Environment",
    re.MULTILINE)

#: "exit code: 1", "Process finished with exit code -1073741819", "exit status 1".
_EXIT_CODE = re.compile(
    r"(?:\bexit\s*(?:code|status)\s*[:=]?\s*-?\d+)"
    r"|(?:\bprocess\s+(?:exited|finished)\s+with\s+(?:exit\s+)?(?:code|status)"
    r"\s*-?\d+)",
    re.IGNORECASE)

_REPORT_MARKERS = (
    re.compile(r"----\s*Minecraft Crash Report", re.IGNORECASE),
    re.compile(r"^\s*Description:", re.MULTILINE),
)


def is_hs_err(text: str) -> bool:
    return bool(_HS_ERR.search(text or ""))


def is_exit_code_only(text: str) -> bool:
    """An exit code with nothing else around it is the whole input."""
    body = (text or "").strip()
    if not body or len(body) > 200:
        return False
    if not _EXIT_CODE.search(body):
        return False
    # A real log that happens to mention an exit code also has lines around it.
    return len(body.splitlines()) <= 2


def looks_like_report(text: str) -> bool:
    body = text or ""
    if any(p.search(body) for p in _REPORT_MARKERS):
        return True
    if len(re.findall(r"^\s*(?:at|\tat)\s+[\w.$]+\s*\(", body, re.MULTILINE)) >= 2:
        return True
    if len(re.findall(r"^\s*\[\d{2}:\d{2}:\d{2}\]", body, re.MULTILINE)) >= 2:
        return True
    return bool(re.search(r"Starting minecraft server version|"
                          r"Done \(\d+(?:\.\d+)?s\)!", body, re.IGNORECASE))


def classify(text: str) -> str:
    if is_hs_err(text):
        return "hs_err"
    if is_exit_code_only(text):
        return "exit_code"
    if looks_like_report(text):
        return "report"
    return "prose"
