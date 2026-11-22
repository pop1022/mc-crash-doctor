"""Corpus availability: the public PR gate vs the private extended gate.

corpus/github/**/*.crash.txt is scraped user content and is not shipped. A
checkout without it can still run everything that matters for a pull request,
but it must say out loud that the corpus-dependent cases did not run. The
failure this prevents is a suite that is green because 42 tests quietly skipped.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "github"

#: Session summary prefix. Both the conftest and the docs use this string, so a
#: reader can grep a CI log for "extended gate".
GATE = "extended gate"

#: Reasons that mean "the check did not run because the data is not here".
#: Kept as substrings so existing tests do not have to be rewritten to import
#: anything; new tests should use MARKER directly.
MARKER = "private corpus absent"
ABSENT_HINTS = ("harvested corpus absent", MARKER, "corpus text not in this checkout")


def texts() -> list[Path]:
    if not CORPUS.is_dir():
        return []
    return sorted(CORPUS.rglob("*.crash.txt"))


def has_corpus() -> bool:
    return bool(texts())


def is_corpus_skip(reason: str) -> bool:
    return any(h in reason for h in ABSENT_HINTS)


def summary_line(skipped: int) -> str:
    """One line, either way -- silence is the thing being fixed."""
    n = len(texts())
    if n:
        return (f"{GATE}: RAN -- {n} crash texts on disk, "
                f"{skipped} corpus case(s) skipped")
    return (f"{GATE}: NOT RUN -- corpus/github is not in this checkout; "
            f"{skipped} corpus case(s) skipped. This is not a green extended gate.")
