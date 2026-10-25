"""Drift guard around `corpus/RULE_CANDIDATES.md` + `corpus/rule-candidates.json`.

WHY A GUARD AND NOT A REGENERATION
  The pack is a generated artifact (ROADMAP 1E.3) and it makes one load-bearing
  claim in its third line: *117 of 454 reports are uncovered, 107 clusters,
  top-10 = 17%, therefore R4 fires and writing rules is no longer the
  bottleneck.* Every follow-up decision quotes those numbers.

  The failure mode is not "the pack is wrong" -- it is **the corpus moving and
  the pack not following**. Add a rule, regenerate `coverage.json` (which the
  coverage gate does), forget this pack, and the repository now ships a document
  whose headline arithmetic contradicts its own coverage report. Nobody notices,
  because a stale number looks exactly like a fresh one.

  Regenerating inside the gate would catch that, but it parses 454 fragments
  (~40 s on top of a 72 s gate) to re-answer a question that only changes when
  rules or corpus change. So this file is split in two:

    always on     arithmetic that must hold *within* the committed pack, the
                  markdown twin agreeing with the JSON, and the pack agreeing
                  with `coverage.json` -- milliseconds, no corpus walk.
    MCD_DRIFT_FULL=1  a real regeneration, byte-compared. Opt-in, same reason
                  `tools/blind_eval.py` is a report and not a gate.

  The cross-artifact check is the one that actually catches staleness: two
  independent tools compute `uncovered` over the same corpus with the same
  ruleset, so their numbers disagreeing is a fact about the repository, not a
  matter of interpretation.

    pytest tests/test_rule_candidates.py -v
    MCD_DRIFT_FULL=1 pytest tests/test_rule_candidates.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
MD_PATH = CORPUS / "RULE_CANDIDATES.md"
JSON_PATH = CORPUS / "rule-candidates.json"
COVERAGE_PATH = CORPUS / "coverage.json"

_spec = importlib.util.spec_from_file_location(
    "suggest_rules", ROOT / "tools" / "suggest_rules.py")
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

#: The vocabulary `candidate_when()` is allowed to produce. Listed here rather
#: than imported so that adding a verdict is a deliberate two-place edit: the
#: pack's `verdicts` counter is read by humans deciding what to write next, and
#: a new label with no explanation is worse than the old one.
VERDICTS = {"reusable", "needs_generalisation", "singleton", "singleton+overfit"}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _json() -> dict:
    if not JSON_PATH.exists():
        pytest.skip("corpus/rule-candidates.json absent "
                    "(run tools/suggest_rules.py --report)")
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _md() -> str:
    if not MD_PATH.exists():
        pytest.skip("corpus/RULE_CANDIDATES.md absent "
                    "(run tools/suggest_rules.py --report)")
    return MD_PATH.read_text(encoding="utf-8")


def _clusters() -> list[dict]:
    return _json()["clusters"]


def _summary() -> dict:
    return _json()["summary"]


# --------------------------------------------------------------------------
# the pack is not a ruleset
# --------------------------------------------------------------------------
def test_the_pack_is_not_loadable_as_rules():
    """1E.3's hard constraint is "model output never reaches `builtin/`". A
    second way to break it is to leave a YAML file somewhere a glob walks. The
    pack is JSON + Markdown precisely so it cannot be mistaken for a rule pack;
    this pins that shape and the absence of loose YAML next to it."""
    assert set(_json()) == {"summary", "clusters"}
    stray = sorted(p.name for p in CORPUS.glob("*.y*ml"))
    assert not stray, f"loose rule-pack files in corpus/: {stray}"


# --------------------------------------------------------------------------
# internal arithmetic
# --------------------------------------------------------------------------
def test_clusters_partition_the_uncovered_set():
    """Every uncovered report appears in exactly one cluster. If this breaks,
    `reports_per_rule` and the top-N share are both meaningless -- they are
    computed by summing cluster sizes."""
    clusters = _clusters()
    sizes = sum(c["size"] for c in clusters)
    reports = [r for c in clusters for r in c["reports"]]
    assert sizes == _summary()["uncovered"], "cluster sizes do not sum to the total"
    assert len(reports) == sizes, "a cluster's `size` disagrees with its `reports`"
    dupes = {r for r in reports if reports.count(r) > 1}
    assert not dupes, f"reports in more than one cluster: {sorted(dupes)[:5]}"
    assert all(c["size"] >= 1 for c in clusters), "empty cluster"


def test_summary_arithmetic_matches_the_clusters():
    s, clusters = _summary(), _clusters()
    assert s["clusters"] == len(clusters)
    assert s["singletons"] == sum(1 for c in clusters if c["size"] == 1)
    assert s["singleton_reports"] == sum(c["size"] for c in clusters
                                         if c["size"] == 1)
    assert s["reports_per_rule"] == round(s["uncovered"] / len(clusters), 2)
    assert sum(s["verdicts"].values()) == len(clusters), (
        "the verdict counter does not cover every cluster")
    assert set(s["verdicts"]) <= VERDICTS, sorted(set(s["verdicts"]) - VERDICTS)


def test_r4_verdict_follows_the_published_threshold():
    """R4 is a *stopping rule fixed in advance*; that is the only thing making
    it a risk register entry rather than a rationalisation. Recomputing it from
    the constants means lowering `R4_MIN_SHARE` to keep writing rules cannot
    leave a green suite behind."""
    s, clusters = _summary(), _clusters()
    assert s["top_n"] == sr.R4_TOP_N
    assert s["r4_threshold"] == sr.R4_MIN_SHARE
    top = sum(c["size"] for c in clusters[:s["top_n"]])
    assert s["top_n_reports"] == top
    assert s["top_n_share"] == round(top / s["uncovered"], 4)
    assert s["r4_fires"] is (s["top_n_share"] < s["r4_threshold"])


def test_every_verdict_is_in_the_known_vocabulary():
    for c in _clusters():
        assert c["verdict"] in VERDICTS, (c["signature"], c["verdict"])


def test_overfit_markers_and_verdicts_agree():
    """`candidate_when()` only tests for overfit markers on singletons, so the
    two labels mean something specific. A `singleton` that silently carries a
    UUID would be re-advertised as reusable six months from now."""
    for c in _clusters():
        v, of = c["verdict"], c["overfit"]
        if v == "singleton+overfit":
            assert c["size"] == 1 and of, (c["signature"], c["overfit"])
        elif v == "singleton":
            assert c["size"] == 1 and not of, (c["signature"], c["overfit"])
        else:
            assert c["size"] > 1, (v, c["signature"])


def test_clusters_are_sorted_by_value():
    """Order is the reading order of the pack: biggest cluster first. A cluster
    that buys four reports sorted below one that buys two would bury the only
    actionable rows."""
    clusters = _clusters()
    keys = [(-c["size"], c["signature"]) for c in clusters]
    assert keys == sorted(keys), "clusters are no longer size-descending"


# --------------------------------------------------------------------------
# the markdown twin
# --------------------------------------------------------------------------
def test_markdown_has_one_section_per_cluster():
    md, clusters = _md(), _clusters()
    heads = re.findall(r"^### (\d+)\. ", md, re.M)
    assert len(heads) == len(clusters), (
        f"{len(heads)} sections for {len(clusters)} clusters")
    assert [int(h) for h in heads] == list(range(1, len(clusters) + 1)), (
        "cluster numbering has a gap")
    rows = re.findall(r"^\| \d+ \|", md, re.M)
    assert len(rows) == len(clusters), "summary table lost a row"


def test_headline_numbers_in_the_markdown_match_the_json():
    """The whole point of the guard: the sentence people quote must be the one
    the JSON computes. Rebuilt here with the same format specifiers the renderer
    uses, so a regenerated-but-unstale pack passes and a half-regenerated one
    does not."""
    md, s = _md(), _summary()
    assert (f"扫描 {s['total_reports']} 份 · 未覆盖 **{s['uncovered']}** 份 · "
            f"签名聚类 {s['clusters']} 个") in md
    assert f"平均覆盖 **{s['reports_per_rule']} 份**" in md
    assert f"**{s['singletons']}** 个聚类只有 1 份报告" in md
    assert f"top-{s['top_n']} 聚类合计 {s['top_n_reports']} 份 = " \
           f"**{s['top_n_share']:.0%}**" in md
    # the verdict sentence is the conclusion, so it is the worst one to leave
    # stale: it says whether writing rules is still worth doing at all
    assert ("**判据触发**：写规则不再是瓶颈。" if s["r4_fires"]
            else "判据未触发：还有值得写的成簇模式。") in md


def test_every_when_block_in_the_pack_round_trips():
    """The `when` skeletons are meant to be pasted into a draft. Checking them
    in the committed pack (not just in the renderer, which
    `test_rule_drafts.py` does) means a quoting regression cannot hide behind
    "the artifact will be regenerated later"."""
    yaml = pytest.importorskip("yaml", reason="rule packs need PyYAML")
    md, clusters = _md(), _clusters()
    blocks = re.findall(r"```yaml\n(when:\n.*?)```", md, re.S)
    expected = [c["when"] for c in clusters if c["when"]]
    assert len(blocks) == len(expected), (
        f"{len(blocks)} yaml blocks for {len(expected)} non-empty `when`s")
    for block, want in zip(blocks, expected):
        doc = yaml.safe_load(block)
        assert isinstance(doc, dict) and list(doc) == ["when"], block
        assert doc["when"] == want, f"yaml block drifted: {want} -> {doc['when']}"


# --------------------------------------------------------------------------
# cross-artifact: the part that actually detects staleness
# --------------------------------------------------------------------------
def test_pack_agrees_with_the_coverage_report():
    """Two tools, one corpus, one ruleset: `uncovered` must be the same number.

    `coverage_report.py` walks the corpus for its own reasons (bucketing), and
    `coverage.json` is regenerated whenever the coverage gate runs. If a rule is
    added and only that side is refreshed, the two artifacts disagree here --
    which is the cheapest possible alarm for "the pack is now a lie".
    """
    if not COVERAGE_PATH.exists():
        pytest.skip("corpus/coverage.json absent (run tools/coverage_report.py)")
    cov = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    s = _summary()
    assert cov["files_scanned"] == s["total_reports"], (
        "the two tools enumerate different corpora "
        f"({cov['files_scanned']} vs {s['total_reports']})")
    assert cov["totals"]["uncovered"] == s["uncovered"], (
        "corpus/coverage.json and corpus/rule-candidates.json disagree on the "
        f"uncovered count ({cov['totals']['uncovered']} vs {s['uncovered']}) -- "
        "regenerate whichever is stale with tools/suggest_rules.py --report")


def test_coverage_json_is_internally_consistent():
    """The other side of the same check. `uncovered` is not stored by
    `coverage_report.py`, it is derived as `n - diagnosed`, so a bucket row
    edited or dropped by hand would break these sums before it broke the
    cross-check above."""
    if not COVERAGE_PATH.exists():
        pytest.skip("corpus/coverage.json absent")
    cov = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    t, buckets = cov["totals"], cov["buckets"]
    assert t["n"] == sum(b["n"] for b in buckets.values())
    assert t["diagnosed"] == sum(b["diagnosed"] for b in buckets.values())
    assert t["uncovered"] == t["n"] - t["diagnosed"]
    assert t["rate"] == round(t["diagnosed"] / t["n"], 4)
    assert set(buckets) <= set(cov["bucket_order"]), (
        "a bucket row is not in the pinned order")


# --------------------------------------------------------------------------
# corpus layout assumptions the pack silently relies on
# --------------------------------------------------------------------------
def test_corpus_layout_is_flat_and_report_keys_are_unique():
    """`report` is `"<org>__<repo>/<number>"`. Two independent assumptions ride
    on that: the corpus is exactly two levels deep (so the key is unambiguous),
    and the org prefix is kept (so `sodium/3473` cannot mean two repositories).
    Dropping the org would collide -- the same repo name exists under different
    orgs in the harvested set."""
    files = sr.corpus_files()
    if not files:
        pytest.skip("harvested corpus absent (run tools/harvest_corpus.py)")
    for p in files:
        assert p.parent.parent.name == "github", f"unexpected depth: {p}"
        assert p.name.endswith(".crash.txt"), p
    keys = [f"{p.parent.name}/{p.name[:-len('.crash.txt')]}" for p in files]
    assert len(keys) == len(set(keys)), (
        "report keys collide -- the org/repo prefix is not unique")


# --------------------------------------------------------------------------
# opt-in: the real thing
# --------------------------------------------------------------------------
@pytest.mark.skipif(
    not os.environ.get("MCD_DRIFT_FULL"),
    reason="set MCD_DRIFT_FULL=1 (parses the whole corpus, ~40 s)")
def test_pack_is_byte_identical_to_a_fresh_regeneration(tmp_path):
    """What the cheap checks approximate. Run before shipping a corpus or rule
    change; the fast suite deliberately does not."""
    assert sr.main(["--report", str(tmp_path / "p.md"),
                    "--json", str(tmp_path / "p.json")]) == 0
    for fresh, committed in ((tmp_path / "p.md", MD_PATH),
                             (tmp_path / "p.json", JSON_PATH)):
        assert fresh.read_bytes() == committed.read_bytes(), (
            f"{committed.name} is stale -- rerun "
            "python tools/suggest_rules.py --report corpus/RULE_CANDIDATES.md "
            "--json corpus/rule-candidates.json")
