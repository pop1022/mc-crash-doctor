"""`corpus/VERSION_STRATA.md` is a published claim; keep it internally honest.

The number in that file answers "does this tool work on my version?", so it is
the kind of table that gets copied into a README and quoted without the caveats
attached. Re-deriving it costs ~40 s, so it is NOT re-derived here -- these
tests check the arithmetic that the renderer and the analysis are supposed to
agree on, which is where a hand-edit or a refactor breaks first:

  * the strata add up to the total (a dropped stratum changes the headline),
  * `quotable_as_rate` really is `n >= min_n_for_quoting` (the bar that keeps a
    3-report stratum from being quoted as a percentage),
  * every interval brackets its own rate (Wilson, not the normal approximation),
  * a pair is called a failure only when the criterion says so -- gap above the
    threshold AND disjoint intervals -- so the verdict sentence cannot drift from
    the numbers above it,
  * a pair is only skipped for low n when one side really is under the bar.

`python tools/version_strata.py --check` is the staleness half; it is a manual
command on purpose, because it parses all 661 reports.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "corpus" / "version-strata.json"
MD_PATH = ROOT / "corpus" / "VERSION_STRATA.md"


def _res() -> dict:
    if not JSON_PATH.is_file():
        pytest.fail("corpus/version-strata.json is missing -- run "
                    "python tools/version_strata.py")
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def test_strata_add_up_to_the_total():
    res = _res()
    n = sum(s["n"] for s in res["strata"])
    k = sum(s["diagnosed"] for s in res["strata"])
    assert n == res["totals"]["n"], f"strata hold {n} reports, total says {res['totals']['n']}"
    assert k == res["totals"]["diagnosed"]
    assert n == res["files"], f"{res['files']} files but {n} stratified"
    assert res["totals"]["rate"] == round(k / n, 4)


def test_quotable_flag_matches_the_declared_bar():
    res = _res()
    bar = res["min_n_for_quoting"]
    wrong = [(s["version"], s["n"], s["quotable_as_rate"])
             for s in res["strata"]
             if s["quotable_as_rate"] != (s["n"] >= bar)]
    assert not wrong, f"quotable flag disagrees with n >= {bar}: {wrong}"


def test_every_interval_brackets_its_rate():
    bad = [(s["version"], s["rate"], s["lo"], s["hi"])
           for s in _res()["strata"]
           if not (s["lo"] <= s["rate"] <= s["hi"])]
    assert not bad, f"interval does not contain the rate: {bad}"


def test_failures_are_exactly_the_pairs_that_meet_the_criterion():
    res = _res()
    thr = res["gap_threshold_pp"]
    expected = {p["a"] + "|" + p["b"] for p in res["adjacent_pairs"]
                if p["intervals_disjoint"] and p["gap_pp"] > thr}
    actual = {p["a"] + "|" + p["b"] for p in res["failures"]}
    assert actual == expected, (
        "the verdict list and the criterion disagree -- "
        f"criterion says {sorted(expected)}, report says {sorted(actual)}")


def test_no_pair_is_called_adjacent_across_eras():
    """`1.21` and `26.1` are not neighbours: different numbering schemes."""
    for p in _res()["adjacent_pairs"]:
        a, b = p["a"], p["b"]
        assert a.split(".")[0] == b.split(".")[0], (
            f"{a} vs {b} chained across the 1.x -> dated-version switch")


def test_skipped_pairs_really_are_below_the_bar():
    res = _res()
    bar = res["min_n_for_quoting"]
    for s in res["skipped_for_low_n"]:
        below = [v for v, n in s["n"].items() if n < bar]
        assert below, f"{s['a']} vs {s['b']} skipped but both reach n >= {bar}"
        assert set(below) == set(s["under_min_n"]), (
            f"{s['a']} vs {s['b']}: under-min side listed as "
            f"{s['under_min_n']}, measured {below}")


def test_markdown_lists_every_stratum():
    res = _res()
    md = MD_PATH.read_text(encoding="utf-8") if MD_PATH.is_file() else ""
    assert md, "corpus/VERSION_STRATA.md is missing"
    missing = [s["version"] for s in res["strata"]
               if f"`{s['version']}`" not in md]
    assert not missing, f"strata absent from the rendered table: {missing}"
    assert re.search(r"Overall \d+/\d+ = [\d.]+%", md), "headline line is missing"
