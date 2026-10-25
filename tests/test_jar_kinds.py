"""Jar kind classification contract (ROADMAP 1D.4).

`corpus/index.jsonl` has a `jars` field that is **raw evidence**: every `~[...]`
token in the harvested reports. That includes the JVM (`guava`), the loader
(`neoforge-...-universal.jar`) and real mods, all through one channel, because
1.20+ reports dropped the `-- Mod List --` section. A consumer that reads `jars`
as a mod list will report loader internals as "mods the user installed".

What is pinned here:

  1. the two source lists are **disjoint** -- a name in both would make
     `is_runtime_lib` and `classify_jar` disagree, and which one wins would
     depend on call order;
  2. `classify_jar` checks loader before library (so `coremods`, which is a
     loader component, never reports as a library);
  3. `partition_jars` is a partition: nothing lost, nothing double-counted;
  4. version segments are numeric-only, so `3dskinlayers` is a mod, not a
     version marker;
  5. stack-frame decorations (`~[name.jar:?]`) and version prefixes
     (`[1.20.1] name.jar`) both resolve to the same stem.

    pytest tests/test_jar_kinds.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.metadata.jars import (                                # noqa: E402
    JAR_KINDS,
    LOADER_ARTIFACTS,
    RUNTIME_LIBS,
    classify_jar,
    is_loader_artifact,
    is_runtime_lib,
    jar_stem,
    norm_key,
    partition_jars,
)


# --------------------------------------------------------------------------
# the lists are the whole input, so their integrity IS the contract
# --------------------------------------------------------------------------
def test_the_two_lists_do_not_overlap():
    """A shared name would make the loader/library verdict call-order dependent."""
    overlap = {norm_key(x) for x in LOADER_ARTIFACTS} & {
        norm_key(x) for x in RUNTIME_LIBS
    }
    assert not overlap, (
        f"{sorted(overlap)} appear in both LOADER_ARTIFACTS and RUNTIME_LIBS. "
        "Pick one: `coremods` used to be in both, and the old code reported it "
        "as a library only because it happened to check libraries first."
    )


def test_no_two_entries_collapse_to_the_same_key():
    """`fabric-loader` and `fabricloader` are one entry after `norm_key`.

    Lookups normalise both sides, so a duplicate is harmless at runtime -- but
    it means the list has two spellings of one name, and the next person to add
    `fabric_loader` should be told there are already two, not three.
    """
    for label, names in (("LOADER_ARTIFACTS", LOADER_ARTIFACTS),
                         ("RUNTIME_LIBS", RUNTIME_LIBS)):
        counts: dict[str, int] = {}
        for name in names:
            counts[norm_key(name)] = counts.get(norm_key(name), 0) + 1
        dups = {k: v for k, v in counts.items() if v > 1}
        assert not dups, f"{label} has duplicate entries after norm_key: {dups}"


def test_hyphenated_spellings_still_resolve():
    """The lists store one spelling; callers may pass another."""
    assert is_runtime_lib("commons-lang3")
    assert is_runtime_lib("commons_lang3")
    assert is_runtime_lib("netty-transport")      # family-root match
    assert is_loader_artifact("FabricLoader")


def test_coremods_is_a_loader_component():
    """Regression: it was in both lists, so `is_runtime_lib` won by accident."""
    assert classify_jar("coremods-1.0.jar") == "loader"
    assert is_loader_artifact("coremods")
    assert not is_runtime_lib("coremods")


# --------------------------------------------------------------------------
# stems
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Jade-1.20.1-Forge-11.13.1.jar", "Jade"),
        ("lambdynamiclights-4.8.11+1.21.1-neoforge.jar", "lambdynamiclights"),
        ("eternal_starlight-common-1.0.jar", "eternal-starlight"),
        ("~[guava-32.1.2-jre.jar:?]", "guava"),
        ("mixinextras-0.4.1.jar:?", "mixinextras"),
        ("[1.20.1] mcmod-2.0.jar", "mcmod"),
        ("%5B1.20.1%5D%20Foo-1.0.jar", "Foo"),
        ("3dskinlayers-1.0.jar", "3dskinlayers"),
        ("netty-transport-4.1.jar", "netty-transport"),
    ],
)
def test_stem_extraction(filename, expected):
    assert jar_stem(filename) == expected


@pytest.mark.parametrize("junk", ["", "   ", ".jar", "1.20.1.jar", "v2.jar"])
def test_unnameable_input_returns_empty_not_garbage(junk):
    """`""` is the signal for `unknown`; inventing a token would fake a mod."""
    assert jar_stem(junk) == ""


def test_stack_frame_and_prefix_forms_agree():
    """Two label-the-same-thing shapes must not classify differently."""
    bare = classify_jar("guava-32.1.2-jre.jar")
    framed = classify_jar("~[guava-32.1.2-jre.jar:?]")
    assert bare == framed == "library"


def test_a_digit_leading_mod_name_is_not_a_version():
    """`_VERSIONISH` must be numeric-only, or `3dskinlayers` vanishes."""
    assert jar_stem("3dskinlayers-1.0.jar") == "3dskinlayers"
    assert classify_jar("3dskinlayers-1.0.jar") == "mod"


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "filename, kind",
    [
        ("neoforge-21.1.250-universal.jar", "loader"),
        ("client-1.21.1-20240808.144430-srg.jar", "loader"),
        ("fabric-loader-0.16.0.jar", "loader"),
        ("guava-32.1.2-jre.jar", "library"),
        ("asm-util-9.6.jar", "library"),
        ("bootstrap-launcher-1.0.jar", "library"),   # hyphen-blind lookup
        ("Jade-1.20.1-Forge-11.13.1.jar", "mod"),
        ("", "unknown"),
        ("1.20.1.jar", "unknown"),
    ],
)
def test_classify_returns_a_declared_kind(filename, kind):
    got = classify_jar(filename)
    assert got in JAR_KINDS
    assert got == kind


def test_mod_is_the_assumed_default_and_says_so():
    """`mod` means "not a known runtime artifact", which is weaker than proof."""
    assert classify_jar("SomeTotallyUnknownMod-1.0.jar") == "mod"


# --------------------------------------------------------------------------
# partition invariant
# --------------------------------------------------------------------------
def test_partition_loses_nothing():
    jars = [
        "guava-32.1.2-jre.jar",
        "neoforge-21.1.250-universal.jar",
        "Jade-1.20.1-Forge-11.13.1.jar",
        "",
        "asm-9.6.jar",
        "Create-0.5.1.jar",
    ]
    parts = partition_jars(jars)
    assert set(parts) == set(JAR_KINDS)
    flat = [j for kind in JAR_KINDS for j in parts[kind]]
    assert sorted(flat) == sorted(jars), "every jar must land in exactly one kind"
    assert len(flat) == len(jars), "nothing may be double-counted"


def test_partition_preserves_input_order():
    jars = ["Bmod-1.0.jar", "guava-32.1.2-jre.jar", "Amod-1.0.jar"]
    parts = partition_jars(jars)
    assert parts["mod"] == ["Bmod-1.0.jar", "Amod-1.0.jar"]


def test_partition_of_empty_is_all_empty():
    parts = partition_jars([])
    assert all(v == [] for v in parts.values())
