#!/usr/bin/env python
"""Decide each rule's lifecycle status from evidence, and notice when the
decision has changed.

WHY THIS EXISTS
  Four rules are `experimental` because nothing but a synthetic fixture has ever
  fired them: `oom.save-time`, `oom.gc-overhead`, `disk.space`, `native.gl`.
  `tools/stamp_provenance.py` knows how to *upgrade* them ("a real report fired
  this"), but nothing ever asked it to. The status was a hand-maintained
  constant, so the honest description of the mechanism was "upgrades happen when
  somebody remembers" -- which for four rules documents a process that has
  never run.

  This tool closes the loop in the cheap direction: a committed evidence
  snapshot (`corpus/rule-lifecycle.json`) binds every status to the corpus
  revision it was derived from, and `tests/test_rule_lifecycle.py` fails when
  the two disagree. So the promotion signal is a red gate, not a memory.

TWO KINDS OF STALENESS
  * the corpus changed -> `--write` (re-derive; ~40 s, parses 661 files once)
  * a rule earned promotion -> the YAML `lifecycle_status` line must change

  `--check` reports both without touching anything.

    python tools/rule_lifecycle.py            # print the table
    python tools/rule_lifecycle.py --check    # exit 1 if the snapshot is stale
    python tools/rule_lifecycle.py --write    # re-derive the snapshot

  Why this is not folded into the default pytest run: the derivation costs ~40 s
  because it parses all 661 reports, and today's answer is "0 of 4 promotable".
  The cheap half (digest + status comparison, ~0.2 s) IS in the default run, and
  it is the half that notices a changed corpus.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stamp_provenance import scan_corpus          # noqa: E402  (same dir)

OUT = os.path.join(ROOT, "corpus", "rule-lifecycle.json")


def corpus_files() -> list[str]:
    """Every report the derivation reads, in a stable order.

    Same three sources and same order as `stamp_provenance.scan_corpus()`, so
    the digest covers exactly the input that produced the verdicts. A new
    harvest or a new ground-truth fixture changes the digest; editing an
    unrelated markdown file does not.
    """
    pats = ("tests/fixtures/ground-truth/*.txt",
            "corpus/github/*/*.crash.txt",
            "corpus/aternos/**/*.log")
    files: list[str] = []
    for pat in pats:
        files.extend(sorted(glob.glob(os.path.join(ROOT, pat), recursive=True)))
    return files


def corpus_digest(files: list[str] | None = None) -> str:
    """sha256[:16] over (relative path, bytes) of every corpus report.

    Path and content both matter: renaming a report must invalidate the
    snapshot even if no byte changed, because the evidence keys in the JSON are
    derived from paths.
    """
    files = corpus_files() if files is None else files
    h = hashlib.sha256()
    for p in files:
        h.update(os.path.relpath(p, ROOT).replace(os.sep, "/").encode("utf-8"))
        h.update(b"\0")
        h.update(open(p, "rb").read())
        h.update(b"\0")
    return h.hexdigest()[:16]


def derive() -> dict:
    """Status + real-corpus evidence for every builtin rule.

    `real_evidence` comes from `scan_corpus()`, which is the single existing
    answer to "where does this rule fire" -- reusing it means this tool cannot
    disagree with the stamper that writes `provenance.fixtures`.
    """
    from mcd.rules.engine import RuleSet

    rs = RuleSet.load()
    scanned = scan_corpus()
    rules = {}
    for r in sorted(rs.rules, key=lambda r: r.id):
        real = list(scanned.get(r.id, []))
        prov = r.provenance or {}
        synthetic = [str(f) for f in prov.get("fixtures", [])
                     if str(f).startswith("synthetic/")]
        verdict = ("promote"
                   if r.lifecycle_status == "experimental" and real else "hold")
        rules[r.id] = {
            "lifecycle_status": r.lifecycle_status,
            "real_evidence": real,
            "synthetic_fixtures": synthetic,
            "verdict": verdict,
        }
    files = corpus_files()
    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "corpus": {
            "digest": corpus_digest(files),
            "files": len(files),
            # kept apart so a reader can tell which source carries the weight
            "ground_truth": len(glob.glob(os.path.join(
                ROOT, "tests/fixtures/ground-truth/*.txt"))),
            "harvested": len(glob.glob(os.path.join(
                ROOT, "corpus/github/*/*.crash.txt"))),
            "aternos": len(glob.glob(os.path.join(
                ROOT, "corpus/aternos/**/*.log"), recursive=True)),
        },
        "rules": rules,
    }


def load_snapshot() -> dict | None:
    try:
        with open(OUT, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def stale_reasons(snap: dict) -> list[str]:
    """Everything wrong with `snap` that a *cheap* check can see (no parsing).

    This is the half that runs in the default test suite, so it must never
    touch a report: digest + status comparison only.
    """
    bad = []
    if snap.get("corpus", {}).get("digest") != corpus_digest():
        bad.append("corpus changed since the snapshot was derived "
                   "-- run python tools/rule_lifecycle.py --write")
    from mcd.rules.engine import RuleSet
    live = {r.id: r.lifecycle_status for r in RuleSet.load().rules}
    recorded = {rid: v.get("lifecycle_status") for rid, v in snap["rules"].items()}
    for rid in sorted(set(live) - set(recorded)):
        bad.append(f"{rid}: in the rule packs but not in the snapshot")
    for rid in sorted(set(recorded) - set(live)):
        bad.append(f"{rid}: in the snapshot but no longer a rule")
    for rid in sorted(set(live) & set(recorded)):
        if live[rid] != recorded[rid]:
            bad.append(f"{rid}: status is {live[rid]!r} but the snapshot "
                       f"derived {recorded[rid]!r}")
    return bad


def promotion_due(snap: dict) -> list[str]:
    """Rules whose evidence has outgrown their status."""
    return [rid for rid, v in sorted(snap["rules"].items())
            if v.get("verdict") == "promote"]


def print_table(snap: dict) -> None:
    c = snap["corpus"]
    print(f"corpus {c['digest']} -- {c['files']} files "
          f"(ground truth {c['ground_truth']}, harvested {c['harvested']}, "
          f"aternos {c['aternos']})\n")
    by_status: dict[str, int] = {}
    for rid, v in sorted(snap["rules"].items()):
        by_status[v["lifecycle_status"]] = by_status.get(v["lifecycle_status"], 0) + 1
        if v["verdict"] == "promote" or v["lifecycle_status"] == "experimental":
            ev = v["real_evidence"]
            print(f"  {rid:22s} {v['lifecycle_status']:13s} "
                  f"real={len(ev):2d} synth={len(v['synthetic_fixtures'])} "
                  f"{v['verdict'].upper()}")
    print("\n  " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))
    due = promotion_due(snap)
    print(f"  promotion due: {due if due else 'none'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true",
                   help="re-derive and rewrite corpus/rule-lifecycle.json")
    g.add_argument("--check", action="store_true",
                   help="exit 1 if the committed snapshot is stale")
    ap.add_argument("--quiet", action="store_true",
                    help="with --write, do not print the table")
    args = ap.parse_args()

    if args.check:
        snap = load_snapshot()
        if snap is None:
            print(f"missing {os.path.relpath(OUT, ROOT)} -- run --write",
                  file=sys.stderr)
            return 1
        bad = stale_reasons(snap)
        for line in bad:
            print(f"STALE: {line}", file=sys.stderr)
        due = promotion_due(snap)
        for rid in due:
            print(f"PROMOTE: {rid} fires on real corpus reports "
                  f"({snap['rules'][rid]['real_evidence'][:2]}) -- set "
                  f"lifecycle_status: verified in the rule YAML", file=sys.stderr)
        ok = not bad and not due
        print("lifecycle snapshot is current" if ok else "lifecycle snapshot is stale")
        return 0 if ok else 1

    if args.write:
        snap = derive()
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(snap, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"wrote {os.path.relpath(OUT, ROOT)}")
        if not args.quiet:
            print_table(snap)
        due = promotion_due(snap)
        if due:
            # Non-zero on purpose: the snapshot now *contradicts* the YAML, and
            # the YAML is what users read. Writing and exiting 0 would let a
            # promotion sit in a JSON file that nothing gates on.
            print(f"\nPROMOTE {len(due)} rule(s): {due} -- update "
                  f"lifecycle_status in mcd/rules/builtin/*.yaml", file=sys.stderr)
            return 1
        return 0

    snap = load_snapshot() or derive()
    print_table(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
