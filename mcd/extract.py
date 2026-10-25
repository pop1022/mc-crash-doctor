"""Extract crash-report text out of GitHub issue bodies.

Issue bodies are markdown: the report may be inside a fenced block (often
indented), pasted inline, or replaced by a link to mclo.gs / gist / pastebin.
This module normalises all three so downstream parsing sees plain log text.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__

CACHE_DIR = Path(os.environ.get("MCD_CACHE", str(Path.home() / ".cache" / "mcd-corpus")))

BANNER_RE = re.compile(r"-{2,}\s*Minecraft Crash Report\s*-{2,}", re.I)
# Fabric/NeoForge client reports sometimes omit the banner; a Description line
# plus stack frames is strong enough.
DESCRIPTION_RE = re.compile(r"^\s*Description:\s*(.+?)\s*$", re.M)
STACKFRAME_RE = re.compile(r"^\s*(?:at|\u0009at)\s+[\w.$/]+\s*\(", re.M)
LOG_LINE_RE = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\]", re.M)

FENCE_RE = re.compile(
    r"^[ \t]*(?:```+|~~~+)[^\n]*\n(.*?)^[ \t]*(?:```+|~~~+)[ \t]*$",
    re.M | re.S,
)

# External paste hosts we know how to dereference.
#
# mclo.gs share links are https://mclo.gs/<id> (ONE path segment) -- the
# optional middle segment only covers the older "mclo.gs/<name>/<id>" shape
# people still paste. The raw API form (api.mclo.gs/1/raw/<id>) is matched
# separately, because "1/raw" would otherwise be read as that middle segment.
# Both spellings previously fell through to `None`, so `--url <share link>`
# silently fetched the HTML page instead of the log.
MCLOGS_RE = re.compile(
    r"https?://(?:(?:www\.)?mclo\.gs/(?:[\w-]+/)?(?P<id>[A-Za-z0-9]+)"
    r"|api\.mclo\.gs/\d+/raw/(?P<raw>[A-Za-z0-9]+))",
    re.I,
)
GIST_RE = re.compile(r"https?://gist\.github\.com/(?:[\w.\-]+/)?([0-9a-f]{32})", re.I)
PASTEBIN_RE = re.compile(r"https?://pastebin\.com/(?:raw/)?([A-Za-z0-9]{8})", re.I)


def mclogs_id(url: str) -> str | None:
    """The paste id in a mclo.gs share link or raw API URL, else None."""
    m = MCLOGS_RE.search(url)
    if not m:
        return None
    return m.group("id") or m.group("raw")


@dataclass
class Extracted:
    """Normalised crash text found in one issue body."""

    body: str
    texts: list[str] = field(default_factory=list)      # candidate log blobs
    sources: list[str] = field(default_factory=list)    # 'inline' | 'mclo.gs:xxx' ...
    has_banner: bool = False
    has_log_lines: bool = False

    @property
    def best(self) -> str | None:
        """Longest candidate that looks like a real report/log."""
        ranked = sorted(self.texts, key=len, reverse=True)
        return ranked[0] if ranked else None


def _dedent_block(text: str) -> str:
    """Remove markdown quoting/indent so a pasted report reads as plain text."""
    lines = text.splitlines()
    # strip leading '>' quote markers
    if lines and all((not ln.strip()) or ln.lstrip().startswith(">") for ln in lines):
        lines = [re.sub(r"^\s*>\s?", "", ln) for ln in lines]
    return textwrap.dedent("\n".join(lines))


def _looks_like_report(text: str) -> bool:
    if BANNER_RE.search(text):
        return True
    if DESCRIPTION_RE.search(text) and len(STACKFRAME_RE.findall(text)) >= 2:
        return True
    if len(LOG_LINE_RE.findall(text)) >= 5:
        return True
    # bare stack trace blob (common in bug reports written by hand)
    if len(STACKFRAME_RE.findall(text)) >= 4:
        return True
    return False


READ_LIMIT = 8_000_000
_UA_HARVEST = "mc-crash-doctor corpus harvester (research)"
_TIMEOUTS = (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError)


def _http_get(url: str, *, timeout: int, ua: str) -> str | None:
    """GET a URL as text; None on any network, HTTP or TLS failure."""
    req = urllib.request.Request(
        url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(READ_LIMIT).decode("utf-8", errors="replace")
    except _TIMEOUTS:
        return None


def _fetch(url: str, *, timeout: int = 25) -> str | None:
    """Cached GET, for the corpus harvester (batch work, staleness is fine)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"\W+", "_", url)[-120:]
    cache = CACHE_DIR / f"{key}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    data = _http_get(url, timeout=timeout, ua=_UA_HARVEST)
    if not data or len(data) < 60:
        return None
    cache.write_text(data, encoding="utf-8")
    return data


