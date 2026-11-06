"""Crash fingerprints for grouping reports that died the same way.

AUDIT §4 asks for "one conclusion + a count" instead of N near-identical
reports. The tempting key is the exception message, but that merges different
failures that happen to share a wording. So the fingerprint is a **tuple**, and
the tool always prints the differences inside a cluster -- a coarse group is
visible, not hidden.

    (loader, normalised root-cause kind + message, top suspect, top frame)

Deliberately excluded: report id, mod list, timestamps, file paths and any
number that identifies one instance. Those are exactly what makes two copies
of the same bug look different.

    python tools/crash_fingerprints.py --json
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .model import CrashReport

#: Per-report values that must not change the fingerprint.
_QUOTED = re.compile(r'["\'][^"\']*["\']')
_FQCN = re.compile(r"\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){2,}\b")
_PATH = re.compile(r"[A-Za-z]:[\\/][^\s'\"]*")
_URL = re.compile(r"https?://\S+")
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)*")
_WS = re.compile(r"\s+")


def normalise(message: str) -> str:
    """Turn an exception message into a shape: keep words, drop values."""
    text = message or ""
    for rx, repl in ((_URL, "<url>"), (_PATH, "<path>"),
                     (_QUOTED, "<q>"), (_FQCN, "<fqcn>")):
        text = rx.sub(repl, text)
    text = _NUMBER.sub("#", text)
    text = _WS.sub(" ", text).strip()
    return " ".join(text.split()[:10]) or "(no message)"


def _top_frame(rep: CrashReport) -> str:
    block = rep.root_cause
    if not block or not block.frames:
        return "(no frames)"
    f = block.frames[0]
    return f"{f.cls}#{f.method}" or f.raw.strip()[:80]


def signature(rep: CrashReport, *, top_suspect: str = "") -> tuple[str, ...]:
    """The human-readable parts of a fingerprint, in a stable order."""
    cause = rep.root_cause
    kind = (cause.kind if cause else "") or "(no exception)"
    return (
        (rep.system.loader or "unknown").lower(),
        f"{kind} | {normalise(cause.message if cause else '')}",
        (top_suspect or "").lower(),
        _top_frame(rep),
    )


def fingerprint(rep: CrashReport, *, top_suspect: str = "") -> str:
    """12-hex-char stable id for one crash shape."""
    joined = "\x1f".join(signature(rep, top_suspect=top_suspect))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def cluster(rows: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Group `(fingerprint, report)` pairs. Kept tiny and deterministic:
    the interesting logic is in what a cluster is allowed to hide."""
    groups: dict[str, list[str]] = {}
    for fp, name in rows:
        groups.setdefault(fp, []).append(name)
    return {k: sorted(v) for k, v in sorted(groups.items(),
                                            key=lambda kv: (-len(kv[1]), kv[0]))}


__all__ = ["fingerprint", "signature", "normalise", "cluster"]
