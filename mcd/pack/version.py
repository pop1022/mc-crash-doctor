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


def _nums(text: str):
    """(numbers, trailing-nonnumeric) for a dotted version core, or (None, "")."""
    nums: list[int] = []
    pre = ""
    for part in text.split("."):
        m = re.match(r"\d+", part)
        if not m:
            return None, ""
        nums.append(int(m.group(0)))
        rest = part[m.end():]
        if rest:
            pre = f"{rest}-{pre}" if pre else rest
    return (tuple(nums) if nums else None), pre


def _ver(text: str):
    """Parse to `(mc_numbers, mod_numbers, prerelease_rank)`, or None.

    Two number groups, not one, because NeoForge mods version themselves as
    ``<mc-version>-<mod-version>``: ``1.21.1-93-NEOFORGE`` is Minecraft 1.21.1,
    build 93. Flattening that into a single tuple compares 1.21.1 against 1.21
    by looking at the *mod* digits -- measured on a real pack, that turned
    ``[1.21-87-NEOFORGE,)`` against an installed ``1.21.1-93-NEOFORGE`` into a
    false `pack.version-mismatch`, because (1,21,1,93) < (1,21,87).

    A `-` followed by a DIGIT therefore starts the second group; a `-` followed
    by anything else is a prerelease tag (``1.20.1-beta`` < ``1.20.1``), which
    is the Forge/Fabric ordering the old code described.
    """
    s = (text or "").strip()
    if not s:
        return None
    s = s.split("+", 1)[0]                      # build metadata is not ordering
    core, _, suffix = s.partition("-")
    mc, pre = _nums(core)
    if mc is None:
        return None
    mod: tuple[int, ...] = ()
    if suffix and suffix[0].isdigit():
        mod, mod_pre = _nums(suffix)
        if mod is None:                         # "1.2.3-4x" -- unparsable suffix
            mod, mod_pre = (), ""
            pre = f"{suffix}-{pre}" if pre else suffix
        elif mod_pre:
            pre = f"{mod_pre}-{pre}" if pre else mod_pre
    elif suffix:
        pre = f"{suffix}-{pre}" if pre else suffix
    return (mc, mod, 0 if not pre else -1)


def _pad(a: tuple[int, ...], b: tuple[int, ...]):
    n = max(len(a), len(b))
    return (a + (0,) * (n - len(a)), b + (0,) * (n - len(b)))


def _cmp(a, b) -> int:
    am, bm = _pad(a[0], b[0])
    if am != bm:
        return -1 if am < bm else 1
    ax, bx = _pad(a[1], b[1])
    if ax != bx:
        return -1 if ax < bx else 1
    if a[2] != b[2]:                            # same numbers, prerelease differs
        return -1 if a[2] < b[2] else 1
    return 0


def compare(left: str, right: str) -> int | None:
    """-1 / 0 / 1, or None when either side cannot be ordered numerically."""
    a, b = _ver(left), _ver(right)
    if a is None or b is None:
        return None
    return _cmp(a, b)


def _bump(v: tuple[int, ...], index: int):
    out = list(v[:index + 1])
    while len(out) <= index:
        out.append(0)
    out[index] += 1
    return tuple(out)


def _bumped(key, index: int):
    """Same key with one component of the MC group incremented."""
    return (_bump(key[0], index), key[1], key[2])


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
            terms.append(("<", _bumped(base, len(base[0]) - 1), body))
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
            terms.append(("<", _bumped(key, 1 if len(key[0]) > 1 else 0), body))
        elif op == "^":
            terms.append((">=", key, body))
            terms.append(("<", _bumped(key, 0), body))
        else:
            terms.append((op, key, body))
    return terms or None


def parse_spec(text: str):
    """[(op, version_key, verbatim)] | _ANY | None (unparseable)."""
    return _spec_terms(text)


def _holds(op: str, have, want) -> bool:
    c = _cmp(have, want)
    if op == "=":
        return c == 0
    if op == ">":
        return c > 0
    if op == ">=":
        return c >= 0
    if op == "<":
        return c < 0
    if op == "<=":
        return c <= 0
    return False


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
