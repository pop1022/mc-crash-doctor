"""Invariance tests -- ROADMAP 1E.2 ② (position bias) and ③ (metamorphic).

A diagnosis is only worth publishing if it is stable in the ways a *user*
cannot control. Two such invariances are checked here, both offline:

② POSITION INVARIANCE
   The Mod List is a table and its row order carries no information: loaders
   emit it in file-discovery order, which differs per machine, per launcher and
   per `mods/` directory. Attribution therefore must not depend on it.

   It did. ``scores`` is a ``defaultdict(float)`` and the old sort was

       sorted(scores.items(), key=lambda kv: -kv[1])

   which leaves equal scores ordered by dict insertion order -- i.e. by the
   order the mods appear in the report. Two reports of the same two-mod
   interaction, written in opposite order, could name different top suspects.
   That makes "top-1 is the repo's mod" (the metric ROADMAP 1B.2 rests on)
   partly an artefact of prose ordering rather than of evidence.

③ METAMORPHIC INVARIANCE
   Editing fields that cannot matter -- wall-clock time, the date, the player
   name, the install path, the world name -- must not change the diagnosis.
   This catches accidental coupling: a rule keyed on ``C:\\Users\\...`` stops
   firing the day the same crash happens on Linux, and a rule keyed on a clock
   value stops firing at midnight. Neither failure shows up in a normal test
   suite, because normal tests use one fixed report.

Both tests use real harvested reports (not only synthetic ones) so that the
invariance is checked against the corpus the metrics are computed on.

    pytest tests/test_invariance.py -v
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest

from mcd.parser.report import parse_file, parse_text, read_report_text
from mcd.rules.engine import RuleSet, run_rules
from mcd.triage.attribution import triage

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / "corpus" / "github"

#: How many real reports each real-data test walks. Small on purpose: the
#: tests must stay cheap enough to run on every commit, and 6 is already more
#: than the 3 reports that would be needed to catch a positional tie-break.
SAMPLE = 6

MODLIST_HDR = re.compile(r"^\s*Mod List:\s*$|^\s*Mods?:\s*\d+\s*$")


def _norm(text: str) -> str:
    """Same normalisation the parser applies, so line indexes agree with it.

    Needed because some harvested reports carry ``\\r\\r\\n`` endings; Python's
    ``str.splitlines`` splits on the lone ``\\r`` as well and double-counts
    every line, which silently made an earlier version of this helper look at
    blank lines instead of table rows.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def reverse_modlist_rows(text: str) -> tuple[str | None, int]:
    """Reverse the rows of the first Forge-style Mod List table.

    Returns ``(new_text, n_rows)``, or ``(None, 0)`` when the report has no
    table of at least three rows. Only the row *order* changes -- same bytes,
    same rows, same count -- so any difference in the output is positional.
    """
    lines = _norm(text).split("\n")
    for i, ln in enumerate(lines):
        if not MODLIST_HDR.match(ln):
            continue
        idx: list[int] = []
        rows: list[str] = []
        j = i + 1
        while j < len(lines):
            if "|" in lines[j]:
                idx.append(j)
                rows.append(lines[j])
            elif lines[j].strip():
                break
            j += 1
        if len(rows) < 3:
            continue
        for k, pos in enumerate(idx):
            lines[pos] = rows[-1 - k]
        return "\n".join(lines), len(rows)
    return None, 0


