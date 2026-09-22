"""Debug harness: show why each corpus file got its platform label.

For every mismatch it prints which probes fired, at what tier, and what the
tie-break would have been -- so needles get fixed from evidence.

    python tests/debug_platform.py                     # mismatches only
    python tests/debug_platform.py --all
    python tests/debug_platform.py --file <path>
    python tests/debug_platform.py --probe bedrock     # one platform, all files
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.platform import (LAUNCHER_PROBES, PROBES,  # noqa: E402
                                 detect_platform_detailed)
from tests.eval_parser import EQUIV  # noqa: E402

RANK = {p.loader: i for i, p in enumerate(PROBES)}


def all_hits(text: str, window: int = 40000) -> list:
    scope = text[:window]
    out = []
    for pr in PROBES + LAUNCHER_PROBES:
        m = pr.pattern.search(scope)
        if m:
            out.append((pr.tier, RANK.get(pr.loader, 9999), pr.loader,
                        pr.axis, m.start(), m.group(0)[:52]))
    out.sort(key=lambda h: (h[0], h[1] if h[3] == "loader" else 9999))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--probe", help="only show files where this loader fires")
    ap.add_argument("--window", type=int, default=40000)
    args = ap.parse_args()

    files = [args.file] if args.file else [
        lf for jf in sorted(glob.glob(str(ROOT / "corpus/aternos/**" / "*.json"),
                                      recursive=True))
        if os.path.exists(lf := jf[:-5] + ".log")
    ]

    n = bad = 0
    for lf in files:
        jf = lf[:-4] + ".json"
        text = open(lf, encoding="utf-8", errors="replace").read()
        n += 1
        want_name = ""
        if os.path.exists(jf):
            exp = json.load(open(jf, encoding="utf-8"))
            want_name = (exp.get("name") or "").strip()
        accept = EQUIV.get(want_name, {want_name.lower().replace(" ", "-")})

        hits = all_hits(text, args.window)
        lhit, ahit = detect_platform_detailed(text)
        got_axes = {(lhit.loader if lhit else "vanilla"),
                    (ahit.loader if ahit else "")}
        ok = bool(got_axes & accept)

        if args.probe and not any(h[2] == args.probe for h in hits):
            continue
        if ok and not args.all and not args.probe:
            continue
        if not ok:
            bad += 1

        rel = os.path.relpath(lf, ROOT)
        print(f"\n{'✓' if ok else '✗'} {rel[:78]}")
        print(f"   want={want_name:<18} got={got_axes - {''} or {'vanilla'}}"
              f"  size={len(text):,}B")
        for tier, rank, loader, axis, off, needle in hits[:9]:
            mark = "  "
            if lhit and loader == lhit.loader and axis == "loader":
                mark = "←"
            elif ahit and loader == ahit.loader and axis == "launcher":
                mark = "←"
            print(f"   {mark} T{tier} rank{rank:<3} @{off:>7,} "
                  f"{loader:<20}[{axis:<8}] {needle!r}")
        if not hits:
            print("     (no probe fired → vanilla)")

    print(f"\n════ {bad} mismatches / {n} files ════")
    return 0


if __name__ == "__main__":
    sys.exit(main())
