#!/usr/bin/env python
"""Blind-set evaluation (ROADMAP 1B.1) + misattribution rate (basis of 1B.2).

WHY THIS EXISTS
  Rules were authored against the harvested corpus. To answer "can people
  RELY on the diagnosis?" (VISION phase-1 goal) we need numbers computed on
  reports that did NOT motivate any rule. This tool splits the corpus into
  dev vs blind sets and measures, on the blind set only:

    - diagnosis rate (any finding fired)
    - diagnosis rate stratified by the maintainer's weak-supervision verdict
    - attribution accuracy: on crash-type verdicts for MOD repos, does the
      top-1 suspect name the repo's own mod?
    - misattribution rate: top-1 suspect present but NOT the repo's mod
      (the "wrongly blamed someone" numerator for ROADMAP 1B.2)

HONEST LIMITATIONS (do not remove)
  1. Report-level blind, corpus-level NOT blind: rule *wording* was informed
     by corpus-wide blind-spot clustering (e.g. "16 FormattedException
     reports share this phrasing"). Numbers therefore measure
     generalisation to unseen reports, not prospective validity.
  2. The genuinely blind set grows with every future re-harvest: reports
     harvested after the rules were written land in the blind stratum
     automatically (the split is hash-based, not hand-picked).
  3. Ground truth is weak supervision (maintainer labels), not adjudicated
     root cause. `user_error_or_config` reports may still contain a real
     mod crash and vice versa.

SPLIT (deterministic, reproducible)
  - Any report cited in a rule's provenance.fixtures (form "repo/<issue>")
    is forced into the DEV set -- it motivated a rule, it is not blind.
  - Remaining reports: sha256("<repo-dir>/<issue>") % 10 < 5 -> blind.
    Hash input is the corpus-relative path, so the split survives reharvests
    of the same issues and only new issues move between sets by hash luck.

STRATA
  - mod repos   : the repo IS a mod -> attribution measurable
  - loader/api  : fabric-loader, fabric-api, quilt-loader -> blaming "the
                  repo's mod" is meaningless (issues concern submodules or
                  user setups); diagnosis rate only.

    python tools/blind_eval.py [--json corpus/blind-eval.json] [--dev]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GITHUB = os.path.join(ROOT, "corpus", "github")

# repo dir (after "__") -> canonical mod id, for repos that ARE a mod.
# Absence = loader/library repo (diagnosis-rate-only stratum).
REPO_MOD = {
    "Mekanism": "mekanism",
    "sodium": "sodium",
    "Jade": "jade",
    "RFTools": "rftools",
    "Curios": "curios",
    "twilightforest": "twilightforest",
    "ModernFix": "modernfix",
    "Placebo": "placebo",
    "TinkersConstruct": "tconstruct",
}
LOADER_REPOS = {"fabric-loader", "fabric-api", "quilt-loader"}

# Verdict semantics drive the scoring direction -- a single "crash verdicts"
# bucket was wrong (blind_eval's first run flagged TiC/5379 as
# "misattribution" when top-1=mantle on a root_cause_elsewhere verdict is
# exactly RIGHT):
#   bug_in_this_mod       -> top-1 SHOULD be the repo's mod
#   root_cause_elsewhere  -> top-1 should be SOME OTHER mod (repo-mod hit =
#                            wrong blame direction)
#   known_issue           -> ambiguous (known issue in this mod OR a known
#                            external interaction); scored separately, never
#                            folded into hit/miss
#   outdated_version      -> version problem; attribution direction unclear,
#                            excluded from scoring
VERDICT_SHOULD_HIT_REPO = {"bug_in_this_mod"}
VERDICT_SHOULD_MISS_REPO = {"root_cause_elsewhere"}
VERDICT_AMBIGUOUS = {"known_issue", "outdated_version"}
# kept for the stratified diagnosis-rate table (any crash-ish verdict)
CRASH_VERDICTS = (VERDICT_SHOULD_HIT_REPO | VERDICT_SHOULD_MISS_REPO
                  | VERDICT_AMBIGUOUS)

_PIN_RE = re.compile(r"^[\w.\-]+/\d+$")


def pinned_paths() -> set[str]:
    """Corpus paths cited by any rule's provenance (dev set by definition)."""
    from mcd.rules.engine import RuleSet
    rs = RuleSet.load()
    paths = set()
    for r in rs.rules:
        for fx in (r.provenance or {}).get("fixtures", []):
            if isinstance(fx, str) and _PIN_RE.match(fx):
                repo, num = fx.split("/", 1)
                hits = glob.glob(os.path.join(GITHUB, f"*__{repo}",
                                              f"{num}.crash.txt"))
                paths.update(hits)
    return paths


