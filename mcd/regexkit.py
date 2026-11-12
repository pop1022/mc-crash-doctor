"""Small helpers shared by the places that run thousands of regexes.

Both the platform probes and the rule engine search many patterns against the
same text, and in both cases most patterns cannot match. A literal substring
check (`str.find`, C speed) is one to two orders of magnitude cheaper than
`re.search`, so it is worth extracting a *guaranteed* substring from a pattern
and using it as a prefilter.

The extraction is deliberately timid: it returns "" whenever it cannot prove a
substring is required. A false "" costs one extra regex search; a false literal
would skip a real match, so every ambiguity resolves to "no prefilter".
"""
from __future__ import annotations

import re
from functools import lru_cache

#: Regex metacharacters that end the literal prefix.
_SPECIAL = frozenset(".^$*+?()[]{}|")

#: Quantifiers apply to the character before them, so that character
#: cannot be part of a guaranteed literal.
_QUANTIFIERS = frozenset("?*+{")

#: Minimum length worth filtering on. Shorter strings appear everywhere and the
#: `find` would rarely reject anything.
MIN_LITERAL = 4


def _has_alternation(pattern: str) -> bool:
    """True when `pattern` contains an unescaped `|`.

    Character classes are not special-cased: treating `[a|b]` as alternation
    only forfeits a prefilter, which is the safe direction.
    """
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if c == "|":
            return True
        i += 1
    return False


@lru_cache(maxsize=512)
def literal_prefix(pattern: str) -> str:
    """The lowercase literal that *every* match of `pattern` must contain.

    Only the prefix is considered, which is the conservative choice: a literal
    after a metacharacter may sit in an optional group or one branch of an
    alternation, and is therefore not guaranteed. Escaped metacharacters
    (``\\.``, ``\\-``) are literal and kept; class/anchor escapes (``\\b``,
    ``\\d``) are not, and stop the walk.

    Returns "" when nothing of length >= MIN_LITERAL can be proved.
    """
    # An alternation anywhere -- including after a group we stopped at -- means
    # the other branch need not contain the prefix. `Attempted to load class
    # ([\\w/$]+)|NoClassDefFoundError` is exactly that shape, and checking only
    # the characters walked so far missed it (44 findings on the corpus).
    if _has_alternation(pattern):
        return ""

    out: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            nxt = pattern[i + 1] if i + 1 < len(pattern) else ""
            if nxt and not nxt.isalnum():
                out.append(nxt)
                i += 2
                continue
            break
        if c == "|":
            # A branch need not contain anything before it: `foo|bar` matches
            # text that never contains "foo". Measured the hard way -- an
            # earlier version of this function cost 66 findings on the corpus.
            return ""
        if c in _QUANTIFIERS:
            # `ab?c` matches "ac", so `b` is not required either.
            out = out[:-1]
            break
        if c in _SPECIAL:
            break
        out.append(c)
        i += 1
    literal = "".join(out)
    return literal.lower() if len(literal) >= MIN_LITERAL else ""


@lru_cache(maxsize=512)
def compiled(pattern: str) -> re.Pattern[str]:
    """`re.compile(pattern, re.I | re.M)`, memoised.

    `re` caches internally too, but the lookup happens on every call and the
    corpus exercises this ~500k times; an lru_cache hit is cheaper and keeps the
    flags in one place.
    """
    return re.compile(pattern, re.I | re.M)


__all__ = ["literal_prefix", "compiled", "MIN_LITERAL"]