def _corpus_reports_with_modlist() -> list[Path]:
    """Deterministic, spread-across-repos sample of reports with a Mod List."""
    picked: list[Path] = []
    files = sorted(glob.glob(str(GITHUB / "*" / "*.crash.txt")))
    if not files:
        return []
    # stride, not head: taking the first N would sample a single repo, whose
    # reports share one loader and one formatting quirk.
    stride = max(1, len(files) // (SAMPLE * 4))
    for p in files[::stride]:
        path = Path(p)
        try:
            txt = read_report_text(path)
        except Exception:                                  # noqa: BLE001
            continue
        new, n = reverse_modlist_rows(txt)
        if new is None or n < 3:
            continue
        # duplicate modids would make "which row wins" itself positional; skip
        # those rather than pretend the test covers them
        ids = [m.modid.lower() for m in parse_text(txt).mods if m.modid]
        if len(ids) != len(set(ids)):
            continue
        picked.append(path)
        if len(picked) >= SAMPLE:
            break
    return picked


# --- ② position invariance --------------------------------------------------
_FABRIC_MODS = "Fabric Mods:"


def _synthetic(frames: list[str], mods: list[tuple[str, str]]) -> str:
    """A minimal but structurally real crash report."""
    out = ["---- Minecraft Crash Report ----", "", "// Oh dear.", "",
           "Time: 2026-01-01 12:00:00", "Description: Something crashed", "",
           "java.lang.RuntimeException: boom", ""]
    out += [f"\tat {f}" for f in frames]
    out += ["", _FABRIC_MODS]
    out += [f"  {mid}: {name} 1.0.0" for mid, name in mods]
    out.append("")
    return "\n".join(out) + "\n"


FRAME_ALPHA = "com.alpha.core.Boom.bang(Boom.java:42)"
FRAME_BETA = "com.beta.core.Bang.boom(Bang.java:13)"


def test_tie_is_broken_by_name_not_by_report_order():
    """The regression test for the 1E.2② fix.

    Two reports, identical evidence: one mod-owned frame each, both inside the
    top 3 (so both score W_FRAME_TOP), and therefore a genuine tie. Only the
    *order* differs -- frames swapped, Mod List rows swapped. Before the fix
    the winner followed the report (alpha in one, beta in the other).
    """
    a = _synthetic([FRAME_ALPHA, FRAME_BETA], [("alpha", "Alpha"), ("beta", "Beta")])
    b = _synthetic([FRAME_BETA, FRAME_ALPHA], [("beta", "Beta"), ("alpha", "Alpha")])

    ta, tb = triage(parse_text(a)), triage(parse_text(b))
    order_a = [s.modid for s in ta.suspects]
    order_b = [s.modid for s in tb.suspects]

    # sanity: the two reports really do present the evidence in opposite order,
    # so a difference below would be positional and not a change of content
    assert [m.modid for m in parse_text(a).mods] == ["alpha", "beta"]
    assert [m.modid for m in parse_text(b).mods] == ["beta", "alpha"]

    assert order_a == order_b, (
        f"top-1 depends on the order mods are written in the report: "
        f"{order_a} vs {order_b}")
    # and the tie is broken by a rule a reader can predict, not by luck
    assert order_a == ["alpha", "beta"]
    assert ta.suspects[0].score == pytest.approx(tb.suspects[0].score)
    # equal scores must be reported as an interaction, in both orderings
    assert any("interaction" in n for n in ta.notes)
    assert any("interaction" in n for n in tb.notes)


def test_reversing_a_real_mod_list_does_not_change_attribution():
    """Same invariant on real reports: the Mod List row order is machine
    furniture, so reversing it must not move the key."""
    reports = _corpus_reports_with_modlist()
    if not reports:
        pytest.skip("harvested corpus absent (run tools/harvest_corpus.py)")
    failures = []
    for p in reports:
        text = read_report_text(p)
        flipped, n = reverse_modlist_rows(text)
        assert flipped is not None and n >= 3
        before = [s.modid for s in triage(parse_file(p)).suspects]
        after = [s.modid for s in triage(parse_text(flipped)).suspects]
        if before != after:
            failures.append(f"{p.name}: {before} -> {after} ({n} rows)")
    assert not failures, (
        "Mod List row order changed the attribution on "
        f"{len(failures)}/{len(reports)} reports:\n  " + "\n  ".join(failures))


# --- ③ metamorphic invariance -----------------------------------------------
_SCRUBS = (
    # wall clock, both "12:34:56" and "[12:34:56]"
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"), "00:00:00"),
    # dates in both formats Minecraft uses
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "1970-01-01"),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"), "01/01/1970"),
    # Windows user path -> a different path with the same shape.
    # The replacement is a raw string with doubled backslashes on purpose:
    # re.sub parses `\m` in a replacement as a group reference and raises.
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+"), r"D:\\mc\\.minecraft"),
    # POSIX home -> a different home
    (re.compile(r"/(?:home|Users)/[^/\s\"']+"), "/srv/mc"),
    # identity: player name, world name
    (re.compile(r"(?i)(--username\s+|-username\s+|Player:\s*|"
                r"Level name:\s*)\S+"), r"\1redacted"),
    # launcher-assigned session id / uuid noise
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "00000000-0000-0000-0000-000000000000"),
)


def scrub(text: str) -> str:
    for pat, repl in _SCRUBS:
        text = pat.sub(repl, text)
    return text


def _diagnosis(rep, rs: RuleSet) -> tuple[list[str], list[str]]:
    return ([f.rule_id for f in run_rules(rep, rs)],
            [s.modid for s in triage(rep).suspects])


def test_scrubbing_identity_fields_does_not_change_the_diagnosis():
    """Time, date, player, world and install path are not evidence.

    If a rule or the attributor reacts to one of them it is reading the
    environment instead of the crash, and its verdict will not reproduce on
    someone else's machine.
    """
    files = _corpus_reports_with_modlist()
    if not files:
        pytest.skip("harvested corpus absent")
    rs = RuleSet.load()
    failures = []
    for p in files:
        text = read_report_text(p)
        edited = scrub(text)
        assert edited != text or not _SCRUBS, "scrubber matched nothing"
        rules_a, sus_a = _diagnosis(parse_text(text), rs)
        rules_b, sus_b = _diagnosis(parse_text(edited), rs)
        if sorted(rules_a) != sorted(rules_b) or sus_a != sus_b:
            failures.append(
                f"{p.name}: rules {rules_a} -> {rules_b}; "
                f"suspects {sus_a} -> {sus_b}")
    assert not failures, (
        "diagnosis changed after scrubbing non-evidence fields:\n  "
        + "\n  ".join(failures))


def test_scrubber_actually_changes_the_text():
    """Guard the guard: a scrubber that matches nothing makes the test above
    vacuously green."""
    sample = ("Time: 2026-09-08 18:01:19\n"
              "--username Notch\nPlayer: Herobrine\n"
              "Level name: world_2026\n"
              "at C:\\Users\\Notch\\AppData\\Roaming\\.minecraft\\mods\n"
              "at /home/notch/.minecraft/mods\n"
              "uuid 123e4567-e89b-12d3-a456-426614174000\n")
    out = scrub(sample)
    for leaked in ("2026-09-08", "18:01:19", "Notch", "Herobrine", "world_2026",
                   "123e4567"):
        assert leaked not in out, f"scrubber left {leaked!r} in place: {out!r}"
