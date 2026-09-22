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
    """Resolve a pin key to a corpus path.

    Keys are either a bare issue number ("8631" -- unambiguous while the
    corpus was one repo) or a repo-qualified "repo/number" ("sodium/3711").
    14 issue numbers now collide across the 12-repo corpus, so qualified
    keys match the directory name's suffix after "__".
    """
    if "/" in issue:
        repo, num = issue.split("/", 1)
        hits = glob.glob(str(_GH / f"*__{repo}" / f"{num}.crash.txt"))
    else:
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
    # 2026-09 corpus expansion (12 repos, 454 fragments) -- new wordings:
    #   sodium #3524: FormattedException "mod 'Sodium' requires any 0.8.x
    #   version ... but only the wrong version is present" (resolver text
    #   the old `incompatible mod set` pattern never matched)
    "3524": ("mod.incompatible-set", None),
    "3813": ("mod.incompatible-set", None),
    #   fabric-loader #685 / fabric-api #4907: ZipException on a corrupt or
    #   empty jar ("zip file is empty", "zip END header not found")
    "685": ("mod.corrupt-jar", None),
    "4907": ("mod.corrupt-jar", None),
    # 2026-09 second wave (quilt-loader/fabric-loader/sodium blind spots).
    # Repo-qualified keys: issue numbers collide across the 12-repo corpus.
    #   fabric-loader #611: the FATAL NoSuchFieldError (VoxelMap vs new MC
    #   biome registry) -- also exercises the log-FATAL root-cause fix:
    #   an earlier WARN NumberFormatException must NOT win
    "fabric-loader/611": ("mod.binary-incompat", None),
    #   sodium #3711: NoSuchMethodError against a moved MC method
    "sodium/3711": ("mod.binary-incompat", None),
    #   quilt-loader #232: loader constraint violation (duplicate class)
    "quilt-loader/232": ("mod.linkage-duplicate", None),
    #   quilt-loader #261: JSON5 strict-mode parse failure
    "quilt-loader/261": ("quilt.config-broken", None),
    #   quilt-loader #497: intermediary mappings not loaded
    "quilt-loader/497": ("loader.namespace-missing", None),
    #   fabric-api #5097: iris$makeColor @WrapOperation injection failure
    "fabric-api/5097": ("mixin.injection-failed", None),
    #   fabric-api #4862: "Failed to load registries due to above errors"
    "fabric-api/4862": ("crash.registry-load-failed", None),
    #   quilt-loader #344: UnknownHostException beacon.quiltmc.org
    "quilt-loader/344": ("net.connectivity", None),
    #   quilt-loader #398: libawt_xawt.so missing (headless JVM)
    "quilt-loader/398": ("env.headless-jvm", None),
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
