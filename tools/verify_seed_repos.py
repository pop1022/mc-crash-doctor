"""Verify every repo in tools/seed_repos.txt actually resolves on GitHub.

Stale or mistyped owner/name pairs fail silently in the harvester (a 404 just
looks like "no issues"), so this exists to be run before trusting a seed list.

    python tools/verify_seed_repos.py
    python tools/verify_seed_repos.py --file tools/seed_repos.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "tools" / "seed_repos.txt"


def read_repos(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def check(repo: str) -> tuple[int, str]:
    """Return (http_status, detail)."""
    url = f"https://api.github.com/repos/{repo}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "mc-crash-doctor seed verifier",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
            stars = d.get("stargazers_count", 0)
            issues = d.get("open_issues_count", 0)
            moved = d.get("full_name", "")
            note = ""
            if moved and moved.lower() != repo.lower():
                note = f"  (canonical: {moved})"
            return 200, f"stars={stars:,} open_issues={issues:,}{note}"
    except urllib.error.HTTPError as e:
        return e.code, {"404": "NOT FOUND", "403": "rate limited",
                        "451": "DMCA"}.get(str(e.code), e.reason or "?")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return -1, f"network error: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any entry fails")
    args = ap.parse_args()

    repos = read_repos(Path(args.file))
    print(f"checking {len(repos)} repos from {args.file}\n")
    bad = []
    for r in repos:
        code, detail = check(r)
        mark = "✓" if code == 200 else "✗"
        print(f"  {mark} {r:<46} {code}  {detail}")
        if code != 200:
            bad.append(r)
        time.sleep(0.5)

    print(f"\n{len(repos) - len(bad)}/{len(repos)} ok")
    if bad:
        print("failed:")
        for b in bad:
            print(f"  - {b}")
        return 1 if args.strict else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
