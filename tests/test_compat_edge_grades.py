"""Grading decides what the edge corpus can support; every rule gets a case.

The bar this file defends: co-presence in a crash report is not a relationship.
Pairs stay grade C by construction, a maintainer verdict on a pair row is context
about the subject's own issue (not about the pair), and grade A exists only where
a verdict actually pins the cause.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import grade_compat_edges as G  # noqa: E402


def row(**kw) -> dict:
    base = {"subject": "a", "object": "a", "relation": "suspected",
            "evidence_tier": "inferred", "evidence_count": 1,
            "source_reports": [], "maintainer_verdict": None,
            "sample_evidence": ""}
    base.update(kw)
    return base


# --- one claim at a time ----------------------------------------------------
def test_cause_pinning_verdict_is_grade_a() -> None:
    assert G.grade_claim(row(maintainer_verdict="outdated_version")) == "A"
    assert G.grade_claim(row(maintainer_verdict="bug_in_this_mod")) == "A"


def test_a_verdict_saying_not_this_mod_is_rejected() -> None:
    assert G.grade_claim(row(maintainer_verdict="root_cause_elsewhere")) == "rejected"
    assert G.grade_claim(row(maintainer_verdict="user_error_or_config")) == "rejected"


def test_known_issue_alone_is_not_cause_pinning() -> None:
    # Matches build_compat_edges.CAUSE_PINNING_VERDICTS: "known issue" says the
    # report is real, not that this mod is the cause.
    assert G.grade_claim(row(maintainer_verdict="known_issue")) == "C"


def test_specific_evidence_is_grade_b() -> None:
    assert G.grade_claim(row(sample_evidence="stack frame #4: a.b.C.d")) == "B"


def test_the_games_suspect_list_is_not_evidence() -> None:
    for text in ("game 'Suspected Mods' (first listed)",
                 "named in the crash description/message"):
        assert G.grade_claim(row(sample_evidence=text)) == "C"


def test_cooccurrence_relation_cannot_be_grade_b() -> None:
    assert G.grade_claim(row(relation="co_occurred",
                             sample_evidence="stack frame #4: a.b.C.d")) == "C"


# --- the datasets -----------------------------------------------------------
def test_a_pair_is_always_grade_c_even_with_a_verdict() -> None:
    out, stats = G.build([row(subject="a", object="b", relation="co_occurred",
                              maintainer_verdict="outdated_version")])
    pair = next(r for r in out if r["scope"] == "pair")
    assert pair["grade"] == "C"
    assert pair["verdict_context"] == ["outdated_version"]
    assert stats["pair_grades"] == {"A": 0, "B": 0, "C": 1}


def test_reversed_pairs_merge() -> None:
    out, stats = G.build([
        row(subject="a", object="b", relation="co_occurred"),
        row(subject="b", object="a", relation="co_occurred"),
    ])
    assert stats["pairs"] == 1
    assert (out[0]["subject"], out[0]["object"]) == ("a", "b")


def test_duplicates_count_distinct_reports_not_rows() -> None:
    same = [{"repo": "r/x", "issue": 1, "url": "u1"},
            {"repo": "r/x", "issue": 2, "url": "u2"}]
    out, _ = G.build([row(subject="a", object="b", evidence_count=13,
                          source_reports=same)] * 2)
    assert out[0]["evidence_count"] == 2


def test_the_best_claim_grade_wins_for_a_mod() -> None:
    out, _ = G.build([
        row(sample_evidence="game 'Suspected Mods'"),
        row(maintainer_verdict="outdated_version"),
    ])
    mod = next(r for r in out if r["scope"] == "mod")
    assert mod["grade"] == "A"
    assert mod["verdicts"] == ["outdated_version"]


def test_rows_without_both_sides_are_skipped() -> None:
    out, _ = G.build([row(subject=""), row(object="")])
    assert out == []


def test_summary_is_json_serialisable_and_states_the_limit() -> None:
    _, stats = G.build([row()])
    json.dumps(stats)
    assert "co-occurrence only" in stats["note"]


# --- the committed corpus, as it stands --------------------------------------
def test_every_pair_in_the_corpus_is_cooccurrence_only() -> None:
    """Pin the shape: if a future derivation starts producing causal pairs,
    this fails on purpose, so the graph's promise is re-examined rather than
    silently upgraded."""
    src = ROOT / "corpus" / "compat-edges.jsonl"
    if not src.is_file():
        pytest.skip("corpus absent")
    rows = [json.loads(line) for line in
            src.read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs = [r for r in rows if str(r.get("subject")) != str(r.get("object"))]
    assert pairs, "corpus has no pairs at all"
    assert {r.get("relation") for r in pairs} == {"co_occurred"}


def test_committed_summary_matches_a_fresh_computation() -> None:
    """The committed summary is a published number; it must be recomputable."""
    src = ROOT / "corpus" / "compat-edges.jsonl"
    summary_path = ROOT / "corpus" / "compat-edge-grades.json"
    if not src.is_file() or not summary_path.is_file():
        pytest.skip("corpus or summary absent")
    committed = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in
            src.read_text(encoding="utf-8").splitlines() if line.strip()]
    _, stats = G.build(rows)
    assert committed["pairs"] == stats["pairs"], "pair count drifted"
    for key, value in stats.items():
        if key in committed:
            assert committed[key] == value, f"{key} drifted"
