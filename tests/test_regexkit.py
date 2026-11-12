"""The regex prefilter must never skip a pattern that would have matched.

`mcd/regexkit.py` extracts a literal substring from a pattern and skips the
regex when that substring is absent. It is a 20 %-faster corpus run when the
extraction is right and a silent loss of findings when it is wrong -- which is
what happened while writing it: the first version cost 66 findings because it
treated a prefix before `|` as required, and 44 more because it stopped walking
at a `(` and never saw the alternation after it.

So the property is tested directly, against the real patterns and real text:
**if the regex matches, the literal must be in the text.** No sampling of
behaviour, no "looks right" -- the invariant the optimisation depends on.

    pytest tests/test_regexkit.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcd.parser.platform import LAUNCHER_PROBES, PROBES
from mcd.regexkit import MIN_LITERAL, literal_prefix
from mcd.rules.engine import RuleSet

ROOT = Path(__file__).resolve().parent.parent


# --- extraction rules -------------------------------------------------------
@pytest.mark.parametrize("pattern,expected", [
    (r"net\.neoforged", "net.neoforged"),          # escaped dots are literal
    (r"Loading Minecraft", "loading minecraft"),    # lowercased
    (r"git-Magma", "git-magma"),                    # hyphen is literal outside a class
    (r"\bbukkit\b", ""),                            # anchor escape: cannot prove
    (r"^\s*Prism", ""),                             # anchor
    (r"a.b", ""),                                   # too short after the dot
    (r"foo|bar", ""),                               # alternation: neither is required
    (r"Attempted to load class ([\w/$]+)|NoClassDef", ""),   # alternation after a group
    (r"ab?cdef", ""),                               # quantifier: `b` is optional
    (r"[abc]def", ""),                              # character class first
    (r"invalid JSON5?|Not enough", ""),             # alternation, not a literal run
])
def test_literal_extraction(pattern, expected):
    assert literal_prefix(pattern) == expected


def test_short_literals_are_rejected():
    assert literal_prefix("ab") == ""
    assert literal_prefix("abc") == ""
    assert len(literal_prefix("abcd")) == MIN_LITERAL


# --- the invariant ----------------------------------------------------------
def _rule_patterns() -> list[str]:
    out: list[str] = []
    for rule in RuleSet.load().rules:
        for value in (rule.when or {}).values():
            if isinstance(value, list):
                out.extend(p for p in value if isinstance(p, str))
    return out


def _probe_patterns() -> list[str]:
    return [p.pattern.pattern for p in PROBES + LAUNCHER_PROBES]


def _sample_texts(limit: int = 24) -> list[str]:
    """Real reports, biggest and smallest included: the prefilter's whole point
    is large files, and a sample of only small ones would not exercise it."""
    files = sorted((ROOT / "corpus/github").rglob("*.crash.txt"),
                   key=lambda p: p.stat().st_size)
    if not files:
        pytest.skip("corpus/github is empty (gitignored on fresh clones)")
    picked = files[:limit // 2] + files[-(limit // 2):]
    return [p.read_text(encoding="utf-8", errors="replace") for p in picked]


@pytest.mark.parametrize("source", ["rules", "probes"])
def test_literal_is_present_in_every_matching_text(source):
    """If `re.search` finds the pattern, `literal_prefix` must be in the text.

    A failure here means `regexkit` would skip a real match -- the exact bug
    class this file exists to prevent.
    """
    patterns = _rule_patterns() if source == "rules" else _probe_patterns()
    texts = _sample_texts()
    checked = 0
    for pattern in patterns:
        lit = literal_prefix(pattern)
        if not lit:
            continue
        rx = re.compile(pattern, re.I | re.M)
        for text in texts:
            if rx.search(text):
                assert lit in text.lower(), (
                    f"{lit!r} is not required by {pattern!r} -- the prefilter "
                    f"would drop a real match")
                checked += 1
    assert checked > 0, f"no matches exercised for {source}; sample too small"


def test_every_probe_or_rule_pattern_still_compiles():
    for p in _rule_patterns() + _probe_patterns():
        re.compile(p)
