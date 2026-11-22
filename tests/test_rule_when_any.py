"""when_any: any one block may match, while the keys beside it still must.

Why this is a separate shape rather than more regex alternation: the conditions
being OR-ed are on different fields (a stack frame OR the description, say), and
the honest rule wants captures from whichever one matched.
"""
from __future__ import annotations

from mcd.model import CrashReport, Severity
from mcd.rules.engine import (MatchCtx, Rule, RuleSet, _config_warnings,
                              evaluate_rule, run_rules)


def ctx(**fields) -> MatchCtx:
    rep = CrashReport(full_text="boom")
    rep.description = fields.pop("description", "")
    rep.kind = fields.pop("kind", "")
    for k, v in fields.items():
        setattr(rep.system, k, v)
    return MatchCtx.build(rep)


def rule(**when) -> Rule:
    return Rule(id="t", title="t", when=when, severity=Severity.WARNING)


# --- the disjunction --------------------------------------------------------
def test_either_block_matches() -> None:
    r = rule(when_any=[{"description": ["ticking entity"]},
                       {"kind": ["watchdog"]}])
    assert evaluate_rule(r, ctx(description="Ticking entity")) is not None
    assert evaluate_rule(r, ctx(kind="watchdog")) is not None


def test_neither_block_matches() -> None:
    r = rule(when_any=[{"description": ["ticking entity"]},
                       {"kind": ["watchdog"]}])
    assert evaluate_rule(r, ctx(description="render crash")) is None


def test_keys_beside_when_any_still_have_to_hold() -> None:
    r = rule(loader=["forge"],
             when_any=[{"description": ["ticking"]}, {"kind": ["watchdog"]}])
    assert evaluate_rule(r, ctx(description="ticking", loader="forge")) is not None
    assert evaluate_rule(r, ctx(description="ticking", loader="fabric")) is None


def test_only_when_any_is_allowed() -> None:
    r = rule(when_any=[{"text": ["boom"]}])
    assert evaluate_rule(r, ctx()) is not None      # full_text is "boom"


def test_captures_come_from_the_block_that_matched() -> None:
    r = rule(when_any=[{"text": ["marker (\\w+)"]}])
    rep = CrashReport(full_text="marker alpha")
    caps = evaluate_rule(r, MatchCtx.build(rep))
    assert caps is not None
    assert caps["text"].group(1) == "alpha"


def test_an_empty_when_any_matches_nothing() -> None:
    assert evaluate_rule(rule(when_any=[]), ctx()) is None


def test_a_nested_when_any_is_not_half_applied() -> None:
    r = rule(when_any=[{"when_any": [{"text": ["boom"]}]}])
    assert evaluate_rule(r, ctx()) is None


# --- through the whole rule pipeline ---------------------------------------
def test_run_rules_uses_when_any_end_to_end() -> None:
    rep = CrashReport(full_text="java.lang.OutOfMemoryError: Java heap space")
    rep.kind = "crash"
    r = Rule(id="t.any", title="Disjunction fired",
             severity=Severity.WARNING,
             when={"when_any": [{"kind": ["watchdog"]},
                                {"text": ["OutOfMemoryError"]}]},
             explanation="either shape", fixes=["fix it"])
    findings = run_rules(rep, RuleSet([r]))
    assert [f.rule_id for f in findings] == ["t.any"]


# --- load-time shape checks -------------------------------------------------
def test_bad_shapes_are_named_at_load_time() -> None:
    for value, needle in (("oops", "must be a list"), ([], "is empty")):
        errs = _config_warnings("f.yaml", {"id": "x", "when": {"when_any": value}})
        assert any(needle in e for e in errs), (value, errs)

    nested = _config_warnings(
        "f.yaml", {"id": "x", "when": {"when_any": [{"when_any": [{"text": ["a"]}]}]}})
    assert any("nested when_any" in e for e in nested)

    empty_clause = _config_warnings(
        "f.yaml", {"id": "x", "when": {"when_any": [{}]}})
    assert any("matches every report" in e for e in empty_clause)


def test_the_shipped_pack_still_loads_without_warnings() -> None:
    rs = RuleSet.load()
    assert not rs.errors
    assert len(rs.rules) == 46