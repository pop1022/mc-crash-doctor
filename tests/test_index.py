"""`corpus/index.jsonl` integrity contract (ROADMAP 1D.4).

The index is the input to every derived artifact in `corpus/`: compatibility
edges, the Modrinth mapping audit, the coverage dashboard, the blind evaluation.
Two defects were measured in it and fixed in `tools/rederive_index.py`; this file
keeps them fixed.

DEFECT 1 -- 34 duplicate rows (488 rows, 454 distinct issues)
    `load_index()` existed to make harvest incremental, was never called, and
    `harvest_repo` therefore appended a second copy of every issue it re-scanned.
    33 pairs were byte-identical; the 34th differed only in `comments` (6 vs 7),
    i.e. two harvest passes on different days. Anything counting rows over-counted
    by 7% -- `MODRINTH_MAPPING.json` said `"reports": 488`.

DEFECT 2 -- `mod_ids` populated in 0 of 488 rows
    `MODID_RE` looks for the Forge-1.4-era `from mod (<id>)` marker. It occurs
    480 times in this corpus and is `unknown` every single time, so the filter
    `!= "unknown"` emptied the field while the schema kept promising it. The
    `-- Mod List --` section is the real source: 111 records, 3,080 ids.

    pytest tests/test_index.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.metadata.jars import is_loader_artifact          # noqa: E402

INDEX = ROOT / "corpus" / "index.jsonl"

#: Fields every record must carry. A new field is a schema change: add it here
#: and in the harvester in the same commit, or consumers will KeyError later.
REQUIRED_KEYS = {
    "repo", "number", "title", "state", "created_at", "labels", "verdict",
    "comments", "source", "is_crash_report", "is_log", "descriptions",
    "exceptions", "caused_by", "mod_ids", "jars", "mixin_configs",
    "body_chars", "url",
}


@pytest.fixture(scope="module")
def records():
    assert INDEX.exists(), f"missing corpus index: {INDEX}"
    with open(INDEX, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --------------------------------------------------------------------------
# defect 1: one row per issue
# --------------------------------------------------------------------------
def test_no_duplicate_issues(records):
    """A duplicate row double-counts every statistic derived from the index."""
    seen: dict[tuple[str, int], int] = {}
    dups: dict[tuple[str, int], int] = {}
    for rec in records:
        key = (rec["repo"], rec["number"])
        seen[key] = seen.get(key, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    assert not dups, (
        f"{len(dups)} duplicated (repo, number) pairs, e.g. {list(dups)[:3]}. "
        "Run `python tools/rederive_index.py --dedupe`."
    )


def test_row_count_matches_crash_text_count(records):
    """After dedupe, every row has exactly one report on disk."""
    files = list((ROOT / "corpus" / "github").glob("**/*.crash.txt"))
    assert len(records) == len(files), (
        f"{len(records)} index rows vs {len(files)} crash texts. A row without "
        "text cannot be re-derived; text without a row is unreachable."
    )


# --------------------------------------------------------------------------
# defect 2: mod_ids means something
# --------------------------------------------------------------------------
def test_mod_ids_is_not_a_dead_field(records):
    """Tripwire: it was 0/488, and an empty column still *looks* like data."""
    populated = [r for r in records if r.get("mod_ids")]
    assert populated, (
        "mod_ids is empty in every record again. The old regex "
        "(`from mod (x)`) matches only `unknown` in this corpus -- use the "
        "`-- Mod List --` section via tools/rederive_index.py --mod-ids."
    )
    share = len(populated) / len(records)
    assert share > 0.10, (
        f"only {share:.1%} of records have mod_ids; the Mod List is present in "
        "about a quarter of reports, so this is lower than the corpus supports"
    )


def test_mod_ids_never_lists_the_platform(records):
    """`minecraft` and `forge` are Mod List rows, not installed mods."""
    bad = {
        modid
        for rec in records
        for modid in rec.get("mod_ids") or []
        if is_loader_artifact(modid)
    }
    assert not bad, f"platform ids leaked into mod_ids: {sorted(bad)}"


def test_mod_ids_shape(records):
    for rec in records:
        ids = rec.get("mod_ids")
        assert isinstance(ids, list)
        assert len(ids) <= 60, "the index caps list fields at 60"
        assert len(ids) == len(set(ids)), "duplicate ids in one record"
        assert ids == sorted(ids), "mod_ids is stored sorted"
        assert all(i and i == i.strip() for i in ids)


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------
def test_every_record_has_the_documented_keys(records):
    for rec in records:
        missing = REQUIRED_KEYS - set(rec)
        assert not missing, f"{rec.get('repo')}#{rec.get('number')} missing {missing}"


def test_verdicts_come_from_the_label_mapping(records):
    """`verdict` is weak supervision; an invented value would silently drop out.

    The vocabulary is not restated here -- it is read from the harvester's own
    `LABEL_SEMANTICS`, so adding a label cannot leave this test behind.
    """
    from tools.harvest_corpus import LABEL_SEMANTICS

    allowed = set(LABEL_SEMANTICS.values()) | {None}
    seen = {rec.get("verdict") for rec in records}
    unknown = seen - allowed
    assert not unknown, (
        f"verdict values with no label behind them: {sorted(map(str, unknown))}"
    )
