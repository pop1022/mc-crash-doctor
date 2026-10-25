"""Maven / Fabric version ranges, and the three forms people conflate.

ROADMAP 2.2 pins the semantics this file checks:

    [1.20,1.21)   inclusive lower, exclusive upper
    [1.20]        exactly 1.20
    1.20          MINIMUM -- "1.20 or newer", not "1.20 only"

The third one is the reason this module exists. Treating a bare version as
exact makes every legitimately-newer install look like a mismatch; treating it
as "anything" makes every mismatch disappear. Both are wrong in opposite
directions, and a dependency checker that is wrong in the quiet direction is
worse than no checker.

`None` is a first-class answer: it means "the constraint was read and not
understood". The caller must print that, not swallow it (see
tests/test_pack_doctor.py::test_unparseable_range_becomes_undecided_not_ok).
"""
from __future__ import annotations

import pytest

from mcd.pack.version import compare, parse_spec, satisfies


# --- the three forms the roadmap calls out ---------------------------------
def test_inclusive_lower_exclusive_upper():
    assert satisfies("1.20", "[1.20,1.21)") is True
    assert satisfies("1.20.4", "[1.20,1.21)") is True
    assert satisfies("1.21", "[1.20,1.21)") is False
    assert satisfies("1.19.9", "[1.20,1.21)") is False


def test_closed_brackets_are_exact():
    assert satisfies("1.20", "[1.20]") is True
    assert satisfies("1.20.1", "[1.20]") is False
    # padded comparison: 1.20 and 1.20.0 are the same version
    assert satisfies("1.20.0", "[1.20]") is True


def test_bare_version_is_a_minimum_not_an_exact_match():
    """"1.20 or newer" -- the interpretation people get wrong."""
    assert satisfies("1.20.9", "1.20") is True
    assert satisfies("1.21", "1.20") is True
    assert satisfies("1.19.9", "1.20") is False


@pytest.mark.parametrize("version,spec,expected", [
    # open/closed mixes
    ("1.20", "(1.20,1.21]", False),
    ("1.20.1", "(1.20,1.21]", True),
    ("1.21", "(1.20,1.21]", True),
    ("1.21.1", "(1.20,1.21]", False),
    # half-open, the common Forge shape
    ("1.20", "[1.20,)", True),
    ("99", "[1.20,)", True),
    # Fabric operators
    ("1.20.4", ">=1.20.1", True),
    ("1.20.0", ">=1.20.1", False),
    ("1.20.4", ">1.20.1", True),
    ("1.20.1", ">1.20.1", False),
    ("1.20.1", "=1.20.1", True),
    # ranges and conjunctions
    ("1.20.4", ">=1.20.1 <1.21", True),
    ("1.21", ">=1.20.1 <1.21", False),
    ("1.20.5", "~1.20.1", True),        # ~ bumps the minor
    ("1.21.0", "~1.20.1", False),
    ("1.9.9", "^1.20", False),          # ^ bumps the major
    ("1.99", "^1.20", True),
    ("1.20.7", "1.20.x", True),
    ("1.21", "1.20.x", False),
    # wildcards
    ("0.1", "*", True),
    ("0.1", "", True),
    # prerelease sorts below the release
    ("1.20.1-beta", "1.20.1", False),
    ("1.20.1", ">=1.20.1-beta", True),
])
def test_range_forms(version, spec, expected):
    assert satisfies(version, spec) is expected


def test_unparseable_ranges_answer_none_rather_than_guessing():
    assert satisfies("1.20.4", "banana") is None
    assert satisfies("1.20.4", "latest") is None
    assert satisfies("1.20.4", "[1.20,1.21") is None      # unclosed bracket
    assert satisfies("1.20.4", "[1.20)") is None          # half a range
    # and the reverse: an unorderable *installed* version
    assert satisfies("", "1.20") is None
    assert satisfies("RELEASE", "1.20") is None


def test_parse_spec_exposes_the_terms_it_understood():
    terms = parse_spec("[1.20,1.21)")
    assert [t[0] for t in terms] == [">=", "<"]
    assert [t[2] for t in terms] == ["1.20", "1.21"]


def test_compare_orders_versions_and_says_so_when_it_cannot():
    assert compare("1.20", "1.20.0") == 0
    assert compare("1.20.1", "1.20") == 1
    assert compare("1.19.9", "1.20") == -1
    assert compare("1.20.1-beta", "1.20.1") == -1
    assert compare("1.20.1+build7", "1.20.1") == 0        # build metadata
    assert compare("latest", "1.20") is None
