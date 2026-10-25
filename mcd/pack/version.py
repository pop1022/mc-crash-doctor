"""Version-range satisfaction for Pack Doctor (ROADMAP 2.2).

WHY THIS IS A SEPARATE MODULE
  `mcd/metadata/manifest.py` keeps `version_range` verbatim on purpose: reading
  a manifest and *interpreting* a range are different jobs, and the reader has
  to stay trustworthy on packs whose ranges we cannot parse. This module is the
  interpreter, and it is allowed to say "no idea" (``None``).

WHY THE THREE FORMS ARE NOT THE SAME THING
  The single most common way a dependency checker lies is treating a bare
  version as exact. Forge's `versionRange` and Fabric's `depends` do not mean
  that:

      [1.20,1.21)   >= 1.20 and < 1.21     (inclusive lower, exclusive upper)
      (1.20,1.21]   > 1.20  and <= 1.21
      [1.20]        exactly 1.20
      1.20          MINIMUM 1.20 -- "1.20 or newer", not "1.20 only"
      *             anything

  The bare form is a minimum because that is Forge's own `versionRange`
  semantic, which is what ROADMAP 2.2 pins ("裸 `1.20` 是软下限而非精确锁定").
  Fabric almost always writes `>=1.20` explicitly for a minimum, so the two
  loaders rarely disagree in practice -- but where they would, this follows
  Forge, i.e. it errs towards *not* reporting a mismatch. That is the one place
  this module deliberately stays quiet, and it is written down here so the
  next reader does not have to rediscover it.

  Fabric additionally writes `>=1.20.1`, `~1.20.1` (>=1.20.1, <1.21.0),
  `^1.20` (>=1.20, <2.0), `1.20.x` and conjunctions (`>=1.20 <1.21`). All are
  accepted; anything else returns ``None``.

WHY None RATHER THAN A GUESS
  A dependency check that answers "ok" for a range it did not understand is
  exactly the failure this project keeps finding: the silence looks like
  approval. Pack Doctor lists every ``None`` as "undecided" with the verbatim
  range, so an unreadable constraint is visible instead of reassuring.

    from mcd.pack.version import satisfies
    satisfies("1.20.4", "[1.20,1.21)")   # True
    satisfies("1.21",   "[1.20,1.21)")   # False
    satisfies("1.20.9", "1.20")          # True  -- bare form is a minimum
    satisfies("1.20.4", "banana")         # None  -- we did not understand it
"""
from __future__ import annotations

import re

__all__ = ["parse_spec", "satisfies", "compare"]

#: The JVM/Forge ellipsis-free forms we understand. Anything else -> None.
_MAVEN = re.compile(r"^([\[\(])\s*([^,\[\]\(\)]*?)\s*(?:,\s*([^,\[\]\(\)]*?)\s*)?([\]\)])$")
_TERM = re.compile(r"^(>=|<=|==|=|>|<|\^|~)?\s*(\S+)$")
_PREFIX = re.compile(r"^(.*?)\.(?:\*|[xX])$")

_ANY = object()


def _ver(text: str):
    """`1.20.1` -> (1, 20, 1); `1.20.1-beta` -> ((1,20,1), prerelease_rank).

    Non-numeric segments (``1.20.1a``) keep their digits and become a
    prerelease, which is how Forge/Fabric order them: ``1.20.1a`` < ``1.20.1``.
    Returns None when a segment has no leading digits at all -- ``latest``,
    ``RELEASE`` -- because ordering those as numbers would be fiction.
    """
    s = (text or "").strip()
    if not s:
        return None
    s = s.split("+", 1)[0]                      # build metadata is not ordering
    core, _, pre = s.partition("-")
    nums: list[int] = []
    for part in core.split("."):
        m = re.match(r"\d+", part)
        if not m:
            return None
        nums.append(int(m.group(0)))
        rest = part[m.end():]
        if rest:
            pre = f"{rest}-{pre}" if pre else rest
    if not nums:
        return None
    return (tuple(nums), 0 if not pre else -1)


def _pad(a: tuple[int, ...], b: tuple[int, ...]):
    n = max(len(a), len(b))
    return (a + (0,) * (n - len(a)), b + (0,) * (n - len(b)))


def compare(left: str, right: str) -> int | None:
    """-1 / 0 / 1, or None when either side cannot be ordered numerically."""
    a, b = _ver(left), _ver(right)
    if a is None or b is None:
        return None
    an, bn = _pad(a[0], b[0])
    if an != bn:
        return -1 if an < bn else 1
    if a[1] != b[1]:                        # same numbers, prerelease differs
        return -1 if a[1] < b[1] else 1
    return 0


def _bump(v: tuple[int, ...], index: int):
    out = list(v[:index + 1])
    while len(out) <= index:
        out.append(0)
    out[index] += 1
    return tuple(out)


def _spec_terms(text: str):
    """Parse one range expression into [(op, version_key)] or None."""
    s = (text or "").strip()
    if s in ("", "*", "x", "X", "any", "+"):
        return _ANY
    m = _MAVEN.match(s)
    if m:
        lo_b, lo, hi, hi_b = m.groups()
        if hi is None:                       # [1.20] -- exactly this version
            if lo_b == "[" and hi_b == "]":
                key = _ver(lo)
                return None if key is None else [("=", key, lo)]
            return None                      # [1.20) is not a Maven range
        terms = []
        if lo:
            terms.append((">=" if lo_b == "[" else ">", _ver(lo), lo))
        if hi:
            terms.append(("<=" if hi_b == "]" else "<", _ver(hi), hi))
        return None if any(t[1] is None for t in terms) else terms

    terms = []
    for raw in s.split():
        m = _TERM.match(raw)
        if not m:
            return None
        op, body = m.group(1), m.group(2)
        p = _PREFIX.match(body)
        if p:
            base = _ver(p.group(1))
            if base is None:
                return None
            terms.append((">=", base, body))
            terms.append(("<", (_bump(base[0], len(base[0]) - 1), base[1]), body))
            continue
        key = _ver(body)
        if key is None:
            return None
        if op in (None, ""):                 # bare version == minimum
            terms.append((">=", key, body))
        elif op in ("=", "=="):
            terms.append(("=", key, body))
        elif op == "~":
            terms.append((">=", key, body))
            terms.append(("<", (_bump(key[0], 1 if len(key[0]) > 1 else 0), key[1]), body))
        elif op == "^":
            terms.append((">=", key, body))
            terms.append(("<", (_bump(key[0], 0), key[1]), body))
        else:
            terms.append((op, key, body))
    return terms or None


def parse_spec(text: str):
    """[(op, version_key, verbatim)] | _ANY | None (unparseable)."""
    return _spec_terms(text)


def _holds(op: str, have, want) -> bool:
    a, b = _pad(have[0], want[0])
    if op == "=":
        return a == b and have[1] == want[1]
    if a != b:
        return a > b if op in (">", ">=") else a < b
    if have[1] != want[1]:                 # same numbers, prerelease differs
        return have[1] < want[1] if op in ("<", "<=") else have[1] > want[1]
    return op in (">=", "<=", "=")


def satisfies(version: str, spec: str) -> bool | None:
    """Does `version` satisfy `spec`? None means "could not tell"."""
    terms = _spec_terms(spec)
    if terms is _ANY:
        return True
    if terms is None:
        return None
    have = _ver(version)
    if have is None:
        return None
    return all(_holds(op, have, want) for op, want, _ in terms)
