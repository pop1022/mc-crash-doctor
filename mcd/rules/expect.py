"""Per-rule fixture assertions that travel with the rule.

WHY NOT provenance.fixtures
  provenance.fixtures answers a historical question -- which real report made
  this rule exist -- and tests/test_gaps.py checks it against the gitignored
  corpus. That is the right shape for the builtin pack and the wrong shape for
  a third-party one: the report a stranger's rule was born from is not in our
  corpus, and no test suite here knows the rule exists.

  expect is the self-test such a rule can carry:

      expect:
        fires: [ground-truth/crash-2026-09-08_18.01.19-server.txt]
        quiet: [ground-truth/crash-2026-09-08_22.31.14-server.txt]

  fires means this rule must produce a finding on that report; quiet means it
  must not. Both are checked one rule at a time, so a quiet assertion cannot be
  satisfied by another rule swallowing the match, and a positive one cannot be
  satisfied by a neighbour.

RESOLVING A REF
  in order: the path as written; tests/fixtures/<ref> (with .txt appended when
  the ref has no suffix); corpus/github/<repo>/<number>.crash.txt for a
  repo/number pin. Missing fixture is a problem in --validate-rules, not a
  silent skip: the caller wrote the ref down, so a typo must be visible.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

from ..parser.report import parse_file
from ..triage.attribution import suspects_for_rules
from .engine import Rule, RuleSet, run_rules

__all__ = ["check", "resolve"]

ROOT = Path(__file__).resolve().parent.parent.parent


def resolve(ref: str, *, root: Path | None = None) -> Path | None:
    """Turn a ref into a path, or None when nothing matches it."""
    root = root or ROOT
    p = Path(ref)
    if p.is_absolute() and p.is_file():
        return p
    if p.is_file():
        return p
    cands = [root / ref]
    # Suffix is not a reliable test here: report names contain dots
    # ("...18.01.19-server"), so Path.suffix is ".19-server". Ask the string.
    if not ref.endswith(".txt"):
        cands.append(root / "tests" / "fixtures" / (ref + ".txt"))
    cands.append(root / "tests" / "fixtures" / ref)
    for c in cands:
        if c.is_file():
            return c
    m = re.fullmatch(r"([\w.\-]+)/(\d+)", ref)
    if m:
        repo, num = m.groups()
        hits = glob.glob(str(root / "corpus" / "github" / f"*__{repo}" /
                            f"{num}.crash.txt"))
        if hits:
            return Path(hits[0])
    return None


def _fires(rule: Rule, path: Path) -> bool:
    rep = parse_file(str(path))
    return bool(run_rules(rep, RuleSet([rule]), suspect_fn=suspects_for_rules))


def check(ruleset: RuleSet, *, root: Path | None = None) -> tuple[list[str], int]:
    """Run every expect block. Returns (problems, assertions checked)."""
    problems: list[str] = []
    checked = 0
    for rule in ruleset.rules:
        expect = rule.expect or {}
        for kind in ("fires", "quiet"):
            refs = expect.get(kind) or []
            if not isinstance(refs, list):
                problems.append(f"{rule.id}: expect.{kind} must be a list")
                continue
            for ref in refs:
                path = resolve(str(ref), root=root)
                if path is None:
                    problems.append(f"{rule.id}: expect.{kind}: fixture not "
                                    f"found: {ref}")
                    continue
                hit = _fires(rule, path)
                checked += 1
                if kind == "fires" and not hit:
                    problems.append(f"{rule.id}: expected to fire on {ref} "
                                    f"but produced no finding")
                elif kind == "quiet" and hit:
                    problems.append(f"{rule.id}: expected to stay quiet on "
                                    f"{ref} but fired")
    return problems, checked


def warnings_for(fname: str, rid: str, expect: object) -> list[str]:
    """Load-time shape check, so a typo is named before any fixture is read."""
    if not isinstance(expect, dict):
        return [f"{fname}: rule {rid!r}: expect must be a mapping with "
                f"fires/quiet lists"]
    out = []
    unknown = sorted(set(expect) - {"fires", "quiet"})
    if unknown:
        out.append(f"{fname}: rule {rid!r}: expect has unknown key(s) "
                   f"{unknown} -- only fires/quiet are read")
    for kind in ("fires", "quiet"):
        if kind in expect and not isinstance(expect[kind], list):
            out.append(f"{fname}: rule {rid!r}: expect.{kind} must be a list")
    return out