def split_corpus() -> tuple[list[str], list[str]]:
    """(dev_files, blind_files) -- deterministic."""
    pinned = pinned_paths()
    dev, blind = [], []
    for f in sorted(glob.glob(os.path.join(GITHUB, "**", "*.crash.txt"),
                              recursive=True)):
        if f in pinned:
            dev.append(f)
            continue
        rel = os.path.relpath(f, GITHUB).replace(os.sep, "/")
        key = rel[:-10] if rel.endswith(".crash.txt") else rel  # repo/issue
        h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        (blind if h % 10 < 5 else dev).append(f)
    return dev, blind


def _verdict_index() -> dict[str, dict]:
    """corpus-relative key 'Repo/issue' -> index record (verdict, url)."""
    idx = {}
    p = os.path.join(ROOT, "corpus", "index.jsonl")
    if not os.path.exists(p):
        return idx
    for line in open(p, encoding="utf-8"):
        d = json.loads(line)
        idx[f"{d['repo'].split('/')[-1]}/{d['number']}"] = d
    return idx


def evaluate(files: list[str]) -> dict:
    """Run the engine over `files`, aggregate blind-set metrics."""
    from mcd.parser.report import parse_file
    from mcd.rules.engine import RuleSet, run_rules
    from mcd.triage.attribution import triage

    rs = RuleSet.load()
    vidx = _verdict_index()

    out = {
        "n": 0, "parse_errors": 0,
        "diagnosed": 0, "root_cause": 0,
        "by_verdict": defaultdict(lambda: [0, 0]),      # verdict -> [n, diag]
        "mod_repo": {"n": 0, "diag": 0,
                     # bug_in_this_mod: top-1 SHOULD equal repo mod
                     "bug_n": 0, "bug_hit": 0, "bug_miss": 0, "bug_nopick": 0,
                     # root_cause_elsewhere: top-1 should be a DIFFERENT mod
                     "else_n": 0, "else_correct": 0, "else_wrongrepo": 0,
                     "else_nopick": 0,
                     # known_issue/outdated: reported, not scored as hit/miss
                     "ambig_n": 0, "ambig_repo": 0},
        "loader_repo": {"n": 0, "diag": 0},
        "misattribution_samples": [],
        "good_external_samples": [],
    }
    for f in files:
        rel = os.path.relpath(f, GITHUB).replace(os.sep, "/")
        repo_dir, num = rel.split("/", 1)
        issue = num[:-10]
        short = repo_dir.split("__")[-1]
        rec = vidx.get(f"{short}/{issue}", {})
        verdict = rec.get("verdict")

        out["n"] += 1
        try:
            rep = parse_file(f)
            findings = run_rules(rep, rs)
            t = triage(rep)
        except Exception as e:                            # noqa: BLE001
            out["parse_errors"] += 1
            out["parse_errors_detail"] = str(e)[:80]
            continue

        diag = bool(findings)
        if diag:
            out["diagnosed"] += 1
        if rep.root_cause and rep.root_cause.kind:
            out["root_cause"] += 1
        vk = verdict or "(none)"
        out["by_verdict"][vk][0] += 1
        out["by_verdict"][vk][1] += int(diag)

        if short in REPO_MOD:
            m = out["mod_repo"]
            m["n"] += 1
            m["diag"] += int(diag)
            want = REPO_MOD[short]
            top = t.suspects[0].modid if t.suspects else None
            # slug match: mekanism ~ mekanismgenerators, tconstruct ~ tic
            def _is_repo(x):
                return bool(x) and (x == want or x.startswith(want)
                                    or want.startswith(x))
            sample = {"report": f"{short}/{issue}", "verdict": verdict,
                      "top_suspect": top, "repo_mod": want,
                      "url": rec.get("url", "")}

            if verdict in VERDICT_SHOULD_HIT_REPO:
                # maintainer says the bug IS this mod -> top-1 should name it
                m["bug_n"] += 1
                if top is None:
                    m["bug_nopick"] += 1
                elif _is_repo(top):
                    m["bug_hit"] += 1
                else:
                    m["bug_miss"] += 1
                    if len(out["misattribution_samples"]) < 8:
                        out["misattribution_samples"].append(sample)

            elif verdict in VERDICT_SHOULD_MISS_REPO:
                # root cause is ELSEwhere -> top-1 should be a different mod;
                # naming the repo's own mod here is the actual blame error
                m["else_n"] += 1
                if top is None:
                    m["else_nopick"] += 1
                elif _is_repo(top):
                    m["else_wrongrepo"] += 1
                    if len(out["misattribution_samples"]) < 8:
                        out["misattribution_samples"].append(sample)
                else:
                    m["else_correct"] += 1
                    if len(out["good_external_samples"]) < 8:
                        out["good_external_samples"].append(sample)

            elif verdict in VERDICT_AMBIGUOUS:
                # known_issue/outdated: direction unclear, report only
                m["ambig_n"] += 1
                if _is_repo(top):
                    m["ambig_repo"] += 1
        elif short in LOADER_REPOS:
            out["loader_repo"]["n"] += 1
            out["loader_repo"]["diag"] += int(diag)

    out["by_verdict"] = {k: v for k, v in sorted(out["by_verdict"].items())}
    return out


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else f"{a}/{b} (n/a)"


