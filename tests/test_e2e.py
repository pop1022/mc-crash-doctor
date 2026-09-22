"""End-to-end check: does the pipeline actually diagnose real reports?

Three groups, each with a known answer:

1. **Ground truth** -- six reports whose root cause was established by hand
   (4x heap OOM during world save, 2x ServerHangWatchdog). The rules must
   reproduce that verdict.
2. **MIT corpus** (201 files from aternosorg/codex-minecraft) -- no rule may
   *crash*, and we report how many files get at least one finding.
3. **Harvested corpus** (real mod-repo issues) -- same, plus attribution rate.

    python tests/test_e2e.py
    python tests/test_e2e.py --corpus      # corpus groups only
    python tests/test_e2e.py -v
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file  # noqa: E402
from mcd.rules.engine import RuleSet, run_rules  # noqa: E402
from mcd.triage.attribution import triage  # noqa: E402

MC_DIR = Path(os.environ.get("MCD_MC_DIR", r"C:\Users\Administrator\Desktop\mc"))

# Ground truth, established from the reports' OWN evidence (verified 2026-09):
# none of these six contains "Saving worlds"/"Saving chunks", so none of them is
# a shutdown-save OOM. The 18:01 report's stack is entirely vanilla
# MinecraftServer frames; 18:39 and 18:45 die inside NBT/codec encoding; 18:47
# is a ticking-entity crash. The two 22:xx reports are ServerHangWatchdog kills.
#
# filename stem -> rule ids that MUST fire
GROUND_TRUTH: dict[str, list[str]] = {
    "crash-2026-09-08_18.01.19": ["oom.heap"],
    "crash-2026-09-08_18.39.21": ["oom.heap"],
    "crash-2026-09-08_18.45.43": ["oom.heap"],
    "crash-2026-09-08_18.47.46": ["oom.heap", "crash.ticking-entity"],
    "crash-2026-09-08_22.31.14": ["hang.watchdog"],
    "crash-2026-09-08_22.42.32": ["hang.watchdog"],
}

# Rules that must NOT fire on the ground-truth set (guards against the
# save-time heuristic misreading a ticking-world OOM).
MUST_NOT_FIRE: dict[str, list[str]] = {
    "crash-2026-09-08_18.01.19": ["oom.save-time"],
    "crash-2026-09-08_18.39.21": ["oom.save-time"],
    "crash-2026-09-08_18.47.46": ["oom.save-time"],
}


def run_ground_truth(ruleset: RuleSet, verbose: bool) -> tuple[int, int]:
    if not MC_DIR.exists():
        print("⚠ ground-truth dir not found:", MC_DIR, "-> skipped")
        return 0, 0
    files = sorted(glob.glob(str(MC_DIR / "crash-reports" / "crash-*.txt")))
    if not files:
        print("⚠ no crash reports in", MC_DIR, "-> skipped")
        return 0, 0

    print(f"\n═══ 1. GROUND TRUTH ({len(files)} real reports) ═══")
    ok = 0
    for f in files:
        stem = Path(f).stem.replace("-server", "")
        want = GROUND_TRUTH.get(stem, [])
        forbid = MUST_NOT_FIRE.get(stem, [])
        rep = parse_file(f)
        findings = run_rules(rep, ruleset)
        t = triage(rep)
        ids = [x.rule_id for x in findings]
        missing = [r for r in want if r not in ids]
        fired_forbidden = [r for r in forbid if r in ids]
        hit = (not want or not missing) and not fired_forbidden
        ok += 1 if hit else 0
        mark = "✓" if hit else "✗"
        print(f"\n{mark} {Path(f).name}")
        print(f"   desc      : {rep.description}")
        print(f"   loader    : {rep.system.loader} {rep.system.loader_version}"
              f"  MC {rep.system.minecraft_version}  Java {rep.system.java_major}")
        print(f"   heap      : used {rep.system.memory.used_mib} MiB / "
              f"max {rep.system.memory.max_mib} MiB  "
              f"(xmx flag {rep.system.xmx_mib} MiB)  mods={len(rep.mods)}")
        rc = rep.root_cause
        if rc:
            print(f"   root cause: {rc.signature[:90]}")
        print(f"   must fire : {want}   must NOT: {forbid}")
        print(f"   fired     : {ids[:6]}")
        if missing:
            print(f"   ✗ MISSING : {missing}")
        if fired_forbidden:
            print(f"   ✗ FORBIDDEN FIRED: {fired_forbidden}")
        if verbose or t.suspects:
            for s in t.suspects[:3]:
                print(f"   suspect   : {s.modid:<24} conf={s.confidence:.2f} "
                      f"{(s.reasons[0][:70] if s.reasons else '')}")
            if t.notes:
                print(f"   note      : {t.notes[0][:110]}")
    print(f"\n  ── ground truth: {ok}/{len(files)} matched")
    return ok, len(files)


def run_corpus(ruleset: RuleSet, label: str, pattern: str,
               verbose: bool) -> None:
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        print(f"\n═══ {label}: no files ═══")
        return
    print(f"\n═══ {label} ({len(files)} files) ═══")
    errors: list[tuple[str, str]] = []
    with_finding = 0
    rule_hits: collections.Counter = collections.Counter()
    attributed = 0
    severities: collections.Counter = collections.Counter()

    for f in files:
        try:
            rep = parse_file(f)
            findings = run_rules(rep, ruleset)
            t = triage(rep)
        except Exception as e:  # noqa: BLE001
            errors.append((os.path.relpath(f, ROOT), f"{type(e).__name__}: {e}"))
            continue
        if findings:
            with_finding += 1
            for x in findings:
                rule_hits[x.rule_id] += 1
                severities[x.severity.name] += 1
        if t.suspects:
            attributed += 1

    print(f"  parse/run errors : {len(errors)}")
    for f, e in errors[:8]:
        print(f"    ✗ {f}: {e[:100]}")
    print(f"  files w/ finding : {with_finding}/{len(files)} "
          f"({with_finding/len(files):.0%})")
    print(f"  files w/ suspect : {attributed}/{len(files)} "
          f"({attributed/len(files):.0%})")
    print(f"  severities       : {dict(severities)}")
    print(f"  rule hit counts  :")
    for rid, c in rule_hits.most_common():
        print(f"    {c:>4}  {rid}")
    never = [r.id for r in ruleset.rules if rid_not_hit(r.id, rule_hits)]
    print(f"  rules never fired: {len(never)}")
    for r in never:
        print(f"    - {r}")


def rid_not_hit(rid: str, hits: collections.Counter) -> bool:
    return hits.get(rid, 0) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="store_true",
                    help="skip ground-truth (needs the local MC dir)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    rs = RuleSet.load()
    print(f"ruleset: {len(rs.rules)} rules")

    total_ok = total_n = 0
    if not args.corpus:
        total_ok, total_n = run_ground_truth(rs, args.verbose)

    run_corpus(rs, "2. MIT corpus (aternos)",
               str(ROOT / "corpus/aternos/**/*.log"), args.verbose)
    run_corpus(rs, "3. Harvested corpus (mod repos)",
               str(ROOT / "corpus/github/**/*.crash.txt"), args.verbose)

    if total_n:
        print(f"\n════ ground truth: {total_ok}/{total_n} "
              f"{'✓ PASS' if total_ok == total_n else '✗ FAIL'} ════")
        return 0 if total_ok == total_n else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
