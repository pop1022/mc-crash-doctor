#!/usr/bin/env python
"""How much of the rule set speaks Chinese.

    python tools/i18n_status.py            # summary per pack + missing ids
    python tools/i18n_status.py --json     # machine-readable

A rule counts as translated when all three fields are present: a translated
title over an English explanation reads worse than leaving the rule alone, so
the bar is the whole finding, not the headline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcd.rules.engine import RuleSet  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rs = RuleSet.load()
    rows = [
        {
            "id": r.id,
            "pack": Path(r.source).name,
            "done": bool(r.title_zh and r.explanation_zh and r.fixes_zh),
            "partial": bool(r.title_zh or r.explanation_zh or r.fixes_zh),
        }
        for r in rs.rules
    ]
    done = [r for r in rows if r["done"]]
    partial = [r for r in rows if r["partial"] and not r["done"]]
    report = {
        "total": len(rows),
        "translated": len(done),
        "partial": [r["id"] for r in partial],
        "missing": [r["id"] for r in rows if not r["partial"]],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    pct = 100 * len(done) / max(1, len(rows))
    print(f"rules: {len(done)}/{len(rows)} translated ({pct:.0f}%)")
    packs: dict[str, list[bool]] = {}
    for r in rows:
        packs.setdefault(r["pack"], []).append(r["done"])
    for pack, flags in sorted(packs.items()):
        print(f"  {pack:<26} {sum(flags)}/{len(flags)}")
    if partial:
        print("\npartially translated (a Chinese title over an English body is"
              " worse than nothing -- finish or revert):")
        for rid in report["partial"]:
            print(f"  {rid}")
    if report["missing"]:
        print(f"\nmissing ({len(report['missing'])}): " + ", ".join(report["missing"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
