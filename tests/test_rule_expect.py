"""expect: assertions a rule carries about its own behaviour on a fixture.

The point is the negative half. Every positive pin in the repo proves a rule
fires; nothing proved it *stays quiet* where a neighbouring rule owns the case,
which is exactly how a catch-all starts blaming a mod for an OOM.
"""
from __future__ import annotations

from pathlib import Path

from mcd.cli import main
from mcd.model import Severity
from mcd.rules.engine import Rule, RuleSet, _config_warnings
from mcd.rules.expect import check, resolve

GT = "ground-truth/crash-2026-09-08_18.01.19-server.txt"      # fires oom.heap
WD = "ground-truth/crash-2026-09-08_22.31.14-server.txt"       # fires watchdog


def rule(**kw) -> Rule:
    base = dict(id="t.expect", title="t", severity=Severity.WARNING,
                when={"text": ["this text is not in any fixture"]},
                explanation="x", fixes=["y"])
    base.update(kw)
    return Rule(**base)


# --- resolution -------------------------------------------------------------
def test_resolve_accepts_a_path_under_tests_fixtures() -> None:
    p = resolve(GT)
    assert p is not None and p.name.endswith("18.01.19-server.txt")


def test_resolve_appends_txt_for_a_bare_ref() -> None:
    assert resolve(GT.removesuffix(".txt")) is not None


def test_resolve_returns_none_for_nonsense() -> None:
    assert resolve("no/such/fixture.txt") is None


# --- the assertions ---------------------------------------------------------
def test_the_builtin_pack_assertions_all_pass() -> None:
    problems, checked = check(RuleSet.load())
    assert problems == []
    assert checked == 6            # 3 rules x (fires + quiet)


def test_a_rule_that_does_not_fire_is_a_problem() -> None:
    problems, checked = check(RuleSet([rule(expect={"fires": [GT]})]))
    assert checked == 1
    assert any("expected to fire" in p for p in problems)


def test_a_catch_all_fails_its_quiet_assertion() -> None:
    # "." matches every report: exactly the shape a quiet assertion exists for.
    problems, _ = check(RuleSet([rule(when={"text": ["."]},
                                     expect={"quiet": [GT]})]))
    assert any("expected to stay quiet" in p for p in problems)


def test_a_missing_fixture_is_reported_not_skipped() -> None:
    problems, checked = check(RuleSet([rule(expect={"fires": ["nope.txt"]})]))
    assert checked == 0
    assert any("fixture not found" in p for p in problems)


def test_a_single_rule_is_checked_alone() -> None:
    # If the whole ruleset ran, another rule firing on GT could mask this one.
    problems, _ = check(RuleSet([rule(expect={"quiet": [GT]})]))
    assert problems == []


def test_assertions_only_see_their_own_rule() -> None:
    fires = rule(id="t.fires", when={"text": ["OutOfMemoryError"]},
                 expect={"fires": [GT]})
    quiet = rule(id="t.quiet", expect={"quiet": [GT]})
    problems, checked = check(RuleSet([fires, quiet]))
    assert checked == 2 and problems == []


# --- load-time shape --------------------------------------------------------
def test_non_mapping_expect_is_named() -> None:
    errs = _config_warnings("f.yaml", {"id": "x", "expect": ["fires"]})
    assert any("expect must be a mapping" in e for e in errs)


def test_unknown_expect_key_is_named() -> None:
    errs = _config_warnings("f.yaml", {"id": "x", "expect": {"fire": ["a"]}})
    assert any("unknown key" in e and "fire" in e for e in errs)


def test_a_non_list_side_is_named() -> None:
    errs = _config_warnings("f.yaml", {"id": "x", "expect": {"fires": GT}})
    assert any("expect.fires must be a list" in e for e in errs)


# --- through the CLI --------------------------------------------------------
def test_validate_rules_runs_assertions(tmp_path: Path, capsys) -> None:
    fixture = (Path(__file__).resolve().parent / "fixtures" / GT).as_posix()
    body = f"""rules:
  - id: custom.expect
    title: Custom
    severity: warning
    when:
      text:
        - "OutOfMemoryError"
    explanation: x
    expect:
      fires:
        - "{fixture}"
"""
    d = tmp_path / "rules"
    d.mkdir()
    (d / "r.yaml").write_text(body, encoding="utf-8")
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 0
    out = capsys.readouterr().out
    assert "expect:" in out and "assertion(s) checked" in out
    assert "no problems found" in out


def test_validate_rules_fails_on_a_broken_assertion(tmp_path: Path, capsys) -> None:
    fixture = (Path(__file__).resolve().parent / "fixtures" / GT).as_posix()
    body = f"""rules:
  - id: custom.broken
    title: Custom
    severity: warning
    when:
      text:
        - "OutOfMemoryError"
    explanation: x
    expect:
      quiet:
        - "{fixture}"
"""
    d = tmp_path / "rules"
    d.mkdir()
    (d / "r.yaml").write_text(body, encoding="utf-8")
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 1
    assert "expected to stay quiet" in capsys.readouterr().out
