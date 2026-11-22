"""--validate-rules: a rule pack either loads whole or fails loudly.

Diagnosis is forgiving on purpose (one bad user file must not stop a crash from
being read). A pack check is the opposite job: the caller is about to ship or
install those rules, so a silently skipped file is the bug. These tests pin that
difference, plus the exit code CI depends on.
"""
from __future__ import annotations

from pathlib import Path

from mcd.cli import main

GOOD = """rules:
  - id: custom.example
    title: Example rule
    severity: warning
    when:
      text:
        - "example marker"
    explanation: An example, for the validator.
"""


def pack(tmp_path: Path, body: str, name: str = "custom.yaml") -> Path:
    d = tmp_path / "rules"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")
    return d


def test_builtin_pack_validates_clean(capsys) -> None:
    assert main(["--validate-rules"]) == 0
    out = capsys.readouterr()
    assert "46 loaded" in out.out and "no problems found" in out.out
    assert out.err == ""            # the grouped list is the only printer


def test_a_valid_external_rule_loads_and_is_counted(tmp_path: Path, capsys) -> None:
    d = pack(tmp_path, GOOD)
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 0
    out = capsys.readouterr().out
    assert "1 external" in out
    assert f"{d}: 1 rule(s)" in out


def test_malformed_yaml_fails_with_the_file_name(tmp_path: Path, capsys) -> None:
    d = pack(tmp_path, "rules: [unclosed\n")
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 1
    out = capsys.readouterr().out
    assert "problems (1)" in out
    assert "custom.yaml" in out


def test_an_unknown_key_is_a_failure_here(tmp_path: Path, capsys) -> None:
    # A typo means the rule does not do what its author thinks it does. During
    # diagnosis that is a warning; in a pack check it is a failed build.
    body = GOOD.replace("    severity: warning\n",
                        "    severity: warning\n    sing: text\n")
    d = pack(tmp_path, body)
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 1
    assert "unknown key" in capsys.readouterr().out


def test_shadowing_a_builtin_id_is_a_failure(tmp_path: Path, capsys) -> None:
    body = GOOD.replace("custom.example", "oom.heap")
    d = pack(tmp_path, body)
    assert main(["--validate-rules", "--rules-dir", str(d)]) == 1
    out = capsys.readouterr().out
    assert "duplicate rule id" in out and "oom.heap" in out


def test_a_missing_directory_is_rejected_before_loading(tmp_path: Path) -> None:
    try:
        main(["--validate-rules", "--rules-dir", str(tmp_path / "nope")])
    except SystemExit as e:          # argparse's error path
        assert e.code == 2
    else:                            # pragma: no cover
        raise AssertionError("expected SystemExit(2)")
