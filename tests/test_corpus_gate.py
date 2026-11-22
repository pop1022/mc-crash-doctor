"""The extended gate must announce itself, in both directions.

A green summary over 42 silent skips is the failure mode; these tests pin the
wording and the classification, not the pytest plumbing (which was verified by
running the public tree: 740 passed, 45 skipped, exit 0, "NOT RUN" printed).
"""
from __future__ import annotations

from pathlib import Path

import _corpus_gate as g


def test_a_checkout_without_the_corpus_says_not_run(monkeypatch) -> None:
    monkeypatch.setattr(g, "texts", lambda: [])
    line = g.summary_line(42)
    assert "extended gate: NOT RUN" in line
    assert "42 corpus case(s) skipped" in line
    assert "not a green" in line


def test_a_checkout_with_the_corpus_says_ran(monkeypatch) -> None:
    monkeypatch.setattr(g, "texts", lambda: [Path("a.crash.txt"), Path("b.crash.txt")])
    line = g.summary_line(0)
    assert "extended gate: RAN" in line
    assert "2 crash texts" in line


def test_existing_skip_wording_is_recognised() -> None:
    assert g.is_corpus_skip("harvested corpus absent (run tools/harvest_corpus.py)")
    assert g.is_corpus_skip(f"{g.MARKER}: extended gate NOT RUN")
    assert not g.is_corpus_skip("set MCD_DRIFT_FULL=1 (parses the whole corpus)")
    assert not g.is_corpus_skip("No module named 'rich'")
