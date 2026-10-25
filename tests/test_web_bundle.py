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


# --- payload size -----------------------------------------------------------
# The page loads Pyodide from a CDN, so web/ is only part of what a visitor
# downloads -- but it is the part this repo controls, and the only part that can
# grow without anyone noticing. Sizes are declared in tools/build_web.py so the
# build and the gate cannot disagree about what the budget is.
def _build_web():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_web", ROOT / "tools" / "build_web.py")
    bw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bw)
    return bw


def test_web_payload_stays_within_budget():
    bw = _build_web()
    sizes = bw.payload_sizes()
    over = bw.budget_report(sizes)
    measured = ", ".join(f"{k} {v:,} B" for k, v in sizes.items())
    assert not over, (
        "web/ grew past its declared budget:\n  " + "\n  ".join(over)
        + f"\nmeasured: {measured}\n"
        "If the growth is wanted, raise SIZE_BUDGET in tools/build_web.py in "
        "this same commit and note why; if it is not, find what got in.")


def test_wheel_carries_no_build_detritus():
    """The likeliest way the wheel doubles is not a dependency -- it is a build
    that stops pruning. `.pyc`/`__pycache__`, a test tree or corpus data would
    all inflate the artifact and none of them can run in Pyodide."""
    with zipfile.ZipFile(_wheel()) as z:
        names = z.namelist()
    bad = [n for n in names
           if "__pycache__" in n or n.endswith((".pyc", ".pyo"))
           or n.startswith(("tests/", "corpus/", ".git/"))]
    assert not bad, (
        f"the web wheel ships {len(bad)} non-runtime file(s), e.g. {bad[:5]} "
        "-- run python tools/build_web.py")
