"""A rule's `lifecycle_status` must be backed by evidence, not by memory.

Four rules are `experimental` because only a synthetic fixture has ever fired
them. `tools/stamp_provenance.py` knows how to promote them; the missing piece
was anything that noticed *when to run it*. `corpus/rule-lifecycle.json` binds
each status to the corpus revision it was derived from, and these tests make the
disagreement loud.

The split matters:

  * the cheap half lives here -- digest plus a status comparison, ~0.2 s, so it
    runs on every change and is what notices that the corpus moved;
  * the derivation costs ~40 s (it parses all 661 reports), so it stays behind
    `tools/rule_lifecycle.py --write` and shows up here as a JSON diff.

What a stale snapshot looks like in practice: someone harvests 200 new reports,
the digest changes, this file fails, and the message names the command. The
expensive step then runs once and either confirms 4/4 still hold or prints
`PROMOTE oom.save-time (real evidence: harvested:.../1234)` -- a status change
that has to land in the YAML, because that is what users read.

Nothing here asserts *which* rules are experimental. That set is an output of
the measurement (see the JSON); pinning it by hand is what this file replaces.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SNAPSHOT = ROOT / "corpus" / "rule-lifecycle.json"


def _tool():
    """Import tools/rule_lifecycle.py as a module (same pattern as
    tests/test_web_bundle.py uses for tools/build_web.py)."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rule_lifecycle", TOOLS / "rule_lifecycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snap() -> dict:
    if not SNAPSHOT.is_file():
        pytest.fail("corpus/rule-lifecycle.json is missing -- run "
                    "python tools/rule_lifecycle.py --write")
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_covers_every_builtin_rule():
    from mcd.rules.engine import RuleSet

    live = {r.id for r in RuleSet.load().rules}
    recorded = set(_snap()["rules"])
    assert live == recorded, (
        f"snapshot out of date -- added: {sorted(live - recorded)}, "
        f"removed: {sorted(recorded - live)}; "
        "run python tools/rule_lifecycle.py --write")


def test_snapshot_is_current_for_this_corpus_revision():
    """The one test that notices new evidence arriving: ~0.15 s to hash."""
    bad = _tool().stale_reasons(_snap())
    assert not bad, "\n".join(bad)


def test_no_rule_is_experimental_after_real_evidence():
    """The promotion signal. An `experimental` rule that fires on a real report
    has earned `verified`, and leaving it is exactly the drift this file is
    meant to prevent."""
    due = _tool().promotion_due(_snap())
    detail = [f"{rid}: real_evidence={_snap()['rules'][rid]['real_evidence'][:3]}"
              for rid in due]
    assert not due, (
        "rule(s) have real-corpus evidence but are still experimental:\n  "
        + "\n  ".join(detail)
        + "\nSet lifecycle_status: verified in the rule YAML, then re-run "
        "python tools/rule_lifecycle.py --write")


def test_experimental_rules_carry_no_real_evidence():
    """Other direction: nothing may be marked experimental *and* cite a real
    report. If this fails, the YAML and the JSON disagree about the same fact."""
    liars = [rid for rid, v in _snap()["rules"].items()
             if v["lifecycle_status"] == "experimental" and v["real_evidence"]]
    assert not liars, f"experimental but has real evidence: {liars}"


def test_verified_rules_are_not_marked_hold_without_fixtures():
    """A verified rule with neither real evidence nor a synthetic fixture has no
    proof at all -- `test_rule_metadata.py` covers the YAML side, this catches
    the snapshot side."""
    empty = [rid for rid, v in _snap()["rules"].items()
             if v["lifecycle_status"] != "experimental"
             and not v["real_evidence"] and not v["synthetic_fixtures"]]
    assert not empty, (
        f"{len(empty)} rule(s) claim a non-experimental status with no evidence "
        f"in the snapshot: {empty[:5]}")
