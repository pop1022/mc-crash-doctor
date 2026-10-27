"""Is the uncovered tail exhausted, or is that a clustering artefact?

`corpus/RULE_CANDIDATES.md` clusters the 117 uncovered reports by **full
exception signature** and concludes: 1.09 reports per rule, 85% singletons,
R4 fires, stop writing rules. That number is a property of the clustering key,
not necessarily of the corpus -- the shipped table splits

    ArrayIndexOutOfBoundsException -> "-1", "4", "Index 4 out of bounds"
    ClassNotFoundException         -> five separate singletons

which one `exception:`-keyed rule could in principle cover together. So this
tool re-clusters the same 117 reports at five granularities and prints the
economics of each, then applies the quality test the raw count is missing:

    a cluster buys ONE honest rule only if its members are the same failure
    mode -- same kind, same message shape, one description.

Coarser keys look better and are worse: `kind` alone reaches 60% of the tail
with 10 rules, but those clusters mix six unrelated reports, and a rule for
them could only say something so vague it would be wrong for most of them.

Answer (2026-10-27): the tail IS exhausted. Five clusters are one-rule-shaped,
16 reports in total, five of which are not faults ("Manually triggered debug
crash"). A generic missing-class rule would fire on 30 already-diagnosed
reports, 24 of them already answered by `mod.coremod-missing`.

It also lists the 32 undiagnosed reports in blind-eval's loader-repo stratum
(57.3% vs 78.3% for mod repos), which looked like the better target. It is not:
those 32 are a message-level long tail too -- three families, six reports.

    python tools/coverage_granularity.py            # print
    python tools/coverage_granularity.py --json     # also write the artifact
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import blind_eval as be  # noqa: E402
import coverage_report as cr  # noqa: E402

from mcd.parser.report import parse_file, read_report_text  # noqa: E402
from mcd.rules.engine import RuleSet, run_rules  # noqa: E402

OUT = ROOT / "corpus" / "coverage-granularity.json"

_TEMPLATE_SUBS = (
    (re.compile(r'"[^"]*"'), "<q>"),              # quoted values
    (re.compile(r"`[^`]*`"), "<q>"),              # backticked values
    (re.compile(r"\[[^\[\]]*\]"), "<b>"),         # bracketed payloads
    (re.compile(r"\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){2,}\b"), "<fqcn>"),
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"]*"), "<path>"),
    (re.compile(r"!?\bhttps?://\S+"), "<url>"),
    (re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)*"), "#"),
    (re.compile(r"\s+"), " "),
)


def template(message: str) -> str:
    """Message shape: what is left after removing per-report values.

    `Cannot invoke "a.b.C.d()" because "x" is null` and
    `Cannot invoke "e.f.G.h()" because "y" is null` are one failure mode and
    one rule can speak to both; `NullPointerException` alone is not a failure
    mode at all. This is the level at which a rule is still honest.
    """
    text = (message or "").strip()
    for rx, repl in _TEMPLATE_SUBS:
        text = rx.sub(repl, text)
    return " ".join(text.split()[:8]) or "(empty message)"


def frame_site(block) -> str:
    """`platform` / `mod` / `no-frames` for an exception block's throw site."""
    frames = getattr(block, "frames", None) or []
    if not frames:
        return "no-frames"
    try:
        return "platform" if cr._is_platform_frame(frames[0]) else "mod"
    except Exception:  # noqa: BLE001
        return "unknown"


def economics(sizes: list[int], total: int) -> dict:
    sizes = sorted(sizes, reverse=True)
    cum, marks = 0, {}
    for i, s in enumerate(sizes, 1):
        cum += s
        for pct in (25, 50, 75):
            if pct not in marks and cum >= total * pct / 100:
                marks[pct] = i
    return {
        "clusters": len(sizes),
        "singletons": sum(1 for s in sizes if s == 1),
        "top1": sizes[0] if sizes else 0,
        "top5": sum(sizes[:5]),
        "top10": sum(sizes[:10]),
        "top10_share": (sum(sizes[:10]) / total) if total else 0.0,
        "per_rule": (total / len(sizes)) if sizes else 0.0,
        "rules_to_25pct": marks.get(25),
        "rules_to_50pct": marks.get(50),
    }


