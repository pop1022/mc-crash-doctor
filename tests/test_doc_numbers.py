"""Docs quote numbers; the numbers live in `corpus/*.json`. Keep them married.

Ten pieces of drift accumulated before this file existed: ROADMAP cited a
stale 45.8% match rate while the same file's own later section said 50.8%;
README advertised two features as `[~]` in progress months after they shipped;
HANDOFF still described the web UI as "skeleton written, unverified" and the
suite as 445 tests. Nobody noticed because prose is not compiled.

Each check below recomputes the number from its JSON source and asserts the doc
still contains it. When a metric moves, both the number and its count fail
together, which forces the doc edit in the same commit instead of a quarter
later. It cannot catch a wrong sentence -- only a stale number -- which is the
failure mode that actually happened here.

    pytest tests/test_doc_numbers.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _json(rel: str) -> dict:
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} missing -- regenerate with its tools/ script")
    return json.loads(p.read_text(encoding="utf-8"))


def _doc(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} missing")
    return p.read_text(encoding="utf-8")


def _missing(doc: str, needles: list[str]) -> list[str]:
    text = _doc(doc)
    return [n for n in needles if n not in text]


# --- corpus/coverage.json ---------------------------------------------------
def test_coverage_numbers_in_docs():
    c = _json("corpus/coverage.json")["totals"]
    rate = f"{c['rate']:.1%}"
    counts = f"{c['diagnosed']}/{c['n']}"
    uncovered = str(c["uncovered"])
    for doc in ("ROADMAP.md", "corpus/COVERAGE.md", "docs/AUDIT-2026-10-27.md"):
        miss = _missing(doc, [rate, counts])
        assert not miss, f"{doc} does not cite {miss} (coverage.json says {rate}, {counts})"
        _missing(doc, [])  # keep the helper honest about its contract
    # the uncovered count is quoted as a bare number in several places; require
    # it next to the word that makes it meaningful
    assert f"未覆盖 {uncovered}" in _doc("ROADMAP.md"), (
        f"ROADMAP says something other than '未覆盖 {uncovered}'")


# --- corpus/blind-eval.json -------------------------------------------------
def test_blind_eval_numbers_in_docs():
    b = _json("corpus/blind-eval.json")
    blind = b["blind"]
    mod = blind["mod_repo"]
    loader = blind["loader_repo"]
    needles = [
        f"{blind['diagnosed']}/{blind['n']} ({blind['diagnosed'] / blind['n']:.0%})",
        f"{mod['diag']}/{mod['n']} ({mod['diag'] / mod['n']:.0%})",
        f"{loader['diag']}/{loader['n']} ({loader['diag'] / loader['n']:.0%})",
    ]
    miss = _missing("corpus/BLIND_EVAL.md", needles)
    assert not miss, f"corpus/BLIND_EVAL.md does not cite {miss}"
    # and the CI the table prints must be the Wilson interval in the JSON
    ci = b["ci95"]["diagnosed"]
    assert f"[{ci['lo']:.0%}, {ci['hi']:.0%}]" in _doc("corpus/BLIND_EVAL.md"), (
        "the diagnosed CI in BLIND_EVAL.md is not the one blind_eval.json computed")


# --- corpus/version-strata.json --------------------------------------------
def test_version_strata_numbers_in_doc():
    v = _json("corpus/version-strata.json")
    t = v["totals"]
    needle = f"{t['diagnosed']}/{t['n']} = {t['rate']:.1%}"
    assert needle in _doc("corpus/VERSION_STRATA.md"), (
        f"VERSION_STRATA.md should say {needle}")


# --- corpus/rule-candidates.json -------------------------------------------
def test_rule_candidate_numbers_in_doc():
    s = _json("corpus/rule-candidates.json")["summary"]
    needles = [
        f"未覆盖 **{s['uncovered']}** 份",
        f"签名聚类 {s['clusters']} 个",
        f"{s['reports_per_rule']:.2f} 份",
        f"**{s['singletons']}** 个聚类只有 1 份",
        f"{s['top_n_share']:.0%}",
    ]
    miss = _missing("corpus/RULE_CANDIDATES.md", needles)
    assert not miss, f"corpus/RULE_CANDIDATES.md does not cite {miss}"


# --- corpus/coverage-granularity.json (this round's decision) --------------
def test_granularity_numbers_in_decision_doc():
    d = _json("corpus/coverage-granularity.json")
    sig = d["granularities"]["signature (shipped)"]
    tmpl = d["granularities"]["kind+template"]
    needles = [
        f"{d['uncovered']}",
        f"{sig['per_rule']:.2f}",
        f"{tmpl['per_rule']:.2f} 份/规则",
        f"{tmpl['clusters']} 簇 / {tmpl['singletons']} 单例",
    ]
    miss = _missing("docs/DECISION-coverage.md", needles)
    assert not miss, f"docs/DECISION-coverage.md does not cite {miss}"

    # The decision turned on these. Three were implemented on 2026-10-27, so the
    # invariant flipped: a shipped candidate must now have nothing left to gain,
    # and its rule must exist. If a rule is deleted, the rule-id lookup fails and
    # the gain reappears -- both make this test red.
    from mcd.rules.engine import RuleSet

    ids = set(RuleSet.load().ids())
    shipped = {"game-provider": "loader.game-provider-missing",
               "class-already-loaded": "mixin.class-already-loaded",
               "quilt-coerce": "quilt.version-constraint-unreadable"}
    for cand, rule_id in shipped.items():
        row = d["candidates"][cand]
        assert rule_id in ids, f"{cand}: rule {rule_id} is not in the shipped pack"
        assert len(row["gain"]) == 0, (
            f"{cand}: {len(row['gain'])} reports are still undiagnosed -- the rule "
            f"stopped covering them")
    # not written on purpose: 30 collisions buys 6 reports
    row = d["candidates"]["missing-class"]
    assert len(row["gain"]) == 6 and len(row["collision"]) == 30, (
        "missing-class changed; re-read why it was rejected before touching this")
    assert sum(1 for c in d["writable_clusters"]
               if c["descriptions"] == 1) >= 1


# --- corpus/rule-lifecycle.json --------------------------------------------
def test_rule_count_in_docs():
    """Adding a rule changes two numbers every summary quotes. AUDIT is the
    snapshot a successor reads first, so it must not say 41 when the packs hold
    44 -- that is the same class of drift as the stale match rate."""
    lc = _json("corpus/rule-lifecycle.json")
    rules = lc["rules"]
    total = len(rules)
    verified = sum(1 for v in rules.values()
                   if v.get("lifecycle_status") == "verified")
    miss = _missing("docs/AUDIT-2026-10-27.md",
                    [f"{total} 条规则", f"{verified} verified"])
    assert not miss, (
        f"docs/AUDIT-2026-10-27.md does not cite {miss} "
        f"(rule-lifecycle.json: {total} rules, {verified} verified)")


# --- the drift that started this file --------------------------------------
def test_roadmap_does_not_cite_the_stale_match_rate():
    """ROADMAP's 1D.0 section legitimately narrates 45.8% -- that was the
    measurement before 1D.2b. What it must not do is quote 45.8% as the current
    number in the phase-2 section, which is where the drift lived: 2.1 said
    "当前 45.8%" while 1D.2b three hundred lines earlier said 50.8%."""
    text = _doc("ROADMAP.md")
    idx = text.find("## 阶段 2")
    assert idx > 0, "ROADMAP lost its phase-2 heading"
    stale = [ln for ln in text[idx:].splitlines() if "当前 45.8%" in ln]
    assert not stale, f"phase 2 quotes the pre-1D.2b rate as current: {stale}"
