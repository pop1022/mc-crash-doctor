"""Rule metadata contract (ROADMAP 1A.3): every builtin rule carries
provenance and a valid lifecycle_status; the loader rejects bad metadata.

    pytest tests/test_rule_metadata.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.rules.engine import LIFECYCLE_STATES, Rule, RuleSet  # noqa: E402

_rs = RuleSet.load()


def test_every_rule_has_provenance_fixtures():
    """A rule with no proof is untestable dead weight -- the 0.3 cleanup
    established every rule must point at a real report or a synthetic
    fixture."""
    missing = [r.id for r in _rs.rules
               if not (r.provenance or {}).get("fixtures")]
    assert not missing, f"rules without provenance.fixtures: {missing}"


def test_lifecycle_states_are_valid():
    bad = [(r.id, r.lifecycle_status) for r in _rs.rules
           if r.lifecycle_status not in LIFECYCLE_STATES]
    assert not bad, f"invalid lifecycle_status: {bad}"


def test_verified_rules_cite_real_evidence():
    """'verified' must mean real-world evidence (a harvested pin, ground
    truth, or an aternos hit) -- synthetic-only rules stay 'experimental'
    until a real report fires them."""
    for r in _rs.rules:
        if r.lifecycle_status != "verified":
            continue
        fxs = (r.provenance or {}).get("fixtures", [])
        real = [f for f in fxs
                if not str(f).startswith("synthetic/")]
        assert real, f"{r.id}: verified but only synthetic fixtures"


def test_experimental_rules_are_the_synthetic_only_four():
    """Pinned set: the four rules whose failure modes are absent from all
    real corpora (see tests/test_rule_fixtures.py). If a real report starts
    firing one, re-run tools/stamp_provenance.py to upgrade it -- and update
    this test, deliberately."""
    exp = {r.id for r in _rs.rules if r.lifecycle_status == "experimental"}
    assert exp == {"oom.save-time", "oom.gc-overhead", "disk.space",
                   "native.gl"}, f"experimental set changed: {sorted(exp)}"


def test_expect_suspects_reference_own_fixtures():
    """expect_suspects keys must be fixtures of the same rule, else the pin
    is unenforceable (test_gaps would never look them up)."""
    for r in _rs.rules:
        prov = r.provenance or {}
        fxs = set(prov.get("fixtures", []))
        for k in (prov.get("expect_suspects") or {}):
            assert k in fxs, f"{r.id}: expect_suspects key {k!r} not in fixtures"


def _minimal_rule_dict(**over):
    d = {"id": "test.rule", "title": "t", "when": {"text": ["x"]}}
    d.update(over)
    return d


def test_from_dict_rejects_bad_lifecycle():
    with pytest.raises(ValueError, match="lifecycle_status"):
        Rule.from_dict(_minimal_rule_dict(lifecycle_status="yolo"))


def test_from_dict_rejects_non_mapping_provenance():
    with pytest.raises(ValueError, match="provenance"):
        Rule.from_dict(_minimal_rule_dict(provenance=["not", "a", "dict"]))


def test_from_dict_defaults():
    r = Rule.from_dict(_minimal_rule_dict())
    assert r.lifecycle_status == "verified"   # grandfathered default
    assert r.provenance == {}
