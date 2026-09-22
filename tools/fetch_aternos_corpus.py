"""Re-seed corpus/aternos/ from aternosorg/codex-minecraft (MIT).

Pulls the upstream repository tarball and extracts only the ``test/data``
fixtures (real Minecraft logs + their expected-analysis JSON) into
``corpus/aternos/``. Keeps LICENSE and NOTICE.md in place for attribution.

    python tools/fetch_aternos_corpus.py
    python tools/fetch_aternos_corpus.py --ref master --dry-run

No API token needed (public tarball). Idempotent: overwrites fixtures in place.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "corpus" / "aternos"
REPO = "aternosorg/codex-minecraft"


def fetch_tarball(ref: str) -> bytes:
    url = f"https://github.com/{REPO}/archive/refs/heads/{ref}.tar.gz"
    print(f"fetching {url}", file=sys.stderr)
    req = urllib.request.Request(
        url, headers={"User-Agent": "mc-crash-doctor corpus seeder"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="master", help="branch/tag (default master)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be extracted, write nothing")
    args = ap.parse_args()

    data = fetch_tarball(args.ref)
    n_log = n_json = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t.getmembers():
            if not m.isfile() or "/test/data/" not in m.path:
                continue
            rel = m.path.split("/test/data/", 1)[1]
            if args.dry_run:
                print(f"  would extract {rel}")
            else:
                out = DEST / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(m) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            if rel.endswith(".log"):
                n_log += 1
            elif rel.endswith(".json"):
                n_json += 1

    print(f"\n{'(dry-run) ' if args.dry_run else ''}"
          f"{n_log} .log + {n_json} .json {'would be ' if args.dry_run else ''}"
          f"extracted into {DEST.relative_to(ROOT)}/", file=sys.stderr)
    if not args.dry_run:
        print("LICENSE and NOTICE.md already present for attribution.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
