"""Coverage-bucket contract (ROADMAP 1D.4).

`corpus/COVERAGE.md` is the document that decides what the next rule should be,
so its taxonomy has to be a property of the reports rather than a restatement of
what the rules already do. Two ways that can silently break:

  1. **Circularity.** If a bucket were derived from "which rule fired", the
     `other` bucket would absorb exactly the reports with no rule, the report
     would tautologically agree with itself, and "what is missing" would be
     unanswerable.
  2. **Vocabulary instead of failure.** The first `_world_data` predicate matched
     bare `chunk ` / `anvil` / `corrupt`, which appear in ordinary class names
     (`LevelChunk`, `AnvilChunkLoader`). It reported 140 of 454 reports as
     "world data"; the true figure is under 20.

What is pinned here:

  1. bucket order, and that `other` is the last and only unconditional bucket;
  2. `oom` outranks `mod-loading` when both apply;
  3. classification is independent of rule output (patching `run_rules` changes
     nothing);
  4. class-name vocabulary alone does not decide a bucket;
  5. every bucket name is a valid return value, and `BUCKET_ABSENCE` has no
     stale keys.

    pytest tests/test_coverage_buckets.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "coverage_report", ROOT / "tools" / "coverage_report.py"
)
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)


# --------------------------------------------------------------------------
# stubs -- classification reads only these attributes
# --------------------------------------------------------------------------
def frame(cls: str = "", *, minecraft: bool = False, forge: bool = False):
    return SimpleNamespace(cls=cls, is_minecraft=minecraft, is_forge=forge)


def exc(kind: str, *frames):
    return SimpleNamespace(kind=kind, frames=list(frames))


def rep(*exceptions, loader: str = "neoforge"):
    return SimpleNamespace(
        exceptions=list(exceptions),
        system=SimpleNamespace(loader=loader),
    )


def kind_of(text: str, report) -> str:
    return cov.classify(text, report)


# --------------------------------------------------------------------------
# order is the contract
# --------------------------------------------------------------------------
def test_other_is_last_and_unconditional():
    """`other` must be reachable for any input, so nothing may follow it."""
    names = [b[0] for b in cov.BUCKETS]
    assert names[-1] == "other", f"`other` must stay last, got {names}"
    other = dict((b[0], b[1]) for b in cov.BUCKETS)["other"]
    assert other("", rep()) is True
    assert other("anything at all", rep()) is True


def test_no_duplicate_bucket_names():
    names = [b[0] for b in cov.BUCKETS]
    assert len(names) == len(set(names))


def test_bucket_names_matches_buckets():
    assert cov.BUCKET_NAMES == tuple(b[0] for b in cov.BUCKETS)


def test_order_is_pinned():
    """A reordering changes every number in COVERAGE.md; make it deliberate."""
    assert cov.BUCKET_NAMES == (
        "oom", "watchdog", "mixin", "native", "mod-loading",
        "plugin", "world-data", "mod-bug", "other",
    )


def test_oom_outranks_mod_loading():
    """An OOM during loading is an OOM: that is the thing the user must fix."""
    report = rep(exc("java.lang.OutOfMemoryError",
                     frame("net.neoforged.fml.ModLoader")))
    text = "java.lang.OutOfMemoryError: Java heap space\nMod loading has failed"
    assert kind_of(text, report) == "oom"


def test_watchdog_outranks_world_data():
    report = rep(exc("java.lang.RuntimeException", frame("net.minecraft.Foo")))
    assert kind_of("server has not responded, state: ticking entity",
                   report) == "watchdog"


# --------------------------------------------------------------------------
# circularity guard
# --------------------------------------------------------------------------
def test_classification_ignores_rule_output(monkeypatch):
    """Patching the rule engine must not move a single report between buckets."""
    text = "java.lang.NullPointerException at com.examplemod.Foo.bar(Foo.java:1)"
    report = rep(exc("java.lang.NullPointerException",
                     frame("com.examplemod.Foo")))
    before = kind_of(text, report)

    monkeypatch.setattr(cov, "run_rules", lambda *_a, **_k: [object()] * 99)
    after = kind_of(text, report)
    assert before == after


def test_classify_takes_no_findings_argument():
    """Structurally: if it cannot see findings, it cannot depend on them."""
    import inspect

    params = list(inspect.signature(cov.classify).parameters)
    assert params == ["text", "rep"], params


# --------------------------------------------------------------------------
# vocabulary must not decide a bucket
# --------------------------------------------------------------------------
def test_class_name_vocabulary_is_not_a_failure_signal():
    """`AnvilChunkLoader` in a stack trace says nothing about world corruption."""
    report = rep(exc("java.lang.NullPointerException",
                     frame("com.examplemod.Foo")),
                 loader="neoforge")
    text = (
        "at net.minecraft.world.level.chunk.storage.AnvilChunkLoader.save("
        "AnvilChunkLoader.java:1)\n"
        "at net.minecraft.world.level.chunk.LevelChunk.setBlockState("
        "LevelChunk.java:2)\n"
        "description: corrupt aura\n"
    )
    assert kind_of(text, report) != "world-data"


def test_real_world_signals_still_fire():
    report = rep(exc("java.lang.RuntimeException", frame("net.minecraft.Foo")))
    assert kind_of("ticking entity: minecraft:zombie", report) == "world-data"
    assert kind_of("error loading chunk 12,-3", report) == "world-data"


def test_fabric_formatted_exception_counts_as_loading():
    """Fabric wraps "your mod set did not resolve" in FormattedException."""
    report = rep(exc("net.fabricmc.loader.impl.FormattedException",
                     frame("net.fabricmc.loader.impl.FormattedException")))
    assert kind_of("some of your mods are incompatible", report) == "mod-loading"


# --------------------------------------------------------------------------
# throw-site attribution
# --------------------------------------------------------------------------
def test_mod_throw_site_means_mod_bug():
    report = rep(exc("java.lang.NullPointerException",
                     frame("com.examplemod.Foo", minecraft=False)))
    assert kind_of("", report) == "mod-bug"


def test_platform_throw_site_is_not_a_mod_bug():
    report = rep(exc("java.lang.NullPointerException",
                     frame("net.minecraft.world.level.Level")))
    assert kind_of("", report) != "mod-bug"


def test_deepest_cause_decides_not_the_top_level_wrapper():
    """A mod calling vanilla code that throws is a vanilla throw site."""
    report = rep(
        exc("java.lang.RuntimeException",              # top level
            frame("com.examplemod.Foo")),
        exc("java.lang.NullPointerException",          # deepest cause
            frame("net.minecraft.world.level.Level")),
    )
    assert kind_of("", report) != "mod-bug"


def test_no_frames_is_not_a_mod_bug():
    """An unparseable report must not be blamed on a mod."""
    assert kind_of("", rep(exc("java.lang.RuntimeException"))) != "mod-bug"
    assert kind_of("", rep()) != "mod-bug"


# --------------------------------------------------------------------------
# totality and bookkeeping
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text, report", [
    ("", rep()),
    ("garbage", rep(exc("", frame("")))),
    ("java.lang.OutOfMemoryError", rep(exc("java.lang.OutOfMemoryError"))),
    ("x", rep(loader="paper")),
])
def test_classify_is_total(text, report):
    assert kind_of(text, report) in cov.BUCKET_NAMES


def test_absence_notes_reference_real_buckets():
    """A renamed bucket would leave an orphan explanation nobody sees."""
    stale = set(cov.BUCKET_ABSENCE) - set(cov.BUCKET_NAMES)
    assert not stale, f"BUCKET_ABSENCE has stale keys: {stale}"


def test_every_absence_note_explains_something():
    for name, why in cov.BUCKET_ABSENCE.items():
        assert why.strip(), f"{name} has an empty explanation"


# --------------------------------------------------------------------------
# the rendered document
# --------------------------------------------------------------------------
def _result(buckets: dict[str, tuple[int, int]]) -> dict:
    rows = {
        name: {"n": n, "diagnosed": d, "severe": d, "verdict_known": 0}
        for name, (n, d) in buckets.items()
    }
    total = sum(n for n, _d in buckets.values())
    diag = sum(d for _n, d in buckets.values())
    return {
        "generated_at": "2026-01-01T00:00:00+0000",
        "files_scanned": total,
        "parse_errors": 0,
        "parse_error_examples": [],
        "totals": {"n": total, "diagnosed": diag,
                   "rate": diag / total if total else 0.0,
                   "uncovered": total - diag},
        "buckets": rows,
        "bucket_order": list(cov.BUCKET_NAMES),
        "uncovered_signatures": [],
        "uncovered_verdicts": {},
        "loaders": {"fabric": total},
        "elapsed_seconds": 0.0,
    }


def test_summary_ranks_other_with_everything_else():
    """`other` holds the biggest gap in practice; hiding it flatters the report."""
    md = cov.render_md(_result({
        "mod-bug": (100, 90),        # 10 missing
        "other": (60, 10),           # 50 missing -- the real answer
        "mixin": (40, 39),           # 1 missing
    }))
    gap_line = next(l for l in md.splitlines() if l.startswith("未覆盖绝对数最大"))
    assert "`other` 50" in gap_line, gap_line
    assert gap_line.index("`other`") < gap_line.index("`mod-bug`"), gap_line


def test_empty_buckets_are_rendered_not_omitted():
    """A missing row reads as "covered or irrelevant"; a 0 is a measured fact."""
    md = cov.render_md(_result({"mod-bug": (10, 5)}))
    for name in cov.BUCKET_NAMES:
        assert f"| `{name}`" in md, f"bucket `{name}` vanished from the table"
    assert "空桶" in md


def test_section_numbers_have_no_gap_when_parse_errors_are_empty():
    """The normal case is zero parse errors; it must not leave a hole in 五、."""
    md = cov.render_md(_result({"mod-bug": (10, 5)}))
    heads = [l for l in md.splitlines() if l.startswith("## ")]
    nums = [h[3] for h in heads]
    assert nums == list("一二三四五"), heads


def test_undecidable_share_is_stated_not_implied():
    """84% of uncovered issues have no maintainer label; say so explicitly.

    Without this sentence the section reads as "the gaps are unexplainable",
    which is the opposite of what the data supports.
    """
    result = _result({"mod-bug": (10, 5)})
    result["uncovered_verdicts"] = {"(none)": 4, "bug_in_this_mod": 1}
    md = cov.render_md(result)
    line = next(l for l in md.splitlines() if l.startswith("**这项检查对"))
    assert "80%" in line, line
    assert "不能读成" in line, line
