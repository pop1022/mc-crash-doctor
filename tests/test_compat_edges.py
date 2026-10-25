"""Compatibility-edge contract (ROADMAP 1D.3).

Until now `corpus/compat-edges.jsonl` had **no test at all** -- 9,895 rows of
derived data, 9,721 of which are presence-only pairs, with nothing stopping a
downstream consumer from treating co-presence as guilt. That is the defect this
file closes.

What is pinned here:

  1. every row carries a recognised `evidence_tier`, and the tier is exactly
     what the shared derivation rule says it should be (so a hand-edit to the
     committed JSONL fails loudly instead of being laundered);
  2. the tier never contradicts the relation -- a `co_occurred` row can never
     claim to be causal evidence;
  3. `declared` edges are tripwired: there are none today, and adding one
     requires updating the format doc *and* this test deliberately, rather than
     letting author declarations slip in indistinguishable from inference;
  4. the structural facts we rely on (causal edges are self-loops, co-occurrence
     edges are pairs) still hold;
  5. the diagnosis document does not leak edge vocabulary -- if edges ever reach
     operator-facing output, that is a schema change and must be conscious.

    pytest tests/test_compat_edges.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.cli import diagnose                                   # noqa: E402
from mcd.report.render import build_incident                  # noqa: E402

EDGES = ROOT / "corpus" / "compat-edges.jsonl"

_spec = importlib.util.spec_from_file_location(
    "build_compat_edges", ROOT / "tools" / "build_compat_edges.py")
bce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bce)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def edges() -> list[dict]:
    if not EDGES.exists():
        pytest.skip("corpus/compat-edges.jsonl absent (run build_compat_edges.py)")
    rows = [json.loads(line) for line in EDGES.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert rows, "edges file is empty"
    return rows


# --------------------------------------------------------------------------
# the derivation rule itself
# --------------------------------------------------------------------------
def test_derivation_promotes_only_cause_pinning_verdicts():
    """A maintainer saying `not_a_bug` must not strengthen a causal claim."""
    assert bce.derive_evidence_tier("caused", "bug_in_this_mod") == "maintainer_verdict"
    assert bce.derive_evidence_tier("caused", "outdated_version") == "maintainer_verdict"
    for weak in ("not_a_bug", "insufficient_data", "meta", "user_error_or_config", None):
        assert bce.derive_evidence_tier("caused", weak) == "inferred", weak


def test_derivation_never_promotes_cooccurrence():
    """Even a maintainer label cannot make presence-only evidence causal."""
    assert bce.derive_evidence_tier("co_occurred", "bug_in_this_mod") == "cooccurrence"
    assert bce.derive_evidence_tier("co_occurred", None) == "cooccurrence"


def test_derivation_never_invents_declared():
    """`declared` means an author wrote `conflicts`/`breaks`; this tool has
    never read a manifest, so it must be unreachable from report-only input."""
    for relation in ("caused", "suspected", "co_occurred"):
        for verdict in (None, "bug_in_this_mod", "not_a_bug"):
            assert bce.derive_evidence_tier(relation, verdict) != "declared"


def test_derivation_covers_every_relation():
    for relation in ("caused", "suspected", "co_occurred"):
        assert bce.derive_evidence_tier(relation, None) in bce.EVIDENCE_TIERS


# --------------------------------------------------------------------------
# the committed data
# --------------------------------------------------------------------------
def test_every_row_has_a_recognised_tier(edges):
    missing = [i for i, r in enumerate(edges) if r.get("evidence_tier") not in bce.EVIDENCE_TIERS]
    assert not missing, f"{len(missing)} rows lack a valid evidence_tier (first: {missing[:5]})"


def test_tier_matches_the_shared_rule(edges):
    """The committed file must be reproducible from its own fields. A hand-edited
    tier is exactly how 'weak evidence' silently becomes 'strong evidence'."""
    drift = [
        (r.get("subject"), r.get("relation"), r.get("evidence_tier"),
         bce.derive_evidence_tier(r.get("relation") or "", r.get("maintainer_verdict")))
        for r in edges
        if r.get("evidence_tier")
        != bce.derive_evidence_tier(r.get("relation") or "", r.get("maintainer_verdict"))
    ]
    assert not drift, f"{len(drift)} rows disagree with derive_evidence_tier: {drift[:3]}"


def test_cooccurrence_never_claims_causality(edges):
    offenders = [
        r for r in edges
        if r.get("relation") == "co_occurred" and r.get("evidence_tier") != "cooccurrence"
    ]
    assert not offenders, f"{len(offenders)} co_occurred rows claim stronger evidence"


def test_causal_edges_are_not_tiered_as_cooccurrence(edges):
    """Symmetric to the above: a causal claim must not be downgraded to
    presence-only by accident, which would silently discard real signal."""
    offenders = [
        r for r in edges
        if r.get("relation") in ("caused", "suspected")
        and r.get("evidence_tier") == "cooccurrence"
    ]
    assert not offenders, f"{len(offenders)} causal rows tiered as cooccurrence"


def test_declared_edges_are_a_deliberate_add(edges):
    """Tripwire, not a bug. Nothing writes `declared` today.

    When 1D.2 starts importing author declarations, this test WILL fail. That is
    the point: the failure is the reminder to document the new tier's semantics
    in corpus/COMPAT_EDGES.md and to think about how consumers mix it with
    inference. Update this test in the same commit -- do not delete it.
    """
    declared = [r for r in edges if r.get("evidence_tier") == "declared"]
    assert not declared, (
        f"{len(declared)} declared edges appeared. If 1D.2 landed, update "
        "corpus/COMPAT_EDGES.md and this test's expectation together."
    )


def test_causal_edges_are_self_loops_and_cooccurrence_are_pairs(edges):
    """Pins the semantics we documented: `caused`/`suspected` say "this mod is
    at fault" (subject == object, no pairwise claim), while `co_occurred` is the
    only pairwise relation. If causal edges ever become pairwise, the graph's
    meaning changes and every consumer assumption needs revisiting."""
    bad_causal = [
        r for r in edges
        if r.get("relation") in ("caused", "suspected") and r.get("subject") != r.get("object")
    ]
    bad_pair = [
        r for r in edges
        if r.get("relation") == "co_occurred" and r.get("subject") == r.get("object")
    ]
    assert not bad_causal, f"{len(bad_causal)} causal rows are pairwise"
    assert not bad_pair, f"{len(bad_pair)} co-occurrence rows are self-loops"


def test_every_cited_report_still_exists_in_the_index(edges):
    """Provenance: an edge may only cite a report the current corpus still has.

    WHY THIS IS A TEST AND NOT A COMMENT
    ------------------------------------
    These edges are derived data, and derived data silently rots when its input
    changes. After ROADMAP 1D.4 repaired `corpus/index.jsonl` (488 → 454 rows,
    `mod_ids` filled), `corpus/COMPAT_EDGES.md` was edited to warn that this
    file had gone stale and could no longer be reproduced. That was **wrong**:
    a rebuild reproduces the file byte-for-byte, because `co_occurred` is built
    from `rep.mods` (the Mod List re-parsed from each report) and `load_index()`
    collapses duplicate rows into a dict before they are read.

    The real lesson is that a prose warning cannot be checked and a wrong one
    cannot be caught. This assertion can: a re-harvest that renumbers or drops
    issues makes the build unreproducible, and the failure says so.
    """
    index = ROOT / "corpus" / "index.jsonl"
    if not index.exists():
        pytest.skip("corpus/index.jsonl absent")
    known = {
        (rec["repo"].split("/")[-1], str(rec["number"]))
        for rec in (json.loads(line) for line in
                    index.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    cited = {
        (src["repo"].split("/")[-1], str(src["issue"]))
        for row in edges
        for src in row.get("source_reports") or []
    }
    missing = cited - known
    assert not missing, (
        f"{len(missing)} cited reports are no longer in the index, e.g. "
        f"{sorted(missing)[:3]}. The edges file predates a corpus change -- "
        "rebuild it with `python tools/build_compat_edges.py`."
    )


def test_tier_distribution_is_reported_not_assumed(edges):
    """Not a tautology: it fails if the file becomes dominated by a tier we have
    not thought about, which would mean the corpus changed character."""
    counts = Counter(r.get("evidence_tier") for r in edges)
    assert counts["cooccurrence"] > 0
    assert counts["inferred"] > 0
    # maintainer_verdict may legitimately be empty in a small corpus, but if it
    # exists it must be a minority -- labels are rare by construction.
    assert counts["maintainer_verdict"] < counts["inferred"]


# --------------------------------------------------------------------------
# idempotence of the migration
# --------------------------------------------------------------------------
def test_rederive_is_idempotent(tmp_path, edges):
    """Running the migration twice must be a no-op; otherwise `--rederive-tier`
    is unsafe to re-run and nobody will trust the file."""
    copy = tmp_path / "edges.jsonl"
    copy.write_text(EDGES.read_text(encoding="utf-8"), encoding="utf-8")
    assert bce.rederive_tier(str(copy)) == 0
    once = copy.read_text(encoding="utf-8")
    assert bce.rederive_tier(str(copy)) == 0
    assert copy.read_text(encoding="utf-8") == once


def test_rederive_refuses_unknown_relation(tmp_path):
    """A typo'd relation must not be quietly laundered into a tier."""
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"subject": "a", "object": "a", "relation": "causedd"}) + "\n",
                   encoding="utf-8")
    assert bce.rederive_tier(str(bad)) == 1
    assert json.loads(bad.read_text(encoding="utf-8"))["relation"] == "causedd"


# --------------------------------------------------------------------------
# the operator-facing document must not leak edge vocabulary
# --------------------------------------------------------------------------
def test_incident_document_does_not_leak_edge_vocabulary():
    """Edges are corpus assets, not diagnosis output. If co-occurrence ever
    reaches a user, it arrives via a schema change -- not by accident."""
    report = ROOT / "tests" / "fixtures" / "ground-truth"
    fixture = sorted(report.glob("*.txt"))
    if not fixture:
        pytest.skip("ground-truth fixtures absent")
    rep, findings, triage_result = diagnose(str(fixture[0]), None)
    doc = build_incident(rep, findings, triage_result)
    blob = json.dumps(doc, ensure_ascii=False)
    for token in ("co_occurred", "cooccurrence", "evidence_tier", "weak_supervision"):
        assert token not in blob, f"edge vocabulary {token!r} leaked into the Incident"
