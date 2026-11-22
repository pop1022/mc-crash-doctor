#!/usr/bin/env python
"""Separate what the edge corpus can support from what it cannot.

THE MEASUREMENT THIS TOOL EXISTS TO MAKE
  corpus/compat-edges.jsonl is often described as "9,895 compatibility edges".
  It is not. Measured on 2026-11-17:

    9,721 rows are pairs and every one of them is relation=co_occurred, i.e. two
          mod ids appeared in reports from the same repository. No row says one
          caused the other. A maintainer verdict sitting on such a row is a
          verdict about the *subject's own* issue, not about the pair.
      174 rows are self-loops (subject == object), and those are the only rows
          that make a causal claim ("this mod was suspected / caused it").

  So the honest shape is two datasets, not one:

    pairs       a co-occurrence graph. Usable for "these two are mentioned
                together", never for "these two conflict".
    mod claims  per-mod statements with a maintainer verdict. This is where
                grade A actually lives (outdated_version / bug_in_this_mod).

  The tool merges duplicates, counts distinct source reports instead of rows
  (one pair appears 14 times and is still one pair), and writes both sets with
  the grade attached. It reuses derive_evidence_tier() from
  build_compat_edges.py rather than restating the promotion rule here.

GRADES (for mod claims; pairs are always C by construction)
  A  a cause-pinning maintainer verdict: outdated_version, bug_in_this_mod.
  B  relation is suspected/caused and the report text carries specific
     evidence (a stack frame, an exception message, a named mixin config).
     The game's own "Suspected Mods" list does not count.
  C  neither. Kept and counted, never presented as a finding.
  rejected  the verdict says the mod was not at fault (root_cause_elsewhere,
     not_a_bug, user_error_or_config, meta).

    python tools/grade_compat_edges.py --summary corpus/compat-edge-grades.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_compat_edges import CAUSE_PINNING_VERDICTS  # noqa: E402

INPUT = ROOT / "corpus" / "compat-edges.jsonl"
GRADED = ROOT / "corpus" / "compat-edges.graded.jsonl"

#: Verdicts that say "the mod was not the cause" (or that the report was not
#: about a bug at all). These invert a claim, so they cannot share a bucket with
#: a cause-pinning verdict.
_REJECT = {"root_cause_elsewhere", "not_a_bug", "user_error_or_config", "meta"}

#: Evidence strings that only repeat the game's own guess -- the reporter
#: verified nothing, so the row cannot be grade B however it is tiered.
_GENERIC = ("game 'suspected mods'", "named in the crash description")


def _specific(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(t) and not any(t.startswith(g) for g in _GENERIC)


def grade_claim(row: dict) -> str:
    """Grade one self-loop row: the only kind that makes a causal claim."""
    verdict = (row.get("maintainer_verdict") or "").strip()
    if verdict in _REJECT:
        return "rejected"
    if verdict in CAUSE_PINNING_VERDICTS:
        return "A"
    if (row.get("relation") in ("suspected", "caused")
            and _specific(row.get("sample_evidence", ""))):
        return "B"
    return "C"


def _sources(row: dict) -> list[dict]:
    return [s for s in (row.get("source_reports") or [])
            if isinstance(s, dict) and s.get("url")]


_RANK = {"rejected": 0, "C": 1, "B": 2, "A": 3}


def build(rows: list[dict]) -> tuple[list[dict], dict]:
    """Merge and grade. Returns (graded rows, stats)."""
    pairs: dict[tuple[str, str], dict] = {}
    mods: dict[str, dict] = {}

    for row in rows:
        subject = str(row.get("subject") or "").strip()
        obj = str(row.get("object") or "").strip()
        if not subject or not obj:
            continue
        verdict = (row.get("maintainer_verdict") or "").strip() or None
        srcs = {(s.get("repo"), s.get("issue")): s for s in _sources(row)}

        if subject == obj:
            cur = mods.setdefault(subject, {
                "scope": "mod", "modid": subject, "grade": grade_claim(row),
                "relations": set(), "verdicts": set(), "loaders": set(),
                "mc_versions": set(), "sources": {}, "max_evidence": 0,
            })
            if _RANK[grade_claim(row)] > _RANK[cur["grade"]]:
                cur["grade"] = grade_claim(row)
            cur["relations"].add(str(row.get("relation") or "suspected"))
            if verdict:
                cur["verdicts"].add(verdict)
            if row.get("loader"):
                cur["loaders"].add(row["loader"])
            if row.get("mc_version"):
                cur["mc_versions"].add(row["mc_version"])
            for k, v in srcs.items():
                cur["sources"].setdefault(k, v)
            cur["max_evidence"] = max(cur["max_evidence"], int(row.get("evidence_count") or 0))
            continue

        # A pair is undirected for co-occurrence: (a,b) and (b,a) are one edge,
        # otherwise the graph counts the same coincidence twice.
        a, b = sorted((subject, obj))
        cur = pairs.setdefault((a, b), {
            "scope": "pair", "subject": a, "object": b, "grade": "C",
            "verdict_context": set(), "loaders": set(), "mc_versions": set(),
            "sources": {}, "max_evidence": 0,
        })
        if verdict:
            # Context only: the verdict speaks about the subject's own issue,
            # not about the pair. It is recorded so a reader can see why a
            # co-presence row exists, and it never upgrades the grade.
            cur["verdict_context"].add(verdict)
        if row.get("loader"):
            cur["loaders"].add(row["loader"])
        if row.get("mc_version"):
            cur["mc_versions"].add(row["mc_version"])
        for k, v in srcs.items():
            cur["sources"].setdefault(k, v)
        cur["max_evidence"] = max(cur["max_evidence"], int(row.get("evidence_count") or 0))

    out: list[dict] = []
    for key in sorted(pairs):
        p = pairs[key]
        n = len(p["sources"])
        out.append({
            "scope": "pair", "subject": p["subject"], "object": p["object"],
            "grade": "C",
            "evidence_count": n or p["max_evidence"],
            "verdict_context": sorted(p["verdict_context"]),
            "loaders": sorted(p["loaders"]), "mc_versions": sorted(p["mc_versions"]),
            "sources": [p["sources"][k] for k in sorted(p["sources"], key=str)][:3],
        })
    for modid in sorted(mods):
        m = mods[modid]
        n = len(m["sources"])
        out.append({
            "scope": "mod", "modid": modid, "grade": m["grade"],
            "relations": sorted(m["relations"]), "verdicts": sorted(m["verdicts"]),
            "evidence_count": n or m["max_evidence"],
            "loaders": sorted(m["loaders"]), "mc_versions": sorted(m["mc_versions"]),
            "sources": [m["sources"][k] for k in sorted(m["sources"], key=str)][:5],
        })

    pair_rows = [r for r in out if r["scope"] == "pair"]
    mod_rows = [r for r in out if r["scope"] == "mod"]
    pair_grades = Counter(r["grade"] for r in pair_rows)
    mod_grades = Counter(r["grade"] for r in mod_rows)
    stats = {
        "raw_rows": len(rows),
        "pair_rows_raw": sum(1 for r in rows if str(r.get("subject")) != str(r.get("object"))),
        "mod_rows_raw": sum(1 for r in rows if str(r.get("subject")) == str(r.get("object"))),
        "pairs": len(pair_rows),
        "mods": len(mod_rows),
        "duplicates_merged": len(rows) - len(out),
        "pair_grades": {g: pair_grades.get(g, 0) for g in ("A", "B", "C")},
        "mod_grades": {g: mod_grades.get(g, 0) for g in ("A", "B", "C", "rejected")},
        "note": ("Pairs are co-occurrence only -- no row in the source corpus ties "
                 "two different mods causally. Grade A lives exclusively in the "
                 "per-mod claims (outdated_version / bug_in_this_mod)."),
    }
    return out, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(INPUT))
    ap.add_argument("--out", default=str(GRADED))
    ap.add_argument("--summary", default=None)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.is_file():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in
            src.read_text(encoding="utf-8").splitlines() if line.strip()]
    out, stats = build(rows)

    Path(args.out).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out),
        encoding="utf-8")
    stats = {"generated_by": "tools/grade_compat_edges.py",
             "input": src.name, **stats}

    print(f"{stats['raw_rows']} rows -> {stats['pairs']} pairs "
          f"+ {stats['mods']} mod claims ({stats['duplicates_merged']} merged)")
    pg = stats["pair_grades"]
    print(f"  pairs: A {pg['A']}  B {pg['B']}  C {pg['C']}")
    mg = stats["mod_grades"]
    print(f"  mods : A {mg['A']}  B {mg['B']}  C {mg['C']}  rejected {mg['rejected']}")
    if args.summary:
        Path(args.summary).write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"summary -> {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