def deref_mclogs(log_id: str) -> str | None:
    """Fetch a mclo.gs paste through its public raw API."""
    return _fetch(f"https://api.mclo.gs/1/raw/{log_id}")


def deref_gist(gist_id: str, pat: str | None = None) -> str | None:
    """Fetch the first sizable file of a gist."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "User-Agent": "mc-crash-doctor corpus harvester",
        "Accept": "application/vnd.github+json",
    }
    if pat:
        headers["Authorization"] = f"Bearer {pat}"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"gist_{gist_id}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    files = d.get("files") or {}
    best = max(files.values(), key=lambda f: f.get("size", 0), default=None)
    if not best:
        return None
    content = best.get("content")
    if not content and best.get("raw_url"):
        content = _fetch(best["raw_url"])
    if content:
        cache.write_text(content, encoding="utf-8")
    return content


def deref_pastebin(pid: str) -> str | None:
    return _fetch(f"https://pastebin.com/raw/{pid}")


# One row per supported paste host: how to find its links, how to pull the id
# out of a match, the label recorded in `sources`, and how to dereference it.
# The three hosts used to be three copy-pasted loops; adding a fourth host is
# now a single row instead of another 12-line block.
_PASTE_HOSTS: tuple[tuple[re.Pattern[str], Callable[[re.Match], str], str], ...] = (
    (MCLOGS_RE, lambda m: m.group("id") or m.group("raw"), "mclo.gs"),
    (GIST_RE, lambda m: m.group(1), "gist"),
    (PASTEBIN_RE, lambda m: m.group(1), "pastebin"),
)


def _deref(host: str, pid: str, pat: str | None) -> str | None:
    if host == "mclo.gs":
        return deref_mclogs(pid)
    if host == "gist":
        return deref_gist(pid, pat=pat)
    return deref_pastebin(pid)


def _follow_links(out: Extracted, body: str, *, pat: str | None,
                  max_links: int) -> None:
    """Dereference up to `max_links` pastes and keep the ones that are reports."""
    seen: set[str] = set()
    for regex, ident, host in _PASTE_HOSTS:
        for m in regex.finditer(body):
            if len(seen) >= max_links:
                return
            pid = ident(m)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            txt = _deref(host, pid, pat)
            if txt and _looks_like_report(txt):
                out.texts.append(txt)
                out.sources.append(f"{host}:{pid}")
            time.sleep(0.4)


def fetch_log(url: str, *, timeout: int = 30) -> str | None:
    """Fetch a log from a share link or a raw URL (mclo.gs aware).

    Deliberately uncached: this backs the CLI ``--url`` flag and the GitHub
    Action, where re-reading a stale paste would diagnose the wrong crash.
    The corpus harvester uses :func:`_fetch` instead, which caches on disk.
    """
    if "://" not in url:      # tolerate a pasted "mclo.gs/abc123"
        url = "https://" + url
    pid = mclogs_id(url)
    if pid:
        url = f"https://api.mclo.gs/1/raw/{pid}"
    return _http_get(url, timeout=timeout, ua=f"mc-crash-doctor/{__version__}")


def extract(body: str, *, follow_links: bool = True,
            pat: str | None = None, max_links: int = 3) -> Extracted:
    """Pull every candidate crash text out of an issue body.

    ``follow_links`` costs network calls; the harvester turns it on, tests off.
    """
    out = Extracted(body=body)
    out.has_banner = bool(BANNER_RE.search(body))
    out.has_log_lines = len(LOG_LINE_RE.findall(body)) >= 3

    # 1. fenced blocks (dedented)
    for m in FENCE_RE.finditer(body):
        blk = _dedent_block(m.group(1))
        if len(blk) >= 120 and _looks_like_report(blk):
            out.texts.append(blk)
            out.sources.append("inline:fenced")

    # 2. the whole body, if it reads like a report (unfenced paste)
    plain = _dedent_block(body)
    if _looks_like_report(plain):
        out.texts.append(plain)
        out.sources.append("inline:plain")

    if not follow_links:
        return out

    # 3. external pastes
    _follow_links(out, body, pat=pat, max_links=max_links)
    return out
