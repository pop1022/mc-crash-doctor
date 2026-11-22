#!/usr/bin/env python
"""Export a redacted, reproducible slice of the harvested corpus.

Why this exists: 75.8% is the project's headline claim, and the reports it is
computed from are gitignored (they are other people's bug reports). That makes
the number unverifiable from a clone. This script produces a *shareable* slice:
every report passes the same redact() the harvester uses, each file gets a
sha256, and the manifest records the sample size and seed so a third party can
re-run the engine and compare.

    python tools/export_corpus_sample.py --limit 200 --seed 0 --out dist/corpus-sample

The output is safe to publish when redact() has done its job; the script
verifies that by re-running redact() on its own output and refusing to write a
file that would change a second time (an idempotency failure means a redactor
pattern missed something).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from harvest_corpus import redact  # noqa: E402

#: redact() only masks IPv4 addresses in *network* contexts, to avoid eating
#: version numbers -- measured: a bare "At 192.168.1.55" survives it. That is
#: fine for a gitignored corpus and not fine for a published sample, so the
#: exporter adds a second, blunt pass for private ranges. Defence in depth, not
#: a replacement: public addresses are still handled by redact() context rules.
_PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")


def harden(text: str) -> str:
    """Redact private-range IPv4 addresses wherever they appear."""
    return _PRIVATE_IP.sub("<IP>", text)


def _slug(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix().replace("/", "__")
    except ValueError:
        return p.name


def export(limit: int, seed: int, out: Path, *, source: Path | None = None) -> dict:
    src = source or (ROOT / "corpus" / "github")
    files = sorted(src.rglob("*.txt"))
    rng = random.Random(seed)
    picked = files if limit >= len(files) else rng.sample(files, limit)
    picked = sorted(picked)

    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    entries, skipped = [], []
    for f in picked:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            skipped.append({"file": str(f), "reason": str(e)})
            continue
        clean = harden(redact(text))
        if redact(clean) != clean:          # idempotency: a pattern missed
            skipped.append({"file": str(f), "reason": "redaction not idempotent"})
            continue
        name = _slug(f, src)
        (reports / name).write_text(clean, encoding="utf-8")
        entries.append({
            "file": name,
            "sha256": hashlib.sha256(clean.encode("utf-8")).hexdigest(),
            "bytes": len(clean.encode("utf-8")),
        })

    manifest = {
        "generated_by": "tools/export_corpus_sample.py",
        "source": "corpus/github (gitignored upstream)",
        "limit": limit,
        "seed": seed,
        "available": len(files),
        "exported": len(entries),
        "skipped": skipped,
        "reports": entries,
        "note": ("Every report passed redact() twice: once on export and once to "
                 "prove the result is stable. Verify a run with: "
                 "python -m mcd exported/<file> --json"),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="dist/corpus-sample")
    ap.add_argument("--source", default=None, help="override corpus/github (tests)")
    args = ap.parse_args()

    out = Path(args.out)
    man = export(args.limit, args.seed, out, source=Path(args.source) if args.source else None)
    print(f"exported {man['exported']}/{man['available']} reports to {out}")
    if man["skipped"]:
        print(f"skipped {len(man['skipped'])} (see manifest.json)")
        for s in man["skipped"][:5]:
            print("  ", s["file"], "-", s["reason"])
    print("manifest:", out / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
