#!/usr/bin/env python
"""Diagnosis rate stratified by Minecraft version.

WHY THIS EXISTS
  Every coverage number this repo publishes is an average over 661 reports. An
  average cannot answer the question a user actually asks -- "does this thing
  work on *my* version?" -- and a version-shaped blind spot is the one structural
  risk that no earlier measurement touched: the rule packs were written against
  reports that happened to be in the corpus, and nothing checked whether the
  modern ones carry the weight.

  So: split the corpus by version, report the rate per stratum *with a Wilson
  interval*, and only then judge the roadmap's failure criterion (adjacent
  versions differ by more than 20 percentage points).

WHY THE INTERVALS DECIDE, NOT THE POINT ESTIMATES
  n=18 at 33% and n=96 at 82% look like a 49-point gap. They are 16-56% and
  73-88%: separated, yes, but the small side is 18 reports and a bare "33%"
  invites a conclusion the data does not support. Strata under 30 reports are
  marked `quotable_as_rate: false` and are excluded from the adjacency chain,
  which is the same discipline `tools/blind_eval.py` applies to 1/7.

WHAT THE CORPUS ACTUALLY CONTAINS (measured, 2026-10-25)
  * 196 of 661 reports (30%) have no `Minecraft Version:` line at all. That is
    not a version stratum -- it is a *shape* stratum (Bedrock logs, issue bodies
    that are not crash reports), and it diagnoses at 49% against 74% overall.
    Treating it as "old version" would be the confound this tool exists to avoid.
  * 22 reports say `26.1`, `26.2`, `26.3`. Those are real: Minecraft moved off
    the `1.x` numbering (`Minecraft Version: 26.1.2 (Tiny Takeover)`). Any
    analysis that filters on a `1.` prefix silently drops them.

    python tools/version_strata.py            # print + write corpus/VERSION_STRATA.md
    python tools/version_strata.py --check    # exit 1 if the committed report is stale
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from blind_eval import wilson              # noqa: E402  (same dir)

OUT_JSON = os.path.join(ROOT, "corpus", "version-strata.json")
OUT_MD = os.path.join(ROOT, "corpus", "VERSION_STRATA.md")

#: Below this, a rate is not quotable -- same bar as `tests/test_blind_eval.py`
#: applies to 1/7. Not a statistical law; a policy this repo already uses.
MIN_N = 30

#: The roadmap's failure criterion for a version-shaped blind spot.
GAP_PP = 0.20

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


def stratum_of(version: str) -> str | None:
    """`1.20.1` -> `1.20`; `26.1.2` -> `26.1`; `""` -> None (no version line).

    Two-component key on purpose: patch releases (1.20.1 vs 1.20.4) share their
    tag names and mod ecosystem, and splitting to three components leaves 55
    strata with a median of 4 reports -- bins too small to say anything.
    """
    v = (version or "").strip()
    if not v:
        return None
    m = _VERSION_RE.match(v)
    return f"{m.group(1)}.{m.group(2)}" if m else f"(unparsed) {v}"


def _sort_key(key: str) -> tuple:
    m = re.match(r"^(\d+)\.(\d+)$", key)
    return (0, int(m.group(1)), int(m.group(2))) if m else (1, 0, 0)


def collect() -> dict:
    from mcd.parser.report import parse_file
    from mcd.rules.engine import RuleSet, run_rules

    rs = RuleSet.load()
    files = (sorted(glob.glob(os.path.join(ROOT, "tests/fixtures/ground-truth/*.txt")))
             + sorted(glob.glob(os.path.join(ROOT, "corpus/github/*/*.crash.txt")))
             + sorted(glob.glob(os.path.join(ROOT, "corpus/aternos/**/*.log"),
                                recursive=True)))
    n = Counter()
    diag = Counter()
    shapes = defaultdict(Counter)      # stratum -> (kind/loader) shape counter
    for p in files:
        rep = parse_file(p)
        key = stratum_of(rep.system.minecraft_version)
        name = key or "(no version line)"
        n[name] += 1
        if run_rules(rep, rs):
            diag[name] += 1
        shapes[name][f"{rep.kind}/{rep.system.loader or '-'}"] += 1
    return {"n": n, "diag": diag, "shapes": shapes, "files": len(files)}


def analyse(raw: dict) -> dict:
    total_n = sum(raw["n"].values())
    total_k = sum(raw["diag"].values())
    strata = []
    for key in sorted(raw["n"], key=lambda k: (_sort_key(k), k)):
        k, nn = raw["diag"][key], raw["n"][key]
        lo, hi = wilson(k, nn)
        top_shape, top_count = (raw["shapes"][key].most_common(1)[0]
                                if raw["shapes"][key] else ("-", 0))
        strata.append({
            "version": key,
            "n": nn,
            "diagnosed": k,
            "rate": round(k / nn, 4) if nn else None,
            "lo": round(lo, 4),
            "hi": round(hi, 4),
            "quotable_as_rate": nn >= MIN_N,
            "share": round(nn / total_n, 4) if total_n else None,
            "dominant_shape": top_shape,
            "dominant_shape_share": round(top_count / nn, 3) if nn else None,
        })

    # Adjacency runs over quotable strata inside one era only. `1.21` and `26.1`
    # are not neighbours even though they sort next to each other, and
    # "(no version line)" is a shape, not a release.
    era = lambda v: ("legacy" if v.startswith("1.") else
                     "dated" if re.match(r"^\d+\.\d+$", v) else "unknown")
    # Every neighbouring pair in the *full* ordering, so the report can say which
    # comparisons did not happen. Printing only the pairs that were checked reads
    # as "1.16 vs 1.19 are adjacent" and hides that 1.17 and 1.18 were skipped
    # for low n -- the exact kind of silent gap this repo keeps finding.
    ordered = [s for s in strata if era(s["version"]) in ("legacy", "dated")]
    skipped = []
    for a, b in zip(ordered, ordered[1:]):
        if era(a["version"]) != era(b["version"]):
            continue
        if a["quotable_as_rate"] and b["quotable_as_rate"]:
            continue
        thin = [s["version"] for s in (a, b) if not s["quotable_as_rate"]]
        skipped.append({"a": a["version"], "b": b["version"],
                        "under_min_n": thin,
                        "n": {s["version"]: s["n"] for s in (a, b)}})
    quotable = [s for s in ordered if s["quotable_as_rate"]]
    pairs = []
    for a, b in zip(quotable, quotable[1:]):
        if era(a["version"]) != era(b["version"]):
            continue
        gap = abs((b["rate"] or 0) - (a["rate"] or 0))
        disjoint = a["hi"] < b["lo"] or b["hi"] < a["lo"]
        if not disjoint:
            verdict = "no signal: intervals overlap"
        elif gap > GAP_PP:
            verdict = f"FAIL: gap {gap * 100:.0f}pp > {GAP_PP * 100:.0f}pp"
        else:
            verdict = f"separated, below the {GAP_PP * 100:.0f}pp bar"
        pairs.append({"a": a["version"], "b": b["version"],
                      "gap_pp": round(gap * 100, 1),
                      "intervals_disjoint": disjoint, "verdict": verdict})

    return {
        "files": raw["files"],
        "totals": {"n": total_n, "diagnosed": total_k,
                   "rate": round(total_k / total_n, 4) if total_n else None},
        "min_n_for_quoting": MIN_N,
        "gap_threshold_pp": GAP_PP * 100,
        "strata": strata,
        "adjacent_pairs": pairs,
        "skipped_for_low_n": skipped,
        "failures": [p for p in pairs if p["verdict"].startswith("FAIL")],
        "shape_bias": [
            {"version": s["version"], "n": s["n"],
             "dominant_shape": s["dominant_shape"],
             "dominant_shape_share": s["dominant_shape_share"]}
            for s in strata],
    }


def render_md(res: dict) -> str:
    t = res["totals"]
    lines = [
        "# Diagnosis rate by Minecraft version",
        "",
        f"Generated by `tools/version_strata.py` over {res['files']} reports. "
        f"Overall {t['diagnosed']}/{t['n']} = {t['rate'] * 100:.1f}%.",
        "",
        f"A stratum is quotable as a rate at n >= {res['min_n_for_quoting']}; "
        "below that the Wilson interval is too wide to publish a number, so the "
        f"interval is shown and the rate is not. The roadmap failure criterion is "
        f"an adjacent-version gap above {res['gap_threshold_pp']:.0f}pp **with "
        "disjoint intervals** -- a gap between overlapping intervals is noise.",
        "",
        "Three things about this corpus shape the table:",
        "",
        "1. `(no version line)` is a *shape* stratum, not a release: Bedrock logs "
        "and issue bodies that are not crash reports have no `Minecraft Version:` "
        "line. It is reported and never chained into the adjacency test.",
        "2. `26.1`/`26.2`/`26.3` are real -- Minecraft moved off `1.x` "
        "(`Minecraft Version: 26.1.2 (Tiny Takeover)`). An analysis filtering on "
        "a `1.` prefix drops 22 reports without saying so.",
        "3. `(unparsed) 19w34a` is a snapshot id. Snapshots are listed verbatim "
        "and not merged into a release stratum; they are not releases.",
        "",
        "| version | n | share | diagnosed | rate | 95% CI | quotable | dominant shape |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in res["strata"]:
        rate = f"{s['rate'] * 100:.0f}%" if s["rate"] is not None else "--"
        ci = f"{s['lo'] * 100:.0f}-{s['hi'] * 100:.0f}%"
        q = "yes" if s["quotable_as_rate"] else "no"
        shape = (f"{s['dominant_shape']} "
                 f"({s['dominant_shape_share'] * 100:.0f}%)")
        lines.append(f"| `{s['version']}` | {s['n']} | {s['share'] * 100:.1f}% | "
                     f"{s['diagnosed']} | {rate} | {ci} | {q} | {shape} |")
    lines += ["", "## Adjacent pairs (quotable strata, same era only)", "",
              "| a | b | gap | intervals | verdict |", "|---|---|---|---|---|"]
    for p in res["adjacent_pairs"]:
        lines.append(f"| `{p['a']}` | `{p['b']}` | {p['gap_pp']}pp | "
                     f"{'disjoint' if p['intervals_disjoint'] else 'overlapping'} | "
                     f"{p['verdict']} |")
    if not res["adjacent_pairs"]:
        lines.append("| -- | -- | -- | -- | no two strata reach n >= "
                     f"{res['min_n_for_quoting']} in the same era |")
    if res["skipped_for_low_n"]:
        lines += ["", "### Not compared (one side under "
                  f"n = {res['min_n_for_quoting']})", "",
                  "Listed so the chain above is not read as complete: the pair "
                  "`1.16` vs `1.19` skips 1.17 and 1.18 entirely.", "",
                  "| a | b | n (a, b) | under-min side |", "|---|---|---|---|"]
        for s in res["skipped_for_low_n"]:
            ns = ", ".join(f"{k} = {v}" for k, v in s["n"].items())
            lines.append(f"| `{s['a']}` | `{s['b']}` | {ns} | "
                         f"{', '.join(s['under_min_n'])} |")
    lines += ["", "## Verdict", ""]
    if res["failures"]:
        for f in res["failures"]:
            lines.append(f"- **{f['a']} vs {f['b']}**: {f['verdict']}")
    else:
        lines.append("- No adjacent pair of quotable strata shows a gap above "
                     f"{res['gap_threshold_pp']:.0f}pp with disjoint intervals. "
                     "The version-shaped blind spot is not visible in this corpus "
                     "-- which is a statement about the corpus, not a guarantee.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if corpus/VERSION_STRATA.md is stale")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    res = analyse(collect())
    md = render_md(res)
    if args.check:
        try:
            current = open(OUT_MD, encoding="utf-8").read()
        except FileNotFoundError:
            print("corpus/VERSION_STRATA.md missing -- run without --check",
                  file=sys.stderr)
            return 1
        if current != md:
            print("version strata report is stale -- re-run "
                  "python tools/version_strata.py", file=sys.stderr)
            return 1
        print("version strata report is current")
        return 0

    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if not args.quiet:
        t = res["totals"]
        print(f"{res['files']} reports, overall {t['diagnosed']}/{t['n']} = "
              f"{t['rate'] * 100:.1f}%")
        for s in res["strata"]:
            if s["n"] >= 10:
                print(f"  {s['version']:20s} n={s['n']:3d} "
                      f"{s['rate'] * 100:5.1f}% "
                      f"[{s['lo'] * 100:.0f}-{s['hi'] * 100:.0f}%] "
                      f"{'' if s['quotable_as_rate'] else '(not quotable)'}")
        print(f"adjacent pairs checked: {len(res['adjacent_pairs'])}, "
              f"failures: {len(res['failures'])}")
        for p in res["adjacent_pairs"]:
            print(f"  {p['a']} vs {p['b']}: {p['gap_pp']}pp -- {p['verdict']}")
    print(f"wrote {os.path.relpath(OUT_MD, ROOT)} and "
          f"{os.path.relpath(OUT_JSON, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
