"""CLI 契约：参数必须真的到达它声称要影响的地方。

两个 bug 在这里钉死，都是"标志被接受、但没生效"的类型——最难被发现，
因为退出码是 0、输出看着正常：

    --rules-dir   在 ``--rules`` 列表里能看到，诊断时却被丢弃
    --json --dir  输出多个首尾相接的 JSON 对象，``json.load()`` 抛 Extra data

这两条都写成了回归测试，而不是改完就算。
"""
from __future__ import annotations

import json

import pytest

from mcd.cli import diagnose, main
from mcd.rules.engine import RuleSet

REPORT = """\
---- Minecraft Crash Report ----
// I blame Dinnerbone.

Description: Ticking entity

java.lang.RuntimeException: probe sentinel
\tat net.minecraft.server.MinecraftServer.tick(MinecraftServer.java:1)
"""

RULE = """\
rules:
- id: probe.always
  title: Probe rule fired
  severity: fatal
  priority: 1
  confidence: 0.99
  tags: [probe]
  when:
    text: [probe sentinel]
  explanation: fixture rule for the --rules-dir contract test
  fix: [nothing to fix]
"""


def _rule_dir(tmp_path):
    d = tmp_path / "rules"
    d.mkdir()
    (d / "probe.yaml").write_text(RULE, encoding="utf-8")
    return d


def _report(tmp_path, name="crash-1.txt"):
    p = tmp_path / name
    p.write_text(REPORT, encoding="utf-8")
    return p


# --- --rules-dir 必须影响诊断 -------------------------------------------------
def test_extra_rule_dir_reaches_the_cli_diagnosis(tmp_path, capsys):
    """The reported bug: the flag listed the rule but never ran it."""
    rep = _report(tmp_path)
    rc = main([str(rep), "--text", "--rules-dir", str(_rule_dir(tmp_path))])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Probe rule fired" in out, \
        "--rules-dir was accepted but its rules never reached run_rules()"


def test_without_the_flag_the_probe_rule_does_not_fire(tmp_path, capsys):
    """Reverse control: the assertion above must not pass on a builtin rule."""
    rep = _report(tmp_path)
    main([str(rep), "--text"])
    assert "Probe rule fired" not in capsys.readouterr().out


def test_diagnose_api_accepts_rules_dirs(tmp_path):
    """The API is what action.py and library users call; keep it in sync."""
    rep = _report(tmp_path)
    _, findings, _ = diagnose(str(rep), None,
                              rules_dirs=[str(_rule_dir(tmp_path))])
    assert any(f.rule_id == "probe.always" for f in findings)


def test_rule_sets_extra_dirs_but_not_when_absent(tmp_path):
    with_dir = RuleSet.load([str(_rule_dir(tmp_path))])
    without = RuleSet.load()
    assert "probe.always" in with_dir.ids()
    assert "probe.always" not in without.ids()


# --- 缺失的规则目录不能静默 ---------------------------------------------------
def test_missing_rules_dir_is_a_hard_error(tmp_path):
    """A typo must not silently degrade to builtin-only diagnosis."""
    rep = _report(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main([str(rep), "--rules-dir", str(tmp_path / "no-such-dir")])
    assert exc.value.code == 2


def test_missing_dir_is_recorded_by_the_engine(tmp_path):
    """Even when called directly, a missing dir is reported, not swallowed."""
    rs = RuleSet.load([str(tmp_path / "no-such-dir")])
    assert any("does not exist" in e for e in rs.errors)


# --- 批量 --json 必须是合法 JSON ----------------------------------------------
def test_batch_json_parses_as_one_array(tmp_path, capsys):
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    main(["--dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 2


def test_single_json_stays_a_single_object(tmp_path, capsys):
    """Batch became an array; the one-file contract must not silently change."""
    rep = _report(tmp_path)
    main([str(rep), "--json"])
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_batch_json_keeps_every_report(tmp_path, capsys):
    """Concatenation used to hide documents behind the first parse error."""
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    main(["--dir", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    sources = [d.get("source", "") for d in data]
    assert len(set(sources)) == 2


# --- 目录枚举不能重复 ---------------------------------------------------------
def test_crash_prefixed_report_is_counted_once(tmp_path, capsys):
    """`crash-*.txt` and `*.txt` both match a real crash report.

    Enumerating both globs without dedupe diagnosed every `crash-*.txt` twice:
    doubled findings, doubled runtime, and a doubled chance of `--exit-code`
    firing. The two-file batch below must stay two.
    """
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    main(["--dir", str(tmp_path), "--json"])
    assert len(json.loads(capsys.readouterr().out)) == 2


def test_plain_txt_and_log_still_both_found(tmp_path, capsys):
    """Dedupe must not drop a file that only matches the non-overlapping glob."""
    _report(tmp_path, "crash-1.txt")
    (tmp_path / "latest.log").write_text(REPORT, encoding="utf-8")
    main(["--dir", str(tmp_path), "--json"])
    assert len(json.loads(capsys.readouterr().out)) == 2


# --- 批量：失败必须被计数，全部失败不能算成功 ---------------------------------
def test_batch_reports_a_summary_on_stderr(tmp_path, capsys):
    """A 454-file batch used to be silent; stderr now carries the tally.

    It goes to stderr on purpose: --json/--markdown on stdout must stay
    machine-readable.
    """
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    main(["--dir", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert "2/2 diagnosed" in err


def test_single_file_gets_no_summary(tmp_path, capsys):
    """The tally is a batch affordance; one file should not print it."""
    main([str(_report(tmp_path)), "--text"])
    assert "diagnosed (" not in capsys.readouterr().err


def test_all_files_failing_is_not_success(tmp_path, capsys, monkeypatch):
    """The regression that matters: total failure used to exit 0.

    A machine with no PyYAML printed "error parsing <file>" once per report and
    still returned 0, so CI would read a wholly broken run as a pass.
    """
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")

    def boom(*a, **kw):
        raise RuntimeError("simulated per-file failure")

    monkeypatch.setattr("mcd.cli.diagnose", boom)
    assert main(["--dir", str(tmp_path), "--json"]) == 2


def test_partial_failure_keeps_the_findings_exit_contract(tmp_path, capsys,
                                                          monkeypatch):
    """Some files failing must not hijack --exit-code's meaning."""
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    real = diagnose
    calls = {"n": 0}

    def flaky(path, text, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("one bad file")
        return real(path, text, **kw)

    monkeypatch.setattr("mcd.cli.diagnose", flaky)
    assert main(["--dir", str(tmp_path), "--json"]) == 0
    assert "1 failed" in capsys.readouterr().err


def test_missing_rule_engine_is_reported_once(tmp_path, capsys, monkeypatch):
    """A broken environment is not a property of each report.

    Before: one "error parsing <file>" line per report, exit 0.
    After:  one line naming the real problem, exit 2.
    """
    _report(tmp_path, "crash-1.txt")
    _report(tmp_path, "crash-2.txt")
    _report(tmp_path, "crash-3.txt")

    def no_yaml(cls, *a, **kw):
        raise RuntimeError("PyYAML is required")

    monkeypatch.setattr("mcd.cli.RuleSet.load", classmethod(no_yaml))
    assert main(["--dir", str(tmp_path), "--json"]) == 2
    err = capsys.readouterr().err
    assert err.count("error:") == 1, "the environment error must not repeat per file"
    assert "PyYAML" in err
