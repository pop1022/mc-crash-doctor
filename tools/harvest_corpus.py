"""Harvest real Minecraft crash reports + maintainer labels from mod repositories.

This is the fuel line for the corpus layer (L1). Two outputs:

1. ``corpus/github/<owner>__<repo>/<issue>.crash.txt`` - the raw crash text
   (local only, gitignored; user-submitted content is not redistributed).
2. ``corpus/index.jsonl`` - a factual index: issue number, state, labels,
   exception classes, mod ids seen in the stack. Facts, not content, so it is
   safe to publish and it doubles as the evaluation manifest.

Maintainer labels (``confirmed`` / ``Not <Mod>`` / ``Loader Issue`` / ``Support``
/ ``duplicate``) are weak supervision: they say what the real root cause was.

Usage::

    python tools/harvest_corpus.py --repo mekanism/Mekanism --max-issues 500
    python tools/harvest_corpus.py --from-file tools/seed_repos.txt --gh-token $GH_TOKEN

Rate limits: unauthenticated = 60 REST req/h. With a token = 5000/h.
The harvester never uses the Search API (10 req/min) for listing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mcd.extract import extract as extract_candidates  # noqa: E402

API = "https://api.github.com"
PER_PAGE = 50  # REST max for issue listing
ROOT = Path(__file__).resolve().parent.parent
CORPUS_GH = ROOT / "corpus" / "github"
INDEX_PATH = ROOT / "corpus" / "index.jsonl"

# --- crash report detection -------------------------------------------------
# A real report has the banner and a Description line. We require both to avoid
# harvesting "it crashes pls help" issues with no data.
BANNER_RE = re.compile(r"---- Minecraft Crash Report ----")
DESCRIPTION_RE = re.compile(r"^Description:\s*(.+)$", re.MULTILINE)
# Fabric reports use "---- Minecraft Crash Report ----" too, but the mod list
# header differs; NeoForge/Fabric logs may arrive as raw log text instead.
LOG_START_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]", re.MULTILINE)

EXCEPTION_RE = re.compile(
    r"^((?:java|javax|net|org|com|cpw|it|io)\.[\w.$]+?"
    r"(?:Exception|Error|Throwable))\s*:?\s*(.{0,120})",
    re.MULTILINE,
)
CAUSED_BY_RE = re.compile(r"^Caused by:\s*(.+)$", re.MULTILINE)
MODID_RE = re.compile(r"from mod \(([A-Za-z0-9_.\-]+)\)")
JAR_RE = re.compile(r"~\[([^\]!]{4,64}?\.jar)")
MIXIN_RE = re.compile(r"pl:mixin:APP:([\w.\-]+)\.mixins\.json:([\w.$]+)")

# --- redaction --------------------------------------------------------------
# Published index and any committed fixture must not carry player names,
# absolute home paths, or IPs.
#
# IPv4 needs care: mod jar filenames contain four-segment version numbers
# (Mekanism-1.21.1-10.7.13.78.jar, minecraft-client-patched-26.1.2.75.jar).
# Redacting those destroys the mod attribution the index exists to record.
# So an IPv4 only counts when (a) every octet is <= 255, (b) it is not part of
# a hyphenated filename token, and (c) it is not followed by .jar/.zip/.log.
_IPV4 = (
    r"(?<![\w.\-])"
    r"(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?![\w\-])(?!\.(?:jar|zip|log)\b)"
)

_REDACTORS: list[tuple[re.Pattern[str], str]] = [
    # Windows home dir
    (re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s]+", re.I), r"<HOME>"),
    # POSIX home dir
    (re.compile(r"/(?:home|Users)/[^\s/]+"), "<HOME>"),
    # Player line: "Player: Steve (uuid)"
    (re.compile(r"(Player:\s*)\S+(.*?)(\s*\(\s*[0-9a-fA-F\-]{8,})"), r"\1<PLAYER>\2\3"),
    # bare usernames in typical launcher paths
    (re.compile(r"(\.minecraft[\\/])([^\\/]+)"), r"\1<INSTANCE>"),
    # IPv4 (see _IPV4 above for why this is not a naive dotted-quad match)
    (re.compile(_IPV4), "<IP>"),
    # UUIDs
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
]


def redact(text: str) -> str:
    """Strip personal identifiers from crash text."""
    for pat, repl in _REDACTORS:
        text = pat.sub(repl, text)
    return text


# --- HTTP -------------------------------------------------------------------
class RateLimited(Exception):
    pass


@dataclass
class Client:
    """Minimal GitHub REST client with rate-limit awareness."""

    pat: str | None = None
    remaining: int = 60
    reset_at: float = 0.0
    requests_made: int = 0

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "mc-crash-doctor-corpus-harvester",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.pat:
            h["Authorization"] = f"Bearer {self.pat}"
        return h

    def get(self, path: str, *, params: dict | None = None) -> list | dict:
        url = path if path.startswith("http") else f"{API}{path}"
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params)}"
        self._guard()
        req = urllib.request.Request(url, headers=self._headers())
        self.requests_made += 1
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self.remaining = int(r.headers.get("X-RateLimit-Remaining", 0))
                reset = r.headers.get("X-RateLimit-Reset")
                self.reset_at = float(reset) if reset else 0.0
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                reset = e.headers.get("X-RateLimit-Reset")
                self.reset_at = float(reset) if reset else time.time() + 900
                self.remaining = 0
                raise RateLimited(url) from e
            if e.code == 404:
                return {}
            raise

    def _guard(self) -> None:
        if self.remaining <= 1 and self.reset_at:
            wait = max(0.0, self.reset_at - time.time()) + 1
            if wait > 3600:
                raise RateLimited(f"rate limit resets in {wait:.0f}s (>1h)")
            print(f"  ⏳ rate limited, sleeping {wait:.0f}s ...", file=sys.stderr)
            time.sleep(wait)
            self.remaining = 60 if not self.pat else 5000


# --- extraction -------------------------------------------------------------
@dataclass
class CrashExtract:
    """What we pull out of one issue body."""

    text: str
    descriptions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    caused_by: list[str] = field(default_factory=list)
    mod_ids: list[str] = field(default_factory=list)
    jars: list[str] = field(default_factory=list)
    mixin_configs: list[str] = field(default_factory=list)
    is_crash_report: bool = False
    is_log: bool = False

    @classmethod
    def parse(cls, body: str) -> "CrashExtract":
        is_crash = bool(BANNER_RE.search(body))
        is_log = (not is_crash) and len(LOG_START_RE.findall(body)) >= 3
        descriptions = [m.strip() for m in DESCRIPTION_RE.findall(body)]
        exceptions = sorted({f"{c}" for c, _ in EXCEPTION_RE.findall(body)})
        caused_by = sorted({m.strip()[:160] for m in CAUSED_BY_RE.findall(body)})
        mod_ids = sorted({m for m in MODID_RE.findall(body) if m != "unknown"})
        jars = sorted(set(JAR_RE.findall(body)))
        mixin_configs = sorted({c for c, _ in MIXIN_RE.findall(body)})
        return cls(
            text=body,
            descriptions=descriptions[:8],
            exceptions=exceptions[:20],
            caused_by=caused_by[:8],
            mod_ids=mod_ids[:60],
            jars=jars[:60],
            mixin_configs=mixin_configs[:60],
            is_crash_report=is_crash,
            is_log=is_log,
        )


# --- labels -----------------------------------------------------------------
# Maps maintainer label -> root-cause verdict. This is the weak supervision.
LABEL_SEMANTICS: dict[str, str] = {
    "confirmed": "bug_in_this_mod",
    "not mekanism": "root_cause_elsewhere",
    "not create": "root_cause_elsewhere",
    "not our issue": "root_cause_elsewhere",
    "loader issue": "loader_layer",
    "forge": "loader_layer",
    "fabric": "loader_layer",
    "support": "user_error_or_config",
    "question": "user_error_or_config",
    "not reproducible": "unreproducible",
    "duplicate": "known_issue",
    "fixed in dev": "bug_in_this_mod",
    "has pr": "bug_in_this_mod",
    "critical": "severity_high",
    "important": "severity_high",
    "more info needed": "insufficient_data",
    "waiting feedback": "insufficient_data",
    "invalid": "not_a_bug",
    "format not followed": "meta",
    "didn't bother searching": "meta",
    "old mc": "outdated_version",
    "outdated": "outdated_version",
}


def verdict_from_labels(labels: list[str]) -> str | None:
    """Weak-supervision root-cause verdict, or None if unlabeled."""
    for lab in labels:
        key = lab.strip().lower()
        if key in LABEL_SEMANTICS:
            return LABEL_SEMANTICS[key]
        # generic "Not <ModName>" pattern used by many projects
        if key.startswith("not "):
            return "root_cause_elsewhere"
    return None


# --- harvesting -------------------------------------------------------------
def harvest_repo(
    client: Client,
    repo: str,
    *,
    max_issues: int = 500,
    states: str = "all",
    save_raw: bool = True,
    follow_links: bool = True,
) -> dict:
    owner, _, name = repo.partition("/")
    print(f"\n▶ {repo}", file=sys.stderr)
    kept = 0
    scanned = 0
    page = 1
    verdicts: Counter[str] = Counter()
    exc_counter: Counter[str] = Counter()
    mod_counter: Counter[str] = Counter()

    out_dir = CORPUS_GH / f"{owner}__{name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(INDEX_PATH, "a", encoding="utf-8") as idx:
        while scanned < max_issues:
            try:
                batch = client.get(
                    f"/repos/{owner}/{name}/issues",
                    params={
                        "state": states,
                        "per_page": PER_PAGE,
                        "page": page,
                        "sort": "created",
                        "direction": "desc",
                    },
                )
            except RateLimited:
                print(f"  ✋ {repo}: rate limited at page {page}", file=sys.stderr)
                break
            if not isinstance(batch, list) or not batch:
                break

            for it in batch:
                if "pull_request" in it:
                    continue  # not an issue
                scanned += 1
                body = it.get("body") or ""
                if len(body) < 150:
                    continue
                cand = extract_candidates(
                    body, follow_links=follow_links, pat=client.pat
                )
                text = cand.best
                if not text:
                    continue
                ext = CrashExtract.parse(text)
                if not ext.exceptions and not ext.descriptions:
                    continue
                is_crash = cand.has_banner or ext.is_crash_report
                is_log = cand.has_log_lines or ext.is_log

                labels = [l["name"] for l in it.get("labels", [])]
                verdict = verdict_from_labels(labels)
                if verdict:
                    verdicts[verdict] += 1
                for e in ext.exceptions:
                    exc_counter[e] += 1
                for m in ext.mod_ids:
                    mod_counter[m] += 1

                # The index IS committed (it is factual metadata), so every
                # free-text field taken from the report body must be redacted
                # too -- descriptions/caused_by can carry player names or paths.
                rec = {
                    "repo": repo,
                    "number": it["number"],
                    "title": redact((it.get("title") or ""))[:200],
                    "state": it.get("state"),
                    "created_at": it.get("created_at"),
                    "labels": labels,
                    "verdict": verdict,  # weak supervision, may be null
                    "comments": it.get("comments", 0),
                    "source": cand.sources[0] if cand.sources else "inline",
                    "is_crash_report": is_crash,
                    "is_log": is_log,
                    "descriptions": [redact(d) for d in ext.descriptions],
                    "exceptions": ext.exceptions,
                    "caused_by": [redact(c) for c in ext.caused_by],
                    "mod_ids": ext.mod_ids,
                    "jars": ext.jars,
                    "mixin_configs": ext.mixin_configs,
                    "body_chars": len(body),
                    "url": it.get("html_url"),
                }
                idx.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1

                if save_raw:
                    (out_dir / f"{it['number']}.crash.txt").write_text(
                        redact(text), encoding="utf-8"
                    )

            page += 1
            if len(batch) < PER_PAGE:
                break

    print(
        f"  ✓ scanned {scanned}, kept {kept} | verdicts {dict(verdicts)}",
        file=sys.stderr,
    )
    return {
        "repo": repo,
        "scanned": scanned,
        "kept": kept,
        "verdicts": dict(verdicts),
        "top_exceptions": exc_counter.most_common(10),
        "top_mods": mod_counter.most_common(15),
    }


def _env_pat() -> str | None:
    """Read a GitHub PAT from the environment (never hardcode it)."""
    for var in ("GITHUB_PAT", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def load_index() -> dict[str, set[int]]:
    """Already-harvested issue numbers, for incremental runs."""
    seen: dict[str, set[int]] = {}
    if not INDEX_PATH.exists():
        return seen
    with open(INDEX_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.setdefault(r["repo"], set()).add(r["number"])
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="append", default=[],
                    help="owner/name (repeatable)")
    ap.add_argument("--from-file",
                    help="text file with one owner/name per line (# = comment)")
    ap.add_argument("--max-issues", type=int, default=500,
                    help="cap of issues scanned per repo (default 500)")
    ap.add_argument("--pat", default=_env_pat(),
                    help="GitHub personal access token for 5000 req/h")
    ap.add_argument("--states", default="all", choices=["open", "closed", "all"])
    ap.add_argument("--dry-run", action="store_true",
                    help="report rate limit and exit")
    ap.add_argument("--no-follow-links", action="store_true",
                    help="skip fetching mclo.gs/gist/pastebin links")
    ap.add_argument("--no-raw", action="store_true",
                    help="index only; do not save crash text locally")
    args = ap.parse_args()

    repos = list(args.repo)
    if args.from_file:
        for line in Path(args.from_file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                repos.append(line)
    if not repos:
        ap.error("need --repo or --from-file")

    client = Client(pat=args.pat)
    print(
        f"auth: {'token (5000/h)' if client.pat else 'anonymous (60/h)'}",
        file=sys.stderr,
    )
    if args.dry_run:
        try:
            rl = client.get("/rate_limit")
            core = rl.get("resources", {}).get("core", {})
            print(f"core: {core.get('remaining')}/{core.get('limit')} "
                  f"reset in {(core.get('reset',0)-time.time()):.0f}s")
        except Exception as e:  # noqa: BLE001
            print("rate_limit query failed:", e)
        return 0

    summary = []
    for repo in repos:
        try:
            summary.append(harvest_repo(
                client, repo, max_issues=args.max_issues, states=args.states,
                save_raw=not args.no_raw,
                follow_links=not args.no_follow_links))
        except KeyboardInterrupt:
            print("\ninterrupted; index kept", file=sys.stderr)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {repo}: {e}", file=sys.stderr)
        time.sleep(1.0)

    print("\n════════ summary ════════", file=sys.stderr)
    tot = 0
    for s in summary:
        tot += s["kept"]
        print(f"  {s['repo']:<42} kept {s['kept']:>4} / scanned {s['scanned']:<5}"
              f" verdicts={s['verdicts']}", file=sys.stderr)
    print(f"  {'TOTAL':<42} kept {tot}", file=sys.stderr)
    print(f"  requests used: {client.requests_made}", file=sys.stderr)
    (ROOT / "corpus" / "harvest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
