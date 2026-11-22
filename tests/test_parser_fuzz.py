"""The parser must survive garbage, not just the fixtures we chose.

No hypothesis dependency: the corpus is real crash text, and the failures that
matter are structural (a sliced line, a half-written stack frame, a truncated
UTF-8 run), which random mutation of a real report reproduces better than
generated strings do.

What is asserted is narrow on purpose: a malformed report may raise ValueError
(the CLI reports that as "error parsing"), but it must never raise IndexError,
KeyError, AttributeError, TypeError or RecursionError -- those are bugs in our
own indexing, not properties of the input.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from mcd.cli import diagnose

ROOT = Path(__file__).resolve().parent.parent
GT = ROOT / "tests" / "fixtures" / "ground-truth"

#: Bugs in our code, as opposed to "this text is not a crash report".
BUG_TYPES = (IndexError, KeyError, AttributeError, TypeError, RecursionError)


def _mutations(text: str, rng: random.Random, count: int) -> list[str]:
    out = []
    n = len(text)
    for _ in range(count):
        kind = rng.randrange(6)
        if kind == 0:                                  # truncate
            out.append(text[: rng.randrange(n)])
        elif kind == 1:                                # drop a slice
            i = rng.randrange(n)
            out.append(text[:i] + text[i + rng.randrange(1, 400):])
        elif kind == 2:                                # duplicate a line
            lines = text.splitlines(keepends=True)
            i = rng.randrange(len(lines))
            out.append("".join(lines[:i] + [lines[i]] + lines[i:]))
        elif kind == 3:                                # splice two offsets
            i, j = rng.randrange(n), rng.randrange(n)
            out.append(text[i:j])
        elif kind == 4:                                # flip characters
            chars = list(text)
            for _ in range(20):
                k = rng.randrange(len(chars))
                chars[k] = rng.choice("\x00\t \n[]{}()~%#")
            out.append("".join(chars))
        else:                                          # half a report, twice
            half = text[: n // 2]
            out.append(half + half)
    return out


@pytest.mark.parametrize("seed", [0, 1])
def test_mutated_reports_never_raise_our_bugs(seed: int) -> None:
    rng = random.Random(seed)
    fixture = sorted(GT.glob("*.txt"))[seed]
    text = fixture.read_text(encoding="utf-8", errors="replace")

    for mutated in _mutations(text, rng, 60):
        try:
            diagnose(None, mutated, lang="en")
        except BUG_TYPES as e:                          # pragma: no cover
            pytest.fail(f"{type(e).__name__} on a mutated report: {e!r}")
        except Exception:                               # noqa: BLE001
            pass                                        # ValueError = "not a report"


def test_empty_and_tiny_inputs_do_not_crash() -> None:
    for text in ("", "\n", "x", "-" * 5000, "Exception" * 200):
        try:
            diagnose(None, text)
        except BUG_TYPES as e:                          # pragma: no cover
            pytest.fail(f"{type(e).__name__} on {text[:20]!r}: {e!r}")
        except Exception:                               # noqa: BLE001
            pass
