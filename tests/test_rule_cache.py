"""规则集缓存的不变量。

缓存是为了性能（120 份报告 5.91 s -> 2.09 s），但性能测试本身不稳定，
所以这里测的是**语义**：缓存命中时必须与重新解析得到完全相同的结果，
且不同参数不能互相污染。任一条破裂，缓存就是错误的加速。

反向对照：`test_second_load_reuses_the_parse` 证明缓存确实生效；
`test_different_dirs_do_not_collide` 证明它没有把不该合并的合并掉。
"""
from __future__ import annotations

import pytest

from mcd.rules.engine import RuleSet

RULE = """\
rules:
- id: {rid}
  title: T
  severity: warning
  priority: 10
  confidence: 0.8
  tags: [t]
  when:
    text: [x]
  explanation: e
  fix: [f]
"""


@pytest.fixture(autouse=True)
def _fresh_cache():
    RuleSet.clear_cache()
    yield
    RuleSet.clear_cache()


def _dir(tmp_path, name, rid):
    d = tmp_path / name
    d.mkdir()
    (d / "r.yaml").write_text(RULE.format(rid=rid), encoding="utf-8")
    return d


def test_second_load_reuses_the_parse(tmp_path, monkeypatch):
    """The whole point: identical arguments must not re-read the YAML."""
    calls = []
    original = RuleSet._read.__func__

    def counting(cls, extra_dirs):
        calls.append(extra_dirs)
        return original(cls, extra_dirs)

    monkeypatch.setattr(RuleSet, "_read", classmethod(counting))

    RuleSet.load()
    RuleSet.load()
    RuleSet.load()
    assert len(calls) == 1, "cache miss on identical arguments"


def test_cache_returns_equivalent_rules(tmp_path):
    a = RuleSet.load()
    b = RuleSet.load()
    assert a.ids() == b.ids()
    assert a.rules[0].title == b.rules[0].title


def test_each_call_gets_its_own_errors_list(tmp_path):
    """`errors` is mutable and per-caller; sharing it would leak warnings."""
    a = RuleSet.load()
    b = RuleSet.load()
    assert a is not b
    assert a.errors is not b.errors
    a.errors.append("mutated by caller")
    assert "mutated by caller" not in b.errors


def test_different_dirs_do_not_collide(tmp_path):
    """Two different --rules-dir values are two different rule sets."""
    d1 = _dir(tmp_path, "one", "probe.one")
    d2 = _dir(tmp_path, "two", "probe.two")

    only_one = RuleSet.load([str(d1)])
    only_two = RuleSet.load([str(d2)])
    both = RuleSet.load([str(d1), str(d2)])

    assert "probe.one" in only_one.ids()
    assert "probe.two" not in only_one.ids()
    assert "probe.two" in only_two.ids()
    assert "probe.one" in both.ids() and "probe.two" in both.ids()


def test_cached_missing_dir_still_reports_the_error(tmp_path):
    """A load warning must survive the cache, not be swallowed on the 2nd call."""
    missing = str(tmp_path / "nope")
    first = RuleSet.load([missing])
    second = RuleSet.load([missing])
    assert any("does not exist" in e for e in first.errors)
    assert first.errors == second.errors


def test_strict_still_raises_on_a_cached_error(tmp_path):
    """strict is per-call and must not be cached away."""
    missing = str(tmp_path / "nope")
    RuleSet.load([missing])                       # populate cache, non-strict
    with pytest.raises(ValueError):
        RuleSet.load([missing], strict=True)


def test_env_change_invalidates_the_cache(tmp_path, monkeypatch):
    """MCD_RULES_PATH is part of the identity of a rule set."""
    d = _dir(tmp_path, "env", "probe.env")
    monkeypatch.delenv("MCD_RULES_PATH", raising=False)
    before = RuleSet.load()
    assert "probe.env" not in before.ids()

    monkeypatch.setenv("MCD_RULES_PATH", str(d))
    after = RuleSet.load()
    assert "probe.env" in after.ids(), "stale cache ignored a changed environment"


def test_clear_cache_forces_a_reread(tmp_path, monkeypatch):
    """Long-lived processes need an explicit way out of the cache."""
    calls = []
    original = RuleSet._read.__func__

    def counting(cls, extra_dirs):
        calls.append(1)
        return original(cls, extra_dirs)

    monkeypatch.setattr(RuleSet, "_read", classmethod(counting))
    RuleSet.load()
    RuleSet.clear_cache()
    RuleSet.load()
    assert len(calls) == 2


def test_caller_cannot_corrupt_the_cached_rule_list(tmp_path):
    """load() re-sorts into its own list, so in-place edits stay local."""
    a = RuleSet.load()
    baseline = len(a.rules)
    a.rules.clear()
    b = RuleSet.load()
    assert len(b.rules) == baseline
