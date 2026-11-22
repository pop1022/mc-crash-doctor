"""The release check must fail closed, and it must not need a network to test.

The venv half is exercised by tools/verify_release.py itself (run locally: it
passed on the 0.1.0 artifacts). These assertions cover the decisions it makes:
tag equality, expected rule ids, wheel content checks, and a missing artifact.
"""
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def module():
    spec = importlib.util.spec_from_file_location(
        "verify_release", ROOT / "tools" / "verify_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tag_must_equal_the_version() -> None:
    vr = module()
    assert vr.tag_matches("v0.1.0", "0.1.0")
    assert not vr.tag_matches("v0.2.0", "0.1.0")
    assert not vr.tag_matches("0.1.1", "0.1.0")


def test_expected_rules_come_from_the_lifecycle_manifest() -> None:
    vr = module()
    ids = vr.expected_rule_ids()
    from mcd.rules.engine import RuleSet
    assert ids == {r.id for r in RuleSet.load().rules}


def test_a_wheel_without_rule_packs_is_rejected(tmp_path: Path) -> None:
    vr = module()
    whl = tmp_path / "empty-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("mcd/__init__.py", "")
    failures: list[str] = []
    vr.check_wheel_contents(whl, failures)
    assert any("no YAML rule packs" in f for f in failures)


def test_a_missing_dist_directory_is_an_error(tmp_path: Path, capsys) -> None:
    vr = module()
    assert vr.main([str(tmp_path / "nope")]) == 2
    assert "need a wheel and an sdist" in capsys.readouterr().err


def test_sha256sums_file_matches_the_artifacts(tmp_path: Path) -> None:
    vr = module()
    f = tmp_path / "x.whl"
    f.write_bytes(b"payload")
    assert vr.sha256(f) == (
        "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5")
