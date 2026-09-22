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

CACHE_DIR = Path(os.environ.get("MCD_CACHE", str(Path.home() / ".cache" / "mcd-corpus")))

BANNER_RE = re.compile(r"-{2,}\s*Minecraft Crash Report\s*-{2,}", re.I)
# Fabric/NeoForge client reports sometimes omit the banner; a Description line
# plus stack frames is strong enough.
DESCRIPTION_RE = re.compile(r"^\s*Description:\s*(.+?)\s*$", re.M)
STACKFRAME_RE = re.compile(r"^\s*(?:at|\u0009at)\s+[\w.$/]+\s*\(", re.M)
LOG_LINE_RE = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\]", re.M)
NEOFORGE_RE = re.compile(r"neoforge|fml\.ModLoadingException", re.I)

FENCE_RE = re.compile(
    r"^[ \t]*(?:```+|~~~+)[^\n]*\n(.*?)^[ \t]*(?:```+|~~~+)[ \t]*$",
    re.M | re.S,
)

# External paste hosts we know how to dereference.
MCLOGS_RE = re.compile(r"https?://(?:www\.)?(?:api\.)?mclo\.gs/(\w+)/([A-Za-z0-9]+)", re.I)
GIST_RE = re.compile(r"https?://gist\.github\.com/(?:[\w.\-]+/)?([0-9a-f]{32})", re.I)
PASTEBIN_RE = re.compile(r"https?://pastebin\.com/(?:raw/)?([A-Za-z0-9]{8})", re.I)


@dataclass
class Extracted:
    """Normalised crash text found in one issue body."""

    body: str
    texts: list[str] = field(default_factory=list)      # candidate log blobs
    sources: list[str] = field(default_factory=list)    # 'inline' | 'mclo.gs:xxx' ...
    has_banner: bool = False
    has_log_lines: bool = False
    n_stackframes: int = 0

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


def _fetch(url: str, *, timeout: int = 25) -> str | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"\W+", "_", url)[-120:]
    cache = CACHE_DIR / f"{key}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "mc-crash-doctor corpus harvester (research)",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(8_000_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    if len(data) < 60:
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


def extract(body: str, *, follow_links: bool = True,
            pat: str | None = None, max_links: int = 3) -> Extracted:
    """Pull every candidate crash text out of an issue body.

    ``follow_links`` costs network calls; the harvester turns it on, tests off.
    """
    out = Extracted(body=body)
    out.has_banner = bool(BANNER_RE.search(body))
    out.has_log_lines = len(LOG_LINE_RE.findall(body)) >= 3
    out.n_stackframes = len(STACKFRAME_RE.findall(body))

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
    seen: set[str] = set()
    for m in MCLOGS_RE.finditer(body):
        if len(seen) >= max_links:
            break
        lid = m.group(2)
        if lid in seen:
            continue
        seen.add(lid)
        txt = deref_mclogs(lid)
        if txt and _looks_like_report(txt):
            out.texts.append(txt)
            out.sources.append(f"mclo.gs:{lid}")
        time.sleep(0.4)

    for m in GIST_RE.finditer(body):
        if len(seen) >= max_links:
            break
        gid = m.group(1)
        if gid in seen:
            continue
        seen.add(gid)
        txt = deref_gist(gid, pat=pat)
        if txt and _looks_like_report(txt):
            out.texts.append(txt)
            out.sources.append(f"gist:{gid}")
        time.sleep(0.4)

    for m in PASTEBIN_RE.finditer(body):
        if len(seen) >= max_links:
            break
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        txt = deref_pastebin(pid)
        if txt and _looks_like_report(txt):
            out.texts.append(txt)
            out.sources.append(f"pastebin:{pid}")
        time.sleep(0.4)

    return out
