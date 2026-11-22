"""The mc_version gate: ranges, prefixes, and the "no version stated" case.

A version gate narrows a rule, so the interesting behaviour is when it must
NOT fire. 30% of the harvested corpus states no Minecraft version at all; a
rule gated on >=1.20 has no business guessing for those reports.
"""
from __future__ import annotations

from pathlib import Path

from mcd.cli import diagnose
from mcd.model import CrashReport
from mcd.rules.engine import (MatchCtx, Rule, RuleSet, _version_ok,
                              evaluate_rule)

GT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ground-truth"


def test_ranges_and_prefixes() -> None:
    assert _version_ok(">=1.20 <1.21", "1.20.1")
    assert not _version_ok(">=1.20 <1.21", "1.21")
    assert not _version_ok(">=1.20 <1.21", "1.19.2")
    assert _version_ok(">=1.20.5", "1.21")
    assert _version_ok("1.20", "1.20.4")          # prefix match
    assert not _version_ok("1.20", "1.201")       # ... but not a longer number
    assert _version_ok("=1.20.1", "1.20.1")
    assert not _version_ok("=1.20.1", "1.20.2")
    assert _version_ok(">=1.16 <=1.16.5", "1.16.5")


def test_no_version_means_no_match() -> None:
    # Never guess: without a stated version the gate cannot be satisfied.
    assert not _version_ok(">=1.20", "")
    assert not _version_ok("1.20", "")


def test_gate_fires_only_inside_the_range() -> None:
    rep = CrashReport(full_text="boom")
    rep.system.minecraft_version = "1.20.1"
    rep.description = "Ticking entity"
    ctx = MatchCtx.build(rep)

    inside = Rule(id="t.in", title="t", when={"description": ["Ticking"], "mc_version": ">=1.20 <1.21"})
    outside = Rule(id="t.out", title="t", when={"description": ["Ticking"], "mc_version": ">=1.21"})
    assert evaluate_rule(inside, ctx) is not None
    assert evaluate_rule(outside, ctx) is None

    rep.system.minecraft_version = ""
    assert evaluate_rule(inside, ctx) is None


def test_shipped_rules_still_load_with_the_new_key() -> None:
    # The key is in WHEN_KEYS, so the loader must not warn about it.
    rs = RuleSet.load()
    assert not [e for e in rs.errors if "mc_version" in e]


def test_a_gated_rule_can_fire_end_to_end() -> None:
    fixture = sorted(GT.glob("*.txt"))[0]
    text = fixture.read_text(encoding="utf-8", errors="replace")
    rep, _, _ = diagnose(str(fixture), None)
    assert rep.system.minecraft_version, "fixture lost its version line"
    rule = Rule(id="t.e2e", title="gated", when={"exception_any": ["."], "mc_version": ">=1.20"})
    assert evaluate_rule(rule, MatchCtx.build(rep)) is not None
    assert text
