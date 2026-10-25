"""Contract tests for the two attribution signals added for ROADMAP 1E.

Background: `tools/attribution_ablation.py` removes the crash report's own
``Suspected Mods:`` line and asks whether the remaining evidence still reaches
a mod id. Before these signals, it did not for **20 of 35** oracle-bearing
reports (57%) -- and those 20 were not random: 17 were Fabric API crashes whose
only written trace of the owner is a mixin-generated method name.

Two things had to be right for the fix to be a fix rather than a regression,
and both are pinned here:

1. **Seed anchoring.** Fabric names a patched method
   ``<realName>$<seed>$<modid>$<rest>``. A bare ``$...$`` scan does not recover
   mod ids; it recovers Mixin jargon. Measured on the corpus, the unanchored
   version's most frequent "ids" were ``bridge``, ``new`` and ``static``.
2. **Depth limiting.** The first version scanned 25 frames and its first three
   *hits* included frame #12 and #14 -- both crash-reporter mixins (Not Enough
   Crashes patches the crash handler, so it appears in every report it
   decorates). Restricting to the top 5 frames removed both false positives and
   cost nothing.

    pytest tests/test_attribution_signals.py -v
"""
from __future__ import annotations

import dataclasses
import glob
from pathlib import Path

import pytest

from mcd.parser.report import parse_file
from mcd.triage.attribution import (
    NEAR_FRAME_LIMIT, mixin_method_modid, triage,
)

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / "corpus" / "github"


def _one(repo_suffix: str, issue: str) -> Path | None:
    hits = glob.glob(str(GITHUB / f"*__{repo_suffix}" / f"{issue}.crash.txt"))
    return Path(hits[0]) if hits else None


def _bare_top(path: Path) -> str | None:
    """Top-1 with the report's own `Suspected Mods` line removed."""
    rep = parse_file(path)
    t = triage(dataclasses.replace(rep, suspected_mods=[]))
    return t.suspects[0].modid if t.suspects else None


# --- 1. seed anchoring ------------------------------------------------------
@pytest.mark.parametrize("method,expected", [
    # the real shape, Fabric API: hyphenated mod id, seed `cdi000`
    ("RegistryLoader.wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall",
     "fabric-registry-sync-v0"),
    # mixinextras wraps it and appends a counter
    ("mixinextras$bridge$wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall$36",
     "fabric-registry-sync-v0"),
    ("handler$ccj000$sodium$postInit", "sodium"),
    ("modify$ebh000$notenoughcrashes$atTheEndOfSecondCatch", "notenoughcrashes"),
])
def test_seeded_mixin_method_yields_the_owner(method, expected):
    assert mixin_method_modid(method) == expected


@pytest.mark.parametrize("method", [
    "",
    "load",                                   # plain, no mixin marker
    "lambda$reload$4",                        # $ but no seed
    "mixinextras$bridge$method_45121$33",     # seed-ish, but no mod segment
    "invoke$abc$takeWhile",                   # seed too short / no counter
    "handler$abc000$minecraft$tick",          # platform, not a mod
    "handler$abc000$mixinextras$tick",        # a mixin library, not a mod
])
def test_non_owner_method_names_yield_nothing(method):
    assert mixin_method_modid(method) is None


def test_backslash_free_scan_would_have_returned_jargon():
    """The anchor is load-bearing: without the seed group, the same regex
    happily returns the word between two `$`s."""
    method = "mixinextras$bridge$wrapOperation$cdi000$sodium$postInit"
    bare = [seg for seg in method.split("$") if seg][1:4]
    assert "bridge" in bare, (
        "the unanchored scan is supposed to pick up jargon; if this stops "
        "being true the docstring's justification needs revisiting")
    assert mixin_method_modid(method) == "sodium"


def test_depth_limit_is_small():
    """A guard on the guard: NEAR_FRAME_LIMIT is what keeps crash-reporter
    mixins out, so it must stay in the same order of magnitude as the
    findings it was tuned for (top 5)."""
    assert NEAR_FRAME_LIMIT <= 8


# --- 2. real reports --------------------------------------------------------
def test_fabric_api_report_answers_without_the_loader_hint():
    """fabric-api#4862 was silent with the hint removed. The owner appears only
    in a frame's method name (`.method` since the 2026-10-25 frame repair; this
    used to arrive glued onto `.cls`)."""
    p = _one("fabric-api", "4862")
    if p is None:
        pytest.skip("harvested corpus absent")
    assert _bare_top(p) == "fabric-registry-sync-v0"


def test_no_mod_list_report_answers_without_the_loader_hint():
    """sodium#3771 carries no Mod List at all; the method name is the only
    evidence in the whole report."""
    p = _one("sodium", "3771")
    if p is None:
        pytest.skip("harvested corpus absent")
    assert _bare_top(p) == "sodium"


def test_crash_reporter_mixin_far_down_the_trace_is_not_blamed():
    """sodium#3511: Not Enough Crashes patches the crash handler, so its mixin
    appears at frame #12 of every report it decorates. It names the reporter,
    not the cause, and must not become the top suspect."""
    p = _one("sodium", "3511")
    if p is None:
        pytest.skip("harvested corpus absent")
    assert _bare_top(p) != "notenoughcrashes"


def test_hint_removal_does_not_promote_a_new_top_suspect_over_explicit_ownership():
    """Ablation must only ever weaken evidence. On a report that names the
    owner explicitly (`from mod (x)`), dropping the loader's hint must not
    hand the top spot to something else."""
    p = _one("Mekanism", "8254")
    if p is None:
        pytest.skip("harvested corpus absent")
    with_hint = triage(parse_file(p))
    assert with_hint.suspects and with_hint.suspects[0].modid
    assert _bare_top(p) == with_hint.suspects[0].modid
