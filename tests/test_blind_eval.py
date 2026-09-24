"""Contract tests for tools/blind_eval.py (ROADMAP 1B.1).

The full evaluation is minutes-slow (it parses the whole corpus twice), so it
stays a manual/CI-report tool. What MUST hold structurally is tested here,
fast:

  - the dev/blind split is deterministic and partitioning (no overlap,
    no losses),
  - every report pinned in a rule's provenance lands in the DEV set (a rule
    can never be "blind-tested" on the report that motivated it),
  - the verdict-direction constants are disjoint and cover the scored space.

    pytest tests/test_blind_eval.py -v
"""
from __future__ import annotations

import glob
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "blind_eval", ROOT / "tools" / "blind_eval.py")
be = importlib.util.module_from_spec(spec)
spec.loader.exec_module(be)

_ALL = glob.glob(str(Path(be.GITHUB) / "**" / "*.crash.txt"), recursive=True)


def test_split_is_a_deterministic_partition():
    dev1, blind1 = be.split_corpus()
    dev2, blind2 = be.split_corpus()
    if not _ALL:
        pytest.skip("harvested corpus absent (run tools/harvest_corpus.py)")
    assert dev1 == dev2 and blind1 == blind2, "split is not deterministic"
    assert not (set(dev1) & set(blind1)), "dev/blind overlap"
    assert len(dev1) + len(blind1) == len(_ALL), "split lost reports"


def test_rule_pins_forced_into_dev():
    """The whole point of a blind set: a report that motivated a rule cannot
    also be used to claim the rule generalises."""
    if not _ALL:
        pytest.skip("harvested corpus absent")
    dev, blind = be.split_corpus()
    pinned = be.pinned_paths()
    if not pinned:
        pytest.skip("no harvested pins in rule provenance")
    leaked = pinned & set(blind)
    assert not leaked, f"pinned reports leaked into blind set: {sorted(leaked)[:5]}"


def test_verdict_directions_are_disjoint():
    assert not (be.VERDICT_SHOULD_HIT_REPO & be.VERDICT_SHOULD_MISS_REPO)
    assert not (be.VERDICT_AMBIGUOUS &
                (be.VERDICT_SHOULD_HIT_REPO | be.VERDICT_SHOULD_MISS_REPO))
    assert be.CRASH_VERDICTS == (be.VERDICT_SHOULD_HIT_REPO
                                 | be.VERDICT_SHOULD_MISS_REPO
                                 | be.VERDICT_AMBIGUOUS)
    # the two scored directions must be non-empty, else blame-error rate is
    # silently uncomputable
    assert be.VERDICT_SHOULD_HIT_REPO and be.VERDICT_SHOULD_MISS_REPO


def _one(repo_suffix: str, issue: str) -> str | None:
    hits = glob.glob(str(Path(be.GITHUB) / f"*__{repo_suffix}"
                         / f"{issue}.crash.txt"))
    return hits[0] if hits else None


def test_direction_aware_scoring_on_known_samples():
    """End-to-end check of the direction-aware attribution scoring on three
    real harvested reports whose maintainer verdicts are known. Fast (3 files),
    real data, and it pins the subtle case:

      Mekanism/8455        root_cause_elsewhere, stack is all mekanism.api ->
                           top-1 = mekanism = repo -> counts as a BLAME ERROR
                           (else_wrongrepo). This is a genuine attribution
                           limit, not a bug: the maintainer tagged it
                           'interaction'/'Not Mekanism' (Sinytra Connector),
                           but stack-frame attribution cannot see bytecode-
                           level mod interaction. Documented, not hidden.
      TinkersConstruct/5379 root_cause_elsewhere, top-1 = mantle (external)
                           -> correct (else_correct)
      TinkersConstruct/5590 root_cause_elsewhere, top-1 = mekanismtools
                           -> correct (else_correct)

    If attribution later improves on 8455 (e.g. learns Connector), update the
    expected counts deliberately.
    """
    files = [p for p in (_one("Mekanism", "8455"),
                         _one("TinkersConstruct", "5379"),
                         _one("TinkersConstruct", "5590")) if p]
    if len(files) < 3:
        pytest.skip("known attribution samples absent from harvested corpus")
    m = be.evaluate(files)["mod_repo"]
    # all three carry root_cause_elsewhere verdicts -> all land in else_*
    assert m["else_n"] == 3
    assert (m["else_correct"] + m["else_wrongrepo"]
            + m["else_nopick"]) == m["else_n"], "scoring not conserved"
    # TiC's two external attributions are directionally correct
    assert m["else_correct"] >= 2, f"TiC external attribution regressed: {m}"
    # 8455 is currently the one repo-named-on-elsewhere blame error
    assert m["else_wrongrepo"] == 1, (
        f"Mekanism/8455 attribution changed -- if this is an improvement, "
        f"update this test deliberately. got {m}")
    # no bug_in_this_mod reports in this subset
    assert m["bug_n"] == 0

