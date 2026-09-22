"""Gap regression: each runtime-crash rule pinned to the real report that
motivated it.

These harvested fragments (corpus/github/, gitignored -- rebuilt with
tools/harvest_corpus.py) are what drove the runtime-crashes.yaml pack. If a
corpus file is absent locally the case skips instead of failing, so CI stays
green while contributors who harvest see the pinning.

    pytest tests/test_gaps.py -v
"""

from __future__ import annotations

import glob
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


def _find(issue: str) -> str | None:
    hits = glob.glob(str(_GH / "**" / f"{issue}.crash.txt"), recursive=True)
    return hits[0] if hits else None


# issue number -> (rule that must fire, suspect that must be attributed)
# None suspect = rule must fire but attribution is allowed to be empty.
PINS: dict[str, tuple[str, str | None]] = {
    "8631": ("mod.load-failed.neoforge", None),
    "8633": ("mod.load-failed.neoforge", None),
    "8391": ("mod.load-failed.fabric-entry", None),
    "8479": ("mod.load-failed.fabric-entry", None),
    "8539": ("mod.load-failed.fabric-entry", None),
    "8354": ("mod.client-class-on-server", None),
    "8531": ("crash.threading-race", None),
    "8423": ("crash.datapack-book", None),
    "8518": ("crash.rendering-blockentity", None),
    # attribution via exception-message class mining (no Mod List in fragment)
    "8590": ("crash.runtime-mod", "mekanism"),
    # 8483's root cause is ClassNotFoundException (create's AirCurrent class
    # moved between versions), so the runtime catch-all handles it; the
    # message-mining attribution must still name create.
    "8483": ("crash.runtime-mod", "create"),
}


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
    """At most 3 of the harvested Mekanism fragments may go undiagnosed.

    The three are genuine dead ends (generic exceptions with pure-vanilla
    stacks: ArrayIndexOutOfBounds, 'Not building!', bare
    UnsupportedOperationException). If coverage regresses, this fails first
    and the new blind spots get listed.
    """
    files = sorted(glob.glob(str(_GH / "**" / "*.crash.txt"), recursive=True))
    if not files:
        pytest.skip("harvested corpus absent")
    blind = []
    for f in files:
        rep = parse_file(f)
        if rep.root_cause and rep.root_cause.kind and not run_rules(rep, _rs):
            blind.append(f"{Path(f).stem}: {rep.root_cause.signature[:60]}")
    assert len(blind) <= 3, f"blind spots grew to {len(blind)}:\n  " + "\n  ".join(blind)


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
