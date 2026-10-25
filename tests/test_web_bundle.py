"""The committed web/ wheel must contain exactly what mcd/ contains.

`web/` ships a prebuilt wheel so the static site runs without a build step.
That artifact silently drifted once: it was built before `mcd/action.py`
existed, so the browser was executing older code than the CLI while every
other test still passed. Nothing caught it because nothing looked at the
bundle.

These tests make the drift loud. They fail with "run tools/build_web.py"
instead of letting the web app quietly disagree with the library it claims to
run.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def _wheel() -> Path:
    manifest = WEB / "wheel-manifest.json"
    if not manifest.is_file():
        pytest.fail("web/wheel-manifest.json is missing -- run tools/build_web.py")
    name = json.loads(manifest.read_text(encoding="utf-8"))["file"]
    wheel = WEB / name
    if not wheel.is_file():
        pytest.fail(f"web/{name} is missing -- run tools/build_web.py")
    return wheel


def _source_modules() -> set[str]:
    return {p.relative_to(ROOT).as_posix()
            for p in (ROOT / "mcd").rglob("*.py")
            if "__pycache__" not in p.parts}


def _wheel_modules(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as z:
        return {n for n in z.namelist()
                if n.startswith("mcd/") and n.endswith(".py")}


def test_manifest_points_at_a_real_wheel():
    assert _wheel().suffix == ".whl"


def test_wheel_is_not_missing_source_modules():
    missing = _source_modules() - _wheel_modules(_wheel())
    assert not missing, (
        "web wheel is stale -- run python tools/build_web.py "
        f"(missing: {sorted(missing)})")


def test_wheel_carries_no_deleted_modules():
    extra = _wheel_modules(_wheel()) - _source_modules()
    assert not extra, (
        "web wheel still ships modules deleted from mcd/ -- run "
        f"python tools/build_web.py (extra: {sorted(extra)})")


def test_wheel_ships_every_rule_pack():
    packs = {p.name for p in (ROOT / "mcd" / "rules" / "builtin").glob("*.yaml")}
    assert packs, "no rule packs found in mcd/rules/builtin"
    with zipfile.ZipFile(_wheel()) as z:
        in_wheel = {Path(n).name for n in z.namelist() if n.endswith(".yaml")}
    assert packs <= in_wheel, (
        f"rule packs missing from the web wheel: {sorted(packs - in_wheel)}")


def test_manifest_source_digest_matches_mcd():
    """The guards above compare *names*, so they miss a wheel that ships the
    right modules with stale *contents*.

    That happened: fixing catastrophic regex backtracking in
    `mcd/parser/report.py` renamed nothing, so the committed wheel went on
    carrying a parser that needs 9 seconds for a 276 KB report -- and every
    test stayed green. The digest below is the missing half of the guard.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_web", ROOT / "tools" / "build_web.py")
    bw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bw)

    manifest = json.loads(
        (WEB / "wheel-manifest.json").read_text(encoding="utf-8"))
    recorded = manifest.get("source_digest")
    assert recorded, "manifest has no source_digest -- run tools/build_web.py"
    assert recorded == bw.source_digest(), (
        "mcd/ changed since the web wheel was built (contents, not module "
        "names) -- run python tools/build_web.py")
