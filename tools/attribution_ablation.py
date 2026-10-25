#!/usr/bin/env python
"""Attribution ablation: how much of the attribution is actually ours?

WHY THIS EXISTS
  `triage()` awards `W_GAME_SUSPECTED=12` to whatever the crash report's own
  ``Suspected Mods:`` line names. That line is the strongest available signal --
  the loader computes it from crash-time classloader context -- but it also
  means "our top-1 is in the game's list" is **partly circular**: we are partly
  quoting the file back.

  So the interesting number is not agreement with the hint. It is what happens
  when the hint is removed: do the independent signals (mixin ownership,
  mod-owned frames, mixin-generated method names, jar markers, message
  classes) still land on the mod the loader named?

    python tools/attribution_ablation.py [--json corpus/attribution-ablation.json]

  Reports that carry no ``Suspected Mods:`` line cannot be scored at all --
  there is nothing independent to compare against -- which is exactly why this
  measurement (n≈37) does not replace the maintainer-verdict blind evaluation
  (`tools/blind_eval.py`, n=7 scored). It is the *other* half: a larger sample
  against a weaker oracle.

WHAT IT IS NOT
  The loader's line is a heuristic, not ground truth. ``minecraft`` and
  `fabricloader` appear in it as "suspected mods" and are filtered out here,
  but a report can still be wrong about its own culprit. Agreement therefore
  bounds consistency, not correctness.
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GITHUB = os.path.join(ROOT, "corpus", "github")

#: Names that show up in ``Suspected Mods:`` but denote the platform, not a mod.
#: Leaving them in makes "did we agree?" trivially true (the loader blames
#: ``minecraft`` quite often) and hides real disagreement.
PLATFORM = frozenset({
    "minecraft", "forge", "neoforge", "fabricloader", "fabric_loader",
    "quilt_loader", "quiltloader", "java", "javafml", "lowcodefml",
    "mixinextras",
})


def _same(a: str | None, b: str | None) -> bool:
    """Slug-tolerant identity: 'mekanismgenerators' ~ 'mekanism' is NOT a match,
    but 'curios' vs 'Curios' is, and 'fabric-registry-sync-v0' vs
    'fabric_registry_sync_v0' is."""
    if not a or not b:
        return False
    x = a.lower().replace("_", "-")
    y = b.lower().replace("_", "-")
    return x == y or x.startswith(y) or y.startswith(x)


def classify(top: str | None, oracle: str) -> str:
    if not top:
        return "silent"
    return "hit" if _same(top, oracle) else "miss"


def run() -> dict:
    from mcd.parser.report import parse_file
    from mcd.triage.attribution import triage

    files = sorted(glob.glob(os.path.join(GITHUB, "*", "*.crash.txt")))
    if not files:
        sys.exit("no harvested corpus -- run tools/harvest_corpus.py")

    rows = []
    for p in files:
        rep = parse_file(p)
        real = [s for s in rep.suspected_mods
                if s and s.lower() not in PLATFORM and s != "unknown"]
        if not real:
            continue
        oracle = real[0]
        hint_on = triage(rep)
        hint_off = triage(dataclasses.replace(rep, suspected_mods=[]))
        top_on = hint_on.suspects[0].modid if hint_on.suspects else None
        top_off = hint_off.suspects[0].modid if hint_off.suspects else None
        rows.append({
            "report": os.path.relpath(p, GITHUB).replace(os.sep, "/"),
            "oracle": oracle,
            "oracle_full": rep.suspected_mods,
            "mod_list_rows": len(rep.mods),
            "top_with_hint": top_on,
            "top_without_hint": top_off,
            "verdict_with_hint": classify(top_on, oracle),
            "verdict_without_hint": classify(top_off, oracle),
            "evidence": (hint_off.suspects[0].reasons[:3]
                         if hint_off.suspects else []),
        })
    return {"n": len(rows), "rows": rows}


def summarise(doc: dict) -> None:
    rows = doc["rows"]
    n = len(rows)
    with_list = [r for r in rows if r["mod_list_rows"]]
    without_list = [r for r in rows if not r["mod_list_rows"]]

    print(f"reports with a non-platform 'Suspected Mods' entry: {n}")
    for name, sel in (("with a Mod List", with_list),
                      ("no Mod List", without_list)):
        if not sel:
            continue
        on = Counter(r["verdict_with_hint"] for r in sel)
        off = Counter(r["verdict_without_hint"] for r in sel)
        print(f"\n  {name} (n={len(sel)})")
        print(f"    hint ON  : {dict(on)}")
        print(f"    hint OFF : {dict(off)}")

    off = Counter(r["verdict_without_hint"] for r in rows)
    silent = off.get("silent", 0)
    answered = n - silent
    print(f"\n  independent answer available : {answered}/{n}")
    if answered:
        hit = off.get("hit", 0)
        print(f"  of those, same mod as loader : {hit}/{answered}")
    print(f"  silent without the hint      : {silent}/{n} "
          f"({silent / n:.0%})")

    if silent:
        print("\n  silent reports (evidence did not reach a mod id):")
        for r in rows:
            if r["verdict_without_hint"] == "silent":
                print(f"    {r['report']:44} loader said '{r['oracle']}'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(
        ROOT, "corpus", "attribution-ablation.json"))
    args = ap.parse_args()
    doc = run()
    doc["generated_by"] = "tools/attribution_ablation.py"
    doc["caveat"] = ("oracle is the loader's own Suspected Mods line, not "
                     "ground truth; see module docstring")
    with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    summarise(doc)
    print(f"\nwrote {os.path.relpath(args.json, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
