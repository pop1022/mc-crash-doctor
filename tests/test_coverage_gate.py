"""The coverage gate is code too: its floors must point at real packages, and
its comparison must actually fail. A gate that only ever prints "ok" is worse
than none -- it turns a missing measurement into an implied guarantee.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import coverage_gate as G  # noqa: E402


def _sizes(**overrides: tuple[int, int]) -> dict[str, tuple[int, int]]:
    """One synthetic file per floor, at 100% unless overridden."""
    out = {f"{prefix}/x.py": (100, 0) for prefix in G.FLOORS}
    for name, pair in overrides.items():
        out[name] = pair
    return out


def test_every_floor_points_at_something_that_exists() -> None:
    for prefix in list(G.FLOORS) + list(G.EXEMPT):
        assert (ROOT / prefix).exists(), f"{prefix} is not in the tree any more"


def test_clean_measurement_passes() -> None:
    assert G.check(_sizes()) == []


def test_a_regressed_package_fails() -> None:
    bad = G.check(_sizes(**{"mcd/parser/x.py": (100, 40)}))
    assert any("mcd/parser" in line for line in bad)


def test_a_broken_exemption_fails() -> None:
    # cli.py dropping below its own floor must fail too, not stay silent.
    bad = G.check(_sizes(**{"mcd/cli.py": (100, 99)}))
    assert any("mcd/cli.py" in line for line in bad)


def test_a_missing_package_is_reported_not_ignored() -> None:
    sizes = _sizes()
    del sizes["mcd/triage/x.py"]
    bad = G.check(sizes)
    assert any("mcd/triage" in line for line in bad)


def test_floors_are_never_above_perfect() -> None:
    for prefix, floor in G.FLOORS.items():
        assert 0 < floor <= 100, prefix
    assert 0 < G.TOTAL_FLOOR <= 100
