"""Gap regression: each rule pinned to the real report that motivated it.

The pins are NOT hardcoded here anymore -- they live in each rule's YAML
`provenance.fixtures` (stamped by tools/stamp_provenance.py), so a rule and
its proof sit together in one place. This file reads them back and asserts
each pinned report still fires its rule (and attributes the expected suspect
where `provenance.expect_suspects` says so). ROADMAP 1A.3: single source of
truth for rule<->report bindings.

The pinned fragments live in corpus/github/ (gitignored -- rebuilt with
tools/harvest_corpus.py). If a corpus file is absent locally the case skips
instead of failing, so CI stays green while contributors who harvest locally
see the pinning enforced.

    pytest tests/test_gaps.py -v
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file  # noqa: E402
from mcd.rules.engine import RuleSet, run_rules  # noqa: E402
from mcd.triage.attribution import triage  # noqa: E402

_rs = RuleSet.load()
_GH = ROOT / "corpus" / "github"

# A curated harvested pin looks like "repo/1234" (repo slug + issue number).
# This deliberately excludes scanned evidence keys ("harvested:repo/1234",
# "gt:...", "aternos:...") and synthetic fixtures ("synthetic/foo.txt",
# proven by tests/test_rule_fixtures.py) -- only hand-pinned motivating
# reports become gap-regression tests here.
_HARVESTED_PIN = re.compile(r"^[\w.\-]+/\d+$")


def _find(issue: str) -> str | None:
    """Resolve a "repo/number" pin key to a corpus path.

    Repo-qualified because issue numbers collide across the 12-repo corpus;
    the directory name's suffix after "__" is matched.
    """
    repo, num = issue.split("/", 1)
    hits = glob.glob(str(_GH / f"*__{repo}" / f"{num}.crash.txt"))
    return hits[0] if hits else None


def _pins_from_metadata() -> dict[str, tuple[str, str | None]]:
    """issue-key -> (rule_id, expected_suspect), read from rule provenance."""
    pins: dict[str, tuple[str, str | None]] = {}
    for r in _rs.rules:
        prov = r.provenance or {}
        expects = prov.get("expect_suspects") or {}
        for fx in prov.get("fixtures", []):
            if not isinstance(fx, str) or not _HARVESTED_PIN.match(fx):
                continue
            pins[fx] = (r.id, expects.get(fx))
    return pins


PINS = _pins_from_metadata()


def test_metadata_pins_are_nonempty():
    """Guard against a false green: if provenance stamping broke, PINS would
    silently empty out and every pin test would SKIP (looks green, proves
    nothing). The curated set is known to be >= 20 reports."""
    assert len(PINS) >= 20, (
        f"only {len(PINS)} pins loaded from rule provenance -- did "
        f"tools/stamp_provenance.py run? sample rules with fixtures: "
        f"{[r.id for r in _rs.rules if (r.provenance or {}).get('fixtures')][:5]}")


@pytest.mark.parametrize("issue", sorted(PINS))
def test_rule_pinned_to_real_report(issue):
    path = _find(issue)
    if path is None:
        pytest.skip(f"harvested corpus absent (run tools/harvest_corpus.py); "
                    f"no {issue}.crash.txt")
    want_rule, want_suspect = PINS[issue]
    rep = parse_file(path)
    fired = {f.rule_id for f in run_rules(rep, _rs)}
    assert want_rule in fired, \
        f"issue {issue}: expected {want_rule}, fired={sorted(fired)}"
    if want_suspect:
        suspects = [s.modid for s in triage(rep).suspects]
        assert want_suspect in suspects, \
            f"issue {issue}: expected suspect {want_suspect}, got {suspects}"


def test_blind_spots_stay_bounded():
    """Coverage floor over the whole harvested corpus, scale-free.

    History: this used to assert an absolute count (`blind <= 3`) written when
    the corpus was 34 Mekanism fragments. The 2026-09 expansion (12 repos,
    454 fragments) made that number meaningless -- more issues means more
    blind spots even with *better* rules. So the invariant is now a diagnosis
    RATE floor (regression = rate collapse), plus the original Mekanism
    subset keeps its own tight absolute bound (its 5 dead ends are known and
    documented: generic exceptions with pure-vanilla stacks).
    """
    files = sorted(glob.glob(str(_GH / "**" / "*.crash.txt"), recursive=True))
    if not files:
        pytest.skip("harvested corpus absent")
    blind = []
    mek_blind = 0
    for f in files:
        rep = parse_file(f)
        if rep.root_cause and rep.root_cause.kind and not run_rules(rep, _rs):
            blind.append(f"{Path(f).stem}: {rep.root_cause.signature[:60]}")
            if "Mekanism" in f:
                mek_blind += 1
    rate = 1 - len(blind) / len(files)
    assert rate >= 0.50, (
        f"diagnosis rate collapsed to {rate:.1%} over {len(files)} fragments "
        f"({len(blind)} blind). Worst offenders:\n  " + "\n  ".join(blind[:10])
    )
    assert mek_blind <= 5, f"Mekanism blind spots grew to {mek_blind} (was 5)"


def test_runtime_mod_rule_never_fires_without_suspect():
    """The catch-all must stay honest: has_suspect gate means zero findings
    from crash.runtime-mod on reports where attribution found nothing."""
    files = sorted(glob.glob(str(ROOT / "corpus" / "aternos/**/*.log"),
                             recursive=True))
    fired_no_suspect = []
    for f in files:
        rep = parse_file(f)
        t = triage(rep)
        for fd in run_rules(rep, _rs):
            if fd.rule_id == "crash.runtime-mod" and not t.suspects:
                fired_no_suspect.append(Path(f).name)
    assert not fired_no_suspect, \
        f"crash.runtime-mod fired without a suspect: {fired_no_suspect[:5]}"
