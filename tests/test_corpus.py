"""Pytest suite over the vendored + ground-truth corpora.

Every corpus file becomes a case: parsing must never raise, and the
ground-truth reports additionally assert which rules MUST and MUST NOT fire.
A new rule without a fixture shows up as unchanged coverage here, and a
regressed rule fails loudly with the file that broke it.

Run:
    pytest tests/ -q
    pytest tests/test_corpus.py -k ground_truth -v

The standalone scripts (tests/test_e2e.py, tests/eval_parser.py,
tests/test_redaction.py) remain the canonical gates in run_tests.sh and CI;
this module makes the same corpus usable under pytest for contributors who
prefer it.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file  # noqa: E402
from mcd.rules.engine import RuleSet, run_rules  # noqa: E402
from mcd.triage.attribution import triage  # noqa: E402
from tests.test_e2e import GROUND_TRUTH, MUST_NOT_FIRE  # noqa: E402

ATERNOS = sorted(glob.glob(str(ROOT / "corpus/aternos/**/*.log"), recursive=True))
FIXTURES = sorted(glob.glob(str(ROOT / "tests/fixtures/ground-truth/crash-*.txt")))

_ruleset = RuleSet.load()


def _id(path: str) -> str:
    return Path(path).name


# ---------------------------------------------------------------- corpus ----
@pytest.mark.parametrize("log", ATERNOS, ids=_id)
def test_aternos_parses(log):
    """Every vendored corpus file must parse and run rules without raising."""
    rep = parse_file(log)
    assert rep.kind in ("crash-report", "log", "unknown")
    run_rules(rep, _ruleset)
    triage(rep)


@pytest.mark.parametrize("log", ATERNOS, ids=_id)
def test_aternos_platform_detected(log):
    """No corpus file may fall through to a wrong-but-plausible platform.

    Reuses the verified EQUIV mapping from eval_parser (which accepts a set of
    correct ids per platform, e.g. Spigot may report spigot/paper/bukkit).
    Fine-grained accuracy is gated by tests/eval_parser.py --strict.
    """
    import json

    from tests.eval_parser import EQUIV

    jf = log[:-4] + ".json"
    if not os.path.exists(jf):
        pytest.skip("no expectation file")
    want_name = (json.load(open(jf, encoding="utf-8")).get("name") or "").strip()
    accept = EQUIV.get(want_name, {want_name.lower().replace(" ", "-")})
    sysd = parse_file(log).system
    # Either axis may satisfy the expectation: a Prism-wrapped client log is
    # labelled "Prism Launcher" (launcher axis) while a Prism-wrapped Fabric
    # log is labelled "Fabric" (loader axis).
    got_axes = {sysd.loader, sysd.launcher} - {""}
    assert got_axes & accept, \
        f"{_id(log)}: want one of {accept} got axes={got_axes}"


# ------------------------------------------------------------ ground truth --
@pytest.mark.parametrize("fx", FIXTURES, ids=_id)
def test_ground_truth_rules(fx):
    """Real reports: pinned rules fire, forbidden rules do not."""
    stem = Path(fx).stem.replace("-server", "")
    want = GROUND_TRUTH.get(stem)
    if want is None:
        pytest.skip(f"no expectation for {stem}")
    forbid = MUST_NOT_FIRE.get(stem, [])

    rep = parse_file(fx)
    fired = {f.rule_id for f in run_rules(rep, _ruleset)}

    missing = [r for r in want if r not in fired]
    assert not missing, f"{stem}: rules did not fire: {missing} (fired={sorted(fired)})"
    bad = [r for r in forbid if r in fired]
    assert not bad, f"{stem}: forbidden rules fired: {bad}"


@pytest.mark.parametrize("fx", FIXTURES, ids=_id)
def test_ground_truth_parse(fx):
    """All six reports must parse with the full mod list and heap data."""
    rep = parse_file(fx)
    assert rep.system.loader == "forge"
    assert rep.system.minecraft_version == "1.20.1"
    assert len(rep.mods) == 266, f"{_id(fx)}: parsed {len(rep.mods)} mods"
    assert rep.system.memory.max_mib in (2048, 8192)
    assert rep.root_cause is not None


def test_ground_truth_attribution_names_a_mod():
    """The two watchdog/OOM-with-mixin reports must attribute to a real mod."""
    named = {}
    for fx in FIXTURES:
        rep = parse_file(fx)
        t = triage(rep)
        if t.suspects:
            named[Path(fx).stem] = t.suspects[0].modid
    # 18.39/18.45 (modernfix/harium) and the two watchdogs all attribute
    assert len(named) >= 3, f"too few attributed: {named}"


# ---------------------------------------------------------------- coverage --
def test_ruleset_loads_and_is_unique():
    ids = [r.id for r in _ruleset.rules]
    assert len(ids) >= 25, f"only {len(ids)} rules loaded"
    assert len(ids) == len(set(ids)), "duplicate rule ids"


def test_builtin_packs_present():
    packs = sorted(p.name for p in (ROOT / "mcd/rules/builtin").glob("*.yaml"))
    assert "memory-performance.yaml" in packs
    assert "mod-loading.yaml" in packs


def test_rules_have_actionable_fixes():
    """Every rule must ship at least one fix step and an explanation."""
    for r in _ruleset.rules:
        assert r.explanation.strip(), f"{r.id}: empty explanation"
        assert r.fixes, f"{r.id}: no fixes"
        assert any(len(f) > 20 for f in r.fixes), f"{r.id}: fixes too thin"


def test_rule_ids_are_dotted_lowercase():
    import re

    pat = re.compile(r"^[a-z0-9]+(\.[a-z0-9\-]+)+$")
    for r in _ruleset.rules:
        assert pat.match(r.id), f"bad rule id style: {r.id}"
