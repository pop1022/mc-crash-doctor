"""Synthetic-fixture tests for rules that never fire on the real corpora.

ROADMAP 0.3: four rules covered failure modes absent from our 661-file corpus
(oom.save-time, oom.gc-overhead, disk.space, native.gl). Rather than leave
them as untestable dead weight, each gets a SYNTHETIC fixture (clearly marked,
shaped like a real report) that proves the rule fires on its intended input.

native.gl additionally carries a REGRESSION guard: its `exception` pattern
once wrongly included `mixin.InjectionError` (copy-paste), which would have
misdiagnosed every mixin injection failure as a graphics-driver problem. The
negative case below pins that fix.

    pytest tests/test_rule_fixtures.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file, parse_text  # noqa: E402
from mcd.rules.engine import Rule, RuleSet, run_rules  # noqa: E402

_rs = RuleSet.load()
_SYN = ROOT / "tests" / "fixtures" / "synthetic"


def _fired(path: Path) -> set[str]:
    return {f.rule_id for f in run_rules(parse_file(path), _rs)}


# fixture file -> rule that MUST fire on it
PINS = {
    "oom-save-time.txt": "oom.save-time",
    "oom-gc-overhead.txt": "oom.gc-overhead",
    "disk-space.txt": "disk.space",
    "native-gl.txt": "native.gl",
}


@pytest.mark.parametrize("fname,rule", sorted(PINS.items()))
def test_synthetic_fixture_fires_rule(fname, rule):
    path = _SYN / fname
    assert path.exists(), f"missing fixture {path}"
    fired = _fired(path)
    assert rule in fired, f"{fname}: expected {rule}, fired={sorted(fired)}"


def test_save_time_does_not_fire_without_save_path():
    """oom.save-time must be strictly narrower than oom.heap: a heap OOM with
    NO chunk-serialisation frames must fall through to oom.heap only. This is
    the distinction tests/test_e2e.py asserts on the real ground-truth reports;
    keep a synthetic guard here too so the two rules can't silently merge."""
    fired = _fired(_SYN / "oom-gc-overhead.txt")
    assert "oom.save-time" not in fired
    # gc-overhead fixture is a heap pressure case; oom.heap may or may not fire
    # depending on wording, but save-time specifically must not.


def test_native_gl_does_not_fire_on_mixin_injection():
    """REGRESSION: native.gl used to list mixin.InjectionError in its
    `exception` alternation. A mixin injection failure must be diagnosed by
    the mixin rules, never as a graphics-driver problem."""
    text = (
        "---- Minecraft Crash Report ----\n"
        "Description: Initializing game\n\n"
        "org.spongepowered.asm.mixin.injection.throwables.InjectionError: "
        "Critical injection failure: @Inject annotation on someMod$onTick "
        "could not find any targets\n"
        "\tat org.spongepowered.asm.mixin.injection.struct.InjectionInfo."
        "postInject(InjectionInfo.java:400)\n"
    )
    rep = parse_text(text)
    fired = {f.rule_id for f in run_rules(rep, _rs)}
    assert "native.gl" not in fired, f"native.gl misfired on a mixin error: {sorted(fired)}"


def test_all_four_zero_fire_rules_now_covered():
    """Meta-check: the audit that motivated 0.3 found exactly these 4 rules
    never firing on real corpora. Assert all 4 now have a passing synthetic
    fixture, so this cleanup can't silently regress."""
    covered = {rule for rule in PINS.values()}
    assert covered == {"oom.save-time", "oom.gc-overhead", "disk.space",
                       "native.gl"}
    for rule in covered:
        assert any(r.id == rule for r in _rs.rules), f"rule {rule} vanished"


# --------------------------------------------------------------------------
# OOM is not "this mod crashed" (found by dogfooding issue #1)
# --------------------------------------------------------------------------
# The corpora cannot catch this one: neither the harvested 454 nor the aternos
# 201 contains a single OOM report (1D.4 measured the `oom` bucket as empty and
# saw the same thing from a completely different direction). It took a real
# crash report pasted into a real GitHub issue.
_GT = ROOT / "tests" / "fixtures" / "ground-truth"
_GT_OOM = _GT / "crash-2026-09-08_18.45.43-server.txt"


def test_runtime_mod_stands_down_on_oom():
    """`crash.runtime-mod` matches `java.lang.*(Exception|Error)`, which sweeps
    up OutOfMemoryError. On dogfood issue #1 that produced a second finding
    telling the user to update a mod, with copy about "runtime NPEs/ISEs" on a
    report containing neither. The heap rule owns this failure."""
    assert _GT_OOM.exists(), f"missing fixture {_GT_OOM}"
    fired = _fired(_GT_OOM)
    assert "oom.heap" in fired, fired
    assert "crash.runtime-mod" not in fired, (
        "crash.runtime-mod claims an OOM report again -- the `not_exception` "
        f"condition is gone or wrong; fired={sorted(fired)}")


def test_runtime_mod_still_fires_on_a_non_oom_crash():
    """The guard against over-suppression. `not_exception` must remove the OOM
    case and nothing else; if it removed the rule entirely, the fix would have
    deleted the rule's reason to exist."""
    hits = [p.name for p in sorted(_GT.glob("*.txt"))
            if "crash.runtime-mod" in _fired(p)]
    assert hits, ("crash.runtime-mod no longer fires on any ground-truth "
                  "report -- `not_exception` is too broad")


def test_not_exception_is_read_by_the_engine():
    """Unit-level, so the test above cannot pass for the wrong reason (e.g. if
    `has_suspect` happened to fail on that fixture). Both halves run on the same
    file: with `not_exception` the rule must stay silent, without it the same
    patterns must fire."""
    assert _GT_OOM.exists()
    base = {"severity": "info",
            "when": {"exception": [r"java\.lang\..*Error"]}}

    with_neg = Rule.from_dict({**base, "id": "test.not-oom",
                               "title": "not an OOM",
                               "when": {**base["when"],
                                        "not_exception":
                                            [r"java\.lang\.OutOfMemoryError"]}})
    got = [f.rule_id for f in run_rules(parse_file(_GT_OOM),
                                       RuleSet([with_neg]))]
    assert got == [], f"not_exception was ignored; rule fired anyway: {got}"

    without_neg = Rule.from_dict({**base, "id": "test.catchall",
                                  "title": "catch-all"})
    got2 = [f.rule_id for f in run_rules(parse_file(_GT_OOM),
                                        RuleSet([without_neg]))]
    assert got2 == ["test.catchall"], (
        f"control failed -- the positive pattern alone must match: {got2}")