#: Candidate rules, as predicates over a report's exception signatures.
#: `gain` = currently-undiagnosed reports it would diagnose;
#: `collision` = already-diagnosed reports it would ALSO fire on, i.e. a second
#: finding that competes with an existing rule instead of adding coverage.
CANDIDATES: list[tuple[str, str, object]] = [
    ("missing-class",
     "a class a mod needs is absent -> wrong MC/loader build, or a missing "
     "dependency jar",
     lambda s: any(x.startswith("java.lang.ClassNotFoundException") for x in s)),
    ("game-provider",
     "the launcher pointed the loader at a game directory it cannot read",
     lambda s: any("game provider couldn't locate the game" in x for x in s)),
    ("class-already-loaded",
     "two jars ship the same mixin target class -> duplicate or renamed jar",
     lambda s: any("ClassAlreadyLoadedException" in x for x in s)),
    ("quilt-coerce",
     "Quilt could not parse a loader version constraint in a mod's metadata",
     lambda s: any("Cannot coerce loader value to a String" in x for x in s)),
    ("debug-crash",
     "a human pressed the debug-crash key -- not a fault; kept to show what the "
     "shipped draft actually buys",
     lambda s: any("Manually triggered debug crash" in x for x in s)),
]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    files = sorted((ROOT / "corpus" / "github").rglob("*.crash.txt"))
    ruleset = RuleSet.load()

    uncovered: list[dict] = []
    candidate_rows = {label: {"gain": [], "collision": []}
                      for label, _why, _p in CANDIDATES}
    for path in files:
        try:
            rep = parse_file(path)
        except Exception:  # noqa: BLE001 - one bad fragment must not stop this
            continue
        found = run_rules(rep, ruleset)
        sigs = [b.signature for b in rep.exceptions]
        rel = f"{path.parent.name}/{path.name.replace('.crash.txt', '')}"
        for label, _why, pred in CANDIDATES:
            try:
                hit = bool(pred(sigs))
            except Exception:  # noqa: BLE001
                hit = False
            if hit:
                bucket = "collision" if found else "gain"
                candidate_rows[label][bucket].append(rel)
        if found:
            continue
        block = rep.exceptions[-1] if rep.exceptions else None
        sig = sigs[0] if sigs else "no exception block"
        uncovered.append({
            "report": rel,
            "signature": sig,
            "kind": (block.kind if block else "") or "(no exception)",
            "message": sig.split(":", 1)[1].strip() if ":" in sig else "",
            "description": rep.description or "",
            "bucket": cr.classify(read_report_text(path), rep),
            "site": frame_site(block),
        })

    total = len(uncovered)
    print(f"corpus {len(files)} | uncovered {total}\n")

    def key(rec: dict, gran: str) -> str:
        kind = rec["kind"]
        if gran == "signature (shipped)":
            return rec["signature"]
        if gran == "kind":
            return kind
        if gran == "kind+bucket":
            return f"{kind} | {rec['bucket']}"
        if gran == "kind+bucket+site":
            return f"{kind} | {rec['bucket']} | {rec['site']}"
        return f"{kind} | {template(rec['message'])}"

    grans = ("signature (shipped)", "kind", "kind+bucket", "kind+bucket+site",
             "kind+template")
    groups: dict[str, dict[str, list[str]]] = {}
    result: dict[str, dict] = {}
    for gran in grans:
        g: dict[str, list[str]] = defaultdict(list)
        for rec in uncovered:
            g[key(rec, gran)].append(rec["report"])
        groups[gran] = dict(g)
        result[gran] = economics([len(v) for v in g.values()], total)

    print(f"{'granularity':22s} {'clusters':>8s} {'single':>6s} {'top10%':>7s} "
          f"{'per-rule':>8s} {'->25%':>6s} {'->50%':>6s}")
    for gran in grans:
        r = result[gran]
        print(f"{gran:22s} {r['clusters']:8d} {r['singletons']:6d} "
              f"{r['top10_share']:6.1%} {r['per_rule']:8.2f} "
              f"{str(r['rules_to_25pct']):>6s} {str(r['rules_to_50pct']):>6s}")

    by_report = {r["report"]: r for r in uncovered}
    writable = []
    for gran_key, members in sorted(groups["kind+template"].items(),
                                    key=lambda kv: -len(kv[1])):
        if len(members) < 2:
            continue
        descs = {by_report[m]["description"] for m in members}
        writable.append({"key": gran_key, "size": len(members),
                         "descriptions": len(descs), "members": members})
    cover = sum(w["size"] for w in writable)
    print(f"\nkind+template 簇里 size>=2 的：{len(writable)} 个 / {cover} 份 "
          f"({cover / total:.1%})")
    for w in writable:
        print(f"  [{w['size']} 份 / {w['descriptions']} 种描述] {w['key'][:80]}")

    print(f"\n{'candidate':22s} {'gain':>5s} {'collision':>10s}")
    for label, _why, _p in CANDIDATES:
        row = candidate_rows[label]
        print(f"{label:22s} {len(row['gain']):5d} {len(row['collision']):10d}")

    # loader-repo stratum in blind-eval's split
    _dev, blind = be.split_corpus()
    loader_files = [f for f in blind
                    if Path(f).parent.name.split("__")[-1] in be.LOADER_REPOS]
    loader_undiag = []
    for f in loader_files:
        try:
            rep = parse_file(f)
        except Exception:  # noqa: BLE001
            continue
        if run_rules(rep, ruleset):
            continue
        block = rep.exceptions[-1] if rep.exceptions else None
        sig = block.signature if block else ""
        loader_undiag.append({
            "file": str(Path(f).relative_to(ROOT)).replace("\\", "/"),
            "repo": Path(f).parent.name,
            "kind": (block.kind if block else "") or "(no exception)",
            "message": sig.split(":", 1)[1].strip() if ":" in sig else "",
            "bucket": cr.classify(read_report_text(f), rep),
            "description": rep.description or "",
            "site": frame_site(block) if block else "no-frames",
        })
    fams: dict[str, list[str]] = defaultdict(list)
    for u in loader_undiag:
        fams[f"{u['kind']} | {template(u['message'])}"].append(u["file"])
    fam_big = {k: v for k, v in fams.items() if len(v) >= 2}
    print(f"\nloader-repo: blind {len(blind)} -> loader-repo {len(loader_files)} "
          f"| undiagnosed {len(loader_undiag)} | families(size>=2) {len(fam_big)} "
          f"covering {sum(len(v) for v in fam_big.values())}")

    if "--json" in argv:
        OUT.write_text(json.dumps({
            "corpus": len(files),
            "uncovered": total,
            "granularities": result,
            "writable_clusters": writable,
            "candidates": {
                label: {"why": why,
                        "gain": candidate_rows[label]["gain"],
                        "collision": candidate_rows[label]["collision"]}
                for label, why, _p in CANDIDATES},
            "loader_stratum": {
                "blind_files": len(blind),
                "files": len(loader_files),
                "undiagnosed": len(loader_undiag),
                "families": fam_big,
                "rows": loader_undiag,
                "kind_histogram": dict(Counter(u["kind"]
                                               for u in loader_undiag)),
            },
        }, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        print(f"json -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