#: Two-sided 95% normal quantile. Hard-coded rather than computed so the report
#: does not need SciPy, and so the number cannot drift with a library upgrade.
Z95 = 1.959963984540054

#: Below this denominator we publish the count and the interval, never the bare
#: percentage. 30 is the usual line where the normal approximation to a binomial
#: starts to behave; Wilson is fine below it, but the *point estimate* is not
#: worth quoting on its own either way.
MIN_QUOTABLE_N = 30


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k/n.

    WHY NOT THE NORMAL APPROXIMATION
    --------------------------------
    This report's headline is 1/7. The textbook `p ± z*sqrt(p(1-p)/n)` gives
    0.143 ± 0.26, i.e. a lower bound below zero, which is not a probability and
    gets clipped to "0%" -- reading as "could be perfect". Wilson never leaves
    [0, 1], behaves at small n and at 0/n or n/n, and is the interval the
    roadmap's own limitation note was quoting.

    A bare "14%" is not a finding: with n=7 the same data is consistent with
    anything from ~3% to ~40%. The point estimate is what gets published and
    misquoted, so the interval has to travel with it.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    # Floating-point dust: 10/10 comes out as 0.9999999999999999 and 0/3 as
    # 5.5e-17. A report that prints "99.99999999999999%" or "[0.0000000000001%,
    # ...]" is the same sloppiness this function exists to remove, so snap
    # anything within an epsilon of a boundary onto it.
    eps = 1e-12
    if lo < eps:
        lo = 0.0
    if hi > 1 - eps:
        hi = 1.0
    return (lo, hi)


def _ci(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None,
            "lo": round(lo, 4), "hi": round(hi, 4)}


