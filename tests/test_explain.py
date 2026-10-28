"""`--explain`: show the arithmetic behind a suspicion score.

The tool names a mod and a confidence. Without the derivation a user can only
accept or reject the whole answer; with it they can disagree with one line
("that jar was only on the stack, it did not throw"). `Suspect.reasons` already
carried the prose but dropped the weights, so `triage(trace=...)` records them.

The load-bearing guarantee is the *other* direction: `--explain` must change
nothing when it is off. `test_default_output_is_unchanged` pins that (and 24
renders across text/markdown were compared byte-for-byte against the previous
commit when this landed).

    pytest tests/test_explain.py -v
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from mcd.cli import main
from mcd.parser.report import parse_file
from mcd.report.render import _by_reason, render_explain
from mcd.triage.attribution import triage

ROOT = Path(__file__).resolve().parent.parent
GT = ROOT / "tests" / "fixtures" / "ground-truth"
#: Committed real server crashes: one strong suspect, one two-way tie, one with
#: no suspect at all. No gitignored corpus needed.
STRONG = GT / "crash-2026-09-08_22.42.32-server.txt"       # lithium, 97%
TIE = GT / "crash-2026-09-08_22.31.14-server.txt"          # cupboard / l2screentracker
NOBODY = GT / "crash-2026-09-08_18.01.19-server.txt"       # no signal fires


def _out(capsys) -> str:
    return capsys.readouterr().out


# --- the flag does something -------------------------------------------------
def test_explain_prints_weighted_signals(capsys):
    assert main([str(STRONG), "--explain"]) == 0
    text = _out(capsys)
    assert "suspicion breakdown" in text
    assert "lithium" in text
    # a weight, the unit it is measured in, and the reason it was awarded
    assert "2.50" in text and "stack frame" in text
    assert "total evidence" in text


def test_explain_repeats_a_signal_as_a_count_not_as_rows(capsys):
    """One row per (mod, signal). Three frames from the same jar are `x3`, not
    three identical lines -- the count keeps the information, the repeat does
    not."""
    assert main([str(STRONG), "--explain"]) == 0
    text = _out(capsys)
    rows = [ln for ln in text.splitlines() if "stack frame" in ln]
    assert len(rows) == len({ln.split("  ", 1)[-1] for ln in rows}), rows


def test_explain_surfaces_a_near_tie_as_a_caveat(capsys):
    """A 50/50 split changes what the user should do next, so it belongs in the
    explanation and not only in the JSON."""
    assert main([str(TIE), "--explain"]) == 0
    text = _out(capsys)
    assert "score almost equally" in text
    assert "Remove one at a time" in text


def test_explain_without_a_suspect_says_so(capsys):
    assert main([str(NOBODY), "--explain"]) == 0
    assert "no mod was implicated" in _out(capsys)


# --- and nothing else changes ------------------------------------------------
def test_default_output_is_unchanged(capsys):
    assert main([str(STRONG)]) == 0
    text = _out(capsys)
    assert "suspicion breakdown" not in text
    assert "total evidence" not in text


def test_explain_cannot_be_combined_with_json(capsys):
    """Appending prose after a JSON document makes `json.load` fail on the
    tool's own output -- refuse loudly instead."""
    assert main([str(STRONG), "--explain", "--json"]) == 2
    err = capsys.readouterr().err
    assert "--explain cannot be combined with --json" in err


def test_trace_is_observational_only():
    """Recording weights must not change the answer."""
    rep = parse_file(STRONG)
    plain = triage(rep)
    traced: dict = {}
    with_trace = triage(rep, trace=traced)
    assert [(s.modid, s.score, s.confidence) for s in plain.suspects] == \
           [(s.modid, s.score, s.confidence) for s in with_trace.suspects]
    assert traced, "the trace should have collected something"


# --- rendering details -------------------------------------------------------
def test_by_reason_sums_duplicates_and_sorts_by_weight():
    rows = [(3.0, "jar on the path"), (3.0, "jar on the path"),
            (12.0, "the report's own line"), (2.5, "frame #2")]
    assert _by_reason(rows) == [
        (12.0, 1, "the report's own line"),
        (6.0, 2, "jar on the path"),
        (2.5, 1, "frame #2"),
    ]


def test_markdown_table_escapes_pipes_in_reasons():
    """A reason can quote a report string, and report strings contain pipes."""
    fake = SimpleNamespace(
        suspects=[SimpleNamespace(modid="m", score=3.0, confidence=0.5)],
        notes=[], unresolved_modids=[])
    buf = io.StringIO()
    render_explain(fake, {"m": [(3.0, "message 'a|b' from m")]}, buf, markdown=True)
    text = buf.getvalue()
    assert "| weight | n | signal |" in text
    assert "a\\|b" in text
    # every table row must still have exactly three cells
    rows = [ln for ln in text.splitlines() if ln.startswith("| ")
            and not ln.startswith("| weight")]
    assert all(ln.count("|") - ln.count("\\|") == 4 for ln in rows), rows
