"""Rule localisation: zh copy is used when present, English when it is not.

The contract is deliberately narrow. A rule may ship Chinese copy for its
title, explanation and fixes; nothing else about the diagnosis changes, and a
rule with no translation must read exactly as it did before. That is what lets
translations land rule by rule without a flag day.
"""
from __future__ import annotations

from pathlib import Path

from mcd.cli import diagnose
from mcd.rules.engine import Rule, RuleSet, _localised

ROOT = Path(__file__).resolve().parent.parent
GT = ROOT / "tests" / "fixtures" / "ground-truth"


def test_localised_prefers_zh_only_when_asked() -> None:
    rule = Rule(id="x", title="English title", explanation="English body",
                fixes=["English fix"], title_zh="中文标题",
                explanation_zh="中文说明", fixes_zh=["中文修复"])
    assert _localised(rule, "en")[0] == "English title"
    assert _localised(rule, "zh")[0] == "中文标题"
    assert _localised(rule, "zh-CN")[0] == "中文标题"


def test_localised_falls_back_field_by_field() -> None:
    # A rule may translate the title and leave the fixes in English; the gap is
    # reported by tools/i18n_status.py, never rendered as an empty finding.
    rule = Rule(id="x", title="English title", explanation="English body",
                fixes=["English fix"], title_zh="中文标题")
    title, expl, fixes = _localised(rule, "zh")
    assert title == "中文标题"
    assert expl == "English body"
    assert fixes == ["English fix"]


def test_every_translated_rule_translates_all_three_fields() -> None:
    rs = RuleSet.load()
    half = [r.id for r in rs.rules if r.title_zh and not (r.explanation_zh and r.fixes_zh)]
    assert not half, f"rule has a zh title but no zh body: {half}"


def test_zh_diagnosis_renders_chinese_and_keeps_placeholders() -> None:
    fixture = next(GT.glob("*.txt"))
    _, findings, _ = diagnose(str(fixture), None, lang="zh")
    assert findings, "fixture stopped producing a finding"
    top = findings[0]
    assert any("\u4e00" <= ch <= "\u9fff" for ch in top.title), top.title
    assert "{{" not in top.title and "{{" not in top.explanation


def test_en_diagnosis_is_unchanged_by_the_translation_layer() -> None:
    fixture = next(GT.glob("*.txt"))
    _, findings, _ = diagnose(str(fixture), None)          # default lang
    assert findings
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in findings[0].title)