def _ci_str(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{_pct(k, n)}  95% CI [{lo:.0%}, {hi:.0%}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "corpus",
                                                   "blind-eval.json"))
    ap.add_argument("--dev", action="store_true",
                    help="also evaluate the dev set (for comparison)")
    args = ap.parse_args()

    dev, blind = split_corpus()
    print(f"split: dev={len(dev)}  blind={len(blind)}")
    res = evaluate(blind)
    m = res["mod_repo"]
    l = res["loader_repo"]

    print(f"\n══ BLIND SET ({res['n']} reports) ══")
    print(f"  parse errors      : {res['parse_errors']}")
    print(f"  diagnosed         : {_ci_str(res['diagnosed'], res['n'])}")
    print(f"  with root cause   : {_ci_str(res['root_cause'], res['n'])}")
    print("  by maintainer verdict:")
    for v, (n, d) in res["by_verdict"].items():
        star = " *" if v in CRASH_VERDICTS else ""
        print(f"    {v:24} {_pct(d, n)}{star}")
    print(f"  mod repos         : {_ci_str(m['diag'], m['n'])} diagnosed")
    print(f"  loader repos      : {_ci_str(l['diag'], l['n'])} diagnosed")

    print("\n══ ATTRIBUTION vs maintainer verdict (mod repos) ══")
    print("  bug_in_this_mod   -> top-1 SHOULD name the repo's mod")
    print(f"    correct   : {_pct(m['bug_hit'], m['bug_n'])}")
    print(f"    missed    : {_pct(m['bug_miss'], m['bug_n'])}  <- real blame errors")
    print(f"    no pick   : {_pct(m['bug_nopick'], m['bug_n'])}")
    print("  root_cause_elsewhere -> top-1 SHOULD be a DIFFERENT mod")
    print(f"    correct   : {_pct(m['else_correct'], m['else_n'])}")
    print(f"    blamed repo: {_pct(m['else_wrongrepo'], m['else_n'])}  <- real blame errors")
    print(f"    no pick   : {_pct(m['else_nopick'], m['else_n'])}")
    print(f"  ambiguous (known_issue/outdated, not scored): "
          f"{m['ambig_n']} reports, repo-named {m['ambig_repo']}")

    scored = m["bug_n"] + m["else_n"]
    blame_errors = m["bug_miss"] + m["else_wrongrepo"]
    if scored:
        print(f"\n  >>> BLAME-ERROR RATE (ROADMAP 1B.2 basis): "
              f"{_ci_str(blame_errors, scored)}")
        print("      (direction-aware: counts top-1 wrong for bug_in_this_mod "
              "AND top-1=repo for root_cause_elsewhere)")
        if scored < MIN_QUOTABLE_N:
            lo, hi = wilson(blame_errors, scored)
            print(f"      !! n={scored} is too small to quote as a rate. The same "
                  f"data is consistent with {lo:.0%}-{hi:.0%}. Quote the "
                  f"interval, or say 'we documented exactly {blame_errors} "
                  f"failure mode(s)', never the bare percentage.")

    if res["misattribution_samples"]:
        print("\n  blame-error samples (verify by hand -- weak labels err too):")
        for s in res["misattribution_samples"]:
            print(f"    {s['report']:22} verdict={s['verdict']:20} "
                  f"top={s['top_suspect'] or '-':18} repo={s['repo_mod']}")
    if res["good_external_samples"]:
        print("  correct-external samples:")
        for s in res["good_external_samples"]:
            print(f"    {s['report']:22} top={s['top_suspect']:18} "
                  f"(not {s['repo_mod']} -- matches root_cause_elsewhere)")

    if args.dev:
        dres = evaluate(dev)
        dm = dres["mod_repo"]
        d_scored = dm["bug_n"] + dm["else_n"]
        d_err = dm["bug_miss"] + dm["else_wrongrepo"]
        print(f"\n══ DEV SET comparison ({dres['n']} reports) ══")
        print(f"  diagnosed         : {_ci_str(dres['diagnosed'], dres['n'])}")
        print(f"  blame-error rate  : {_ci_str(d_err, d_scored)}")
        print("      (comparison only: dev reports motivated the rules, so a "
              "better dev number proves nothing about generalisation)")
        res["_dev"] = {"n": dres["n"], "diagnosed": dres["diagnosed"],
                       "bug_hit": dm["bug_hit"], "bug_n": dm["bug_n"],
                       "blame_errors": d_err, "scored": d_scored,
                       "ci": {"diagnosed": _ci(dres["diagnosed"], dres["n"]),
                              "blame_error": _ci(d_err, d_scored)}}

    doc = {
        "generated_by": "tools/blind_eval.py",
        "scoring": {
            "bug_in_this_mod": "top-1 should equal repo mod",
            "root_cause_elsewhere": "top-1 should be a different mod",
            "known_issue/outdated_version": "ambiguous, reported not scored",
        },
        "split": {"dev": len(dev), "blind": len(blind)},
        "blind": {k: v for k, v in res.items()
                  if k not in ("misattribution_samples",
                               "good_external_samples", "_dev")},
        # Every ratio above, with its 95% interval attached. The point estimate
        # alone is what gets copied into a README and then quoted as if it were
        # a property of the tool; at n=7 it is not.
        "ci95": {
            "method": "Wilson score interval, z=1.959963984540054",
            "min_quotable_n": MIN_QUOTABLE_N,
            "diagnosed": _ci(res["diagnosed"], res["n"]),
            "root_cause": _ci(res["root_cause"], res["n"]),
            "mod_repo_diagnosed": _ci(m["diag"], m["n"]),
            "loader_repo_diagnosed": _ci(l["diag"], l["n"]),
            "blame_error": _ci(blame_errors, scored),
            "by_verdict_diagnosed": {
                v: _ci(d, n) for v, (n, d) in res["by_verdict"].items()},
            # A ratio whose denominator is under MIN_QUOTABLE_N is a count, not
            # a rate. This flag travels with the data so a downstream consumer
            # cannot quote "14%" without having been told not to.
            "quotable_as_rate": {
                "diagnosed": res["n"] >= MIN_QUOTABLE_N,
                "blame_error": scored >= MIN_QUOTABLE_N,
            },
        },
        "misattribution_samples": res["misattribution_samples"],
        "good_external_samples": res["good_external_samples"],
    }
    if args.dev and "_dev" in res:
        doc["dev"] = res["_dev"]
    with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(args.json, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
