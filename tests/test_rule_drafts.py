"""The guard rail around `corpus/rule-drafts/` (ROADMAP 1E.3).

The rule for LLM-assisted drafting is "model output never reaches `builtin/`".
That sentence is worth exactly as much as the code that refuses it, so:

* `tools/suggest_rules.py --ingest` is the only door in, and it validates before
  copying;
* this file re-checks every draft that is already on disk -- because a file can
  be added by `git add` without ever passing through the door;
* `test_no_draft_rule_is_in_builtin` (in test_rule_metadata.py) covers the other
  direction: a draft that somebody moved into the shipped packs.

Everything here is offline. The tests skip the corpus-dependent checks when the
harvested fragments are absent, which is the normal CI case.

    pytest tests/test_rule_drafts.py -v
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="rule packs need PyYAML")

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "corpus" / "rule-drafts"
GITHUB = ROOT / "corpus" / "github"

_spec = importlib.util.spec_from_file_location(
    "suggest_rules", ROOT / "tools" / "suggest_rules.py")
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

from mcd.rules.engine import LIFECYCLE_STATES, Rule, RuleSet  # noqa: E402


def _draft_files() -> list[Path]:
    return sorted(DRAFTS.glob("*.yaml")) + sorted(DRAFTS.glob("*.yml"))


def _docs() -> list[tuple[Path, dict]]:
    return [(p, yaml.safe_load(p.read_text(encoding="utf-8")))
            for p in _draft_files()]


def test_draft_directory_is_not_empty():
    """If the directory is empty, every other test here passes vacuously. This
    one fails so the suite says out loud that the guard is not guarding."""
    assert _draft_files(), (
        "corpus/rule-drafts/ is empty -- the ingest path is untested; "
        "run tools/suggest_rules.py --report to see what is available")


def test_every_draft_declares_a_model_and_a_date():
    for path, doc in _docs():
        gen = (doc or {}).get("generated_by")
        assert isinstance(gen, dict), f"{path.name}: no generated_by block"
        assert gen.get("model"), f"{path.name}: generated_by.model missing"
        assert gen.get("date"), f"{path.name}: generated_by.date missing"
        assert str(gen["date"])[:4].isdigit(), (
            f"{path.name}: generated_by.date {gen['date']!r} is not a date")


def test_every_draft_rule_is_lifecycle_draft():
    """A candidate may not enter at any stage above `draft`: promotion to
    verified is a human act backed by evidence, not a property of generation."""
    for path, doc in _docs():
        for rule in doc.get("rules") or []:
            status = rule.get("lifecycle_status")
            assert status in LIFECYCLE_STATES, (
                f"{path.name}/{rule.get('id')}: {status!r} is not a lifecycle state")
            assert status == "draft", (
                f"{path.name}/{rule.get('id')}: candidates must be 'draft', "
                f"got {status!r}")


def test_candidate_ids_cannot_be_confused_with_shipped_ids():
    builtin = {r.id for r in RuleSet.load().rules}
    for path, doc in _docs():
        for rule in doc.get("rules") or []:
            rid = str(rule.get("id", ""))
            assert rid.startswith(sr.CANDIDATE_PREFIX), (
                f"{path.name}: id {rid!r} must start with {sr.CANDIDATE_PREFIX!r}")
            assert rid not in builtin, f"{path.name}: {rid} shadows a shipped rule"


def test_every_candidate_fixture_resolves():
    """A candidate that cites nothing is untestable; one that cites a report
    which does not exist is worse, because it looks testable."""
    missing = []
    for path, doc in _docs():
        for rule in doc.get("rules") or []:
            fxs = (rule.get("provenance") or {}).get("fixtures") or []
            if not fxs:
                missing.append(f"{path.name}/{rule.get('id')}: no fixtures")
            for fx in fxs:
                if not sr._fixture_exists(fx):
                    missing.append(f"{path.name}/{rule.get('id')}: {fx!r}")
    assert not missing, f"unresolvable fixtures: {missing}"


def test_drafts_load_without_touching_the_shipped_rules():
    """Loading `corpus/rule-drafts/` must add rules, never replace or shadow a
    builtin one. If a draft id collided, `RuleSet.load` would keep whichever it
    saw first and the shipped behaviour would change silently."""
    base = RuleSet.load()
    extended = RuleSet.load(extra_dirs=[DRAFTS])
    base_ids = {r.id for r in base.rules}
    ext_ids = {r.id for r in extended.rules}
    assert base_ids <= ext_ids
    added = ext_ids - base_ids
    assert all(i.startswith(sr.CANDIDATE_PREFIX) for i in added), added
    assert not (extended.errors or []), f"load errors: {extended.errors}"


def test_rendered_when_skeletons_parse_as_yaml():
    """The pack's `when` snippets are meant to be pasted into a draft, so a
    quoting mistake turns 107 suggestions into 107 YAML errors.

    Checked here on a synthetic cluster set, because this file's subject is the
    *renderer*: a hostile message must not be able to break the output. The
    committed pack is checked separately, by
    `tests/test_rule_candidates.py::test_every_when_block_in_the_pack_round_trips`
    -- that guard was added with the pack's drift guard, so "the artifact will
    be regenerated later" is no longer the only thing standing behind it.
    """
    uncovered = [
        {"report": "repo/1", "kind": "java.lang.Throwable",
         "message": "Manually triggered debug crash",
         "description": "Manually triggered debug crash",
         "bucket": "other", "signature": "java.lang.Throwable: a"},
        {"report": "repo/2", "kind": "a.b.C",
         "message": 'quotes "and" it\'s \u4e2d\u6587: 12',
         "description": '', "bucket": "other",
         "signature": "a.b.C: quotes"},
    ]
    clusters = sr.build_clusters(uncovered)
    md = sr.render_md(sr.summarise(uncovered, clusters), clusters)
    blocks = re.findall(r"```yaml\n(when:\n.*?)```", md, re.S)
    assert len(blocks) == len(clusters)
    for b in blocks:
        doc = yaml.safe_load(b)
        assert isinstance(doc.get("when"), dict) and doc["when"], b


def test_overfit_markers_are_detected():
    """A `when` built by escaping a UUID or a coordinate can only ever match the
    report it came from; the pack has to say so."""
    assert "uuid" in sr.overfit_markers("id 3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    assert "long number" in sr.overfit_markers("Index 1234 out of bounds")
    assert "path" in sr.overfit_markers(r"open C:\Users\me\.minecraft\config")
    assert sr.overfit_markers("Manually triggered debug crash") == []


def _resolve_pin(name: str) -> Path | None:
    """`sodium/3473` -> corpus path. Same suffix rule as test_gaps.py."""
    parts = str(name).split("/")
    if len(parts) < 2 or not parts[-1].isdigit():
        return None
    hits = sorted(GITHUB.glob(f"*__{parts[-2]}/{parts[-1]}.crash.txt"))
    return hits[0] if hits else None


def test_candidate_fires_on_the_reports_it_cites():
    """The claim a draft makes is "this cluster looks like this". Check it.

    Only the cited reports are parsed here. The corpus-wide version of this
    check -- "does it fire on anything at all" -- already runs at admission
    (`suggest_rules.py --ingest`), which is the moment it matters; re-parsing
    454 reports on every commit would add 30 s to the gate to re-answer a
    question that cannot change unless someone edits the draft.
    """
    if not GITHUB.is_dir():
        pytest.skip("harvested corpus absent")
    from mcd.parser.report import parse_file
    from mcd.rules.engine import run_rules

    for path, doc in _docs():
        for rule in doc.get("rules") or []:
            rid = rule["id"]
            one = RuleSet([Rule.from_dict(rule, source=path.name)])
            cited = [c for c in (rule["provenance"]["fixtures"] or [])]
            checked = 0
            for fx in cited:
                pin = _resolve_pin(fx)
                if pin is None:
                    continue
                checked += 1
                ids = [f.rule_id for f in run_rules(parse_file(pin), one)]
                assert rid in ids, f"{rid}: does not fire on its own pin {fx}"
            assert checked, f"{rid}: none of its fixtures resolve to a report"
