"""Rule config warnings: keys that load fine, change behaviour, and say nothing.

WHEN_KEYS covers the builtin packs (tests/test_rule_metadata.py). This file
covers the half that guard cannot reach -- what happens to a *user's* rule
directory when a key is misspelled.

Measured before the fix (tmp/unknown_key_probe.py):
    typo.when-key  (when: {exceptions: [...]}, meant `exception:`)  fired 4/4
    typo.fix-key   (fix: [...] instead of fixes:)   fired with 0 fix steps
    typo.top-key   (explaination: instead of explanation:)  fired, explanation ""
and RuleSet.errors was empty in all three cases.

The dangerous one is the first: `evaluate_rule` skips keys it does not know, so
a `when` block whose keys are all unknown still passes the non-empty check and
has no condition left to fail -- the rule becomes a catch-all and fires on
every report.

    pytest tests/test_rule_config_warnings.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file  # noqa: E402
from mcd.rules.engine import RULE_KEYS, WHEN_KEYS, RuleSet, run_rules  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/synthetic/oom-save-time.txt"


def _write_lf(path: Path, text: str) -> None:
    """3.9-compatible LF write: Path.write_text(newline=) is 3.10+."""
    path.write_bytes(text.encode("utf-8"))


def _load(tmp_path: Path, rules_yaml: str) -> RuleSet:
    """Write a one-file rule dir and load it (builtin packs included)."""
    d = tmp_path / "rules"
    d.mkdir()
    _write_lf(d / "t.yml", rules_yaml)
    return RuleSet.load([str(d)])


def _rule(rid: str, *, when: str, extra: str = "") -> str:
    return (
        "rules:\n"
        f"  - id: {rid}\n"
        f'    title: "{rid}"\n'
        "    lifecycle_status: experimental\n"
        f"    when:\n      {when}\n"
        f'    fixes: ["do the thing"]\n'
        + (f"    {extra}\n" if extra else "")
    )


def _fires(rs: RuleSet, rid: str) -> bool:
    rep = parse_file(FIXTURE)
    return any(f.rule_id == rid for f in run_rules(rep, rs))


# --- the noise floor -------------------------------------------------------

def test_shipped_packs_produce_no_config_warnings():
    """The 41 builtin rules must be silent: a warning per load would train
    everyone to ignore the channel before a user dir ever needs it."""
    assert RuleSet.load().errors == []


# --- unknown top-level keys ------------------------------------------------

def test_unknown_top_level_key_warns(tmp_path):
    rs = _load(tmp_path, _rule("t.fix", when='exception: ["OutOfMemoryError"]',
                               extra='fix: ["singular"]'))
    assert any("t.fix" in e and "['fix']" in e for e in rs.errors), rs.errors


def test_typo_fix_key_loses_every_repair_step_but_still_fires(tmp_path):
    """Documents the damage, not just the warning: the rule matches and tells
    the user what went wrong, then hands them nothing to do about it."""
    rs = _load(tmp_path, (
        "rules:\n"
        "  - id: t.fix\n"
        '    title: "t.fix"\n'
        "    lifecycle_status: experimental\n"
        '    when:\n      exception: ["OutOfMemoryError"]\n'
        "    explanation: the heap ran out\n"
        '    fix: ["singular"]\n'
    ))
    rep = parse_file(FIXTURE)
    hit = [f for f in run_rules(rep, rs) if f.rule_id == "t.fix"]
    assert len(hit) == 1
    assert hit[0].fixes == []
    assert hit[0].explanation == "the heap ran out"


def test_unknown_top_level_key_is_not_in_the_known_set():
    """RULE_KEYS is the loader's own list; the singular spelling must stay out
    of it, or this whole file proves nothing."""
    assert "fix" not in RULE_KEYS
    assert "fixes" in RULE_KEYS


# --- unknown `when` keys ---------------------------------------------------

def test_all_unknown_when_keys_warns_about_matching_everything(tmp_path):
    rs = _load(tmp_path, _rule("t.when", when='exceptions: ["OutOfMemoryError"]'))
    msgs = [e for e in rs.errors if "t.when" in e]
    assert msgs, rs.errors
    assert "EVERY report" in msgs[0]


def test_all_unknown_when_keys_no_longer_match(tmp_path):
    """The regression that matters. Written to match OOM via a typo'd key, the
    rule fired on 4/4 synthetic fixtures -- i.e. on reports with no OOM at all.
    A `when` block with nothing the engine reads must match nothing, exactly
    like an empty one."""
    rs = _load(tmp_path, _rule("t.when", when='exceptions: ["OutOfMemoryError"]'))
    assert not _fires(rs, "t.when")


def test_correctly_spelled_rule_still_fires(tmp_path):
    """Control for the test above: the only difference is the key name."""
    rs = _load(tmp_path, _rule("t.when", when='exception: ["OutOfMemoryError"]'))
    assert _fires(rs, "t.when")
    assert not rs.errors


def test_partial_when_typo_keeps_the_valid_conditions(tmp_path):
    """A typo alongside a good condition must not disable the good one, and the
    warning has to say so -- otherwise the author cannot tell whether their
    rule still does anything."""
    rs = _load(tmp_path, _rule(
        "t.mixed",
        when='text: ["OutOfMemoryError"]\n      exceptions: ["Nope"]'))
    msgs = [e for e in rs.errors if "t.mixed" in e]
    assert msgs and "still apply" in msgs[0], rs.errors
    assert _fires(rs, "t.mixed")


def test_when_key_typo_alone_is_reported_once(tmp_path):
    """One warning per problem, not one per rule per condition."""
    rs = _load(tmp_path, _rule("t.once", when='exceptions: ["A"]\n      msgg: ["B"]'))
    assert len([e for e in rs.errors if "t.once" in e]) == 1, rs.errors


# --- malformed entries -----------------------------------------------------

def test_rule_entry_that_is_not_a_mapping_does_not_abort_the_load(tmp_path):
    """`- just a string` under `rules:` used to escape the per-rule handler
    (AttributeError is not in its except tuple) and take the whole load down."""
    rs = _load(tmp_path, (
        "rules:\n"
        "  - just a string\n"
        + _rule("t.good", when='exception: ["OutOfMemoryError"]')[len("rules:\n"):]
    ))
    assert "t.good" in [r.id for r in rs.rules]
    assert any("not a mapping" in e for e in rs.errors), rs.errors


# --- strict ----------------------------------------------------------------

def test_strict_promotes_a_config_warning_to_an_error(tmp_path):
    """strict is per-call and must see the new warnings. Config mistakes are
    exactly what a CI running --strict is there to catch."""
    d = tmp_path / "rules"
    d.mkdir()
    _write_lf(d / "t.yml", _rule("t.when", when='exceptions: ["X"]'))
    RuleSet.load([str(d)])                       # populate the cache non-strict
    with pytest.raises(ValueError, match="unknown condition"):
        RuleSet.load([str(d)], strict=True)


# --- the two key sets agree with reality -----------------------------------

def test_when_keys_matches_what_evaluate_rule_reads():
    """A key added to WHEN_KEYS but never read would silence a typo; a key read
    but missing from WHEN_KEYS would warn on a working rule. Pin both."""
    import inspect

    import mcd.rules.engine as eng

    # The AND half moved into _evaluate_all when when_any was added, so the
    # guard has to read both bodies: a key is "read" if either function names it.
    src = inspect.getsource(eng.evaluate_rule) + inspect.getsource(eng._evaluate_all)
    for key in sorted(WHEN_KEYS):
        assert f'"{key}"' in src, f"WHEN_KEYS lists {key!r} but nothing reads it"
