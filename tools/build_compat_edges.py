#!/usr/bin/env python
"""Build compatibility edges from the harvested corpus (ROADMAP 1A.2).

This is the data pipeline for VISION product line 5 (Compatibility Graph),
built YEARS before the graph product ships -- because the graph eats
structured data, and retrofitting accumulated data later is the expensive
path. For now it only RECORDS edges; nothing queries them.

Design (deliberately NOT the naive "one row per mod per report"):
  Raw per-report presence would emit ~11.5k low-signal rows (a 241-mod pack
  makes every mod "co-occur" with every crash). Instead we aggregate into the
  CompatibilityClaim shape from VISION §4.3, deduped by
  (subject, object, relation, loader, mc_version), carrying evidence_count +
  source reports + the maintainer's weak-supervision verdict. Same information,
  far fewer rows, and already in the target schema.

Relations:
  caused       -- subject is the top suspect for the crash (game's first
                  `Suspected Mods` entry if present, else our triage top-1).
                  subject == object.
  suspected    -- subject is a secondary suspect. subject == object.
  co_occurred  -- subject was present (Mod List) in a report where `object`
                  was blamed. Weak presence evidence; the pairwise lift is
                  computed later, not here.

Offline & deterministic: diagnosis stays a pure function (no side effects);
this tool reads the gitignored harvested corpus + the committed index and
writes corpus/compat-edges.jsonl. Re-runnable; output is reproducible.

    python tools/build_compat_edges.py [--out corpus/compat-edges.jsonl]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcd.parser.report import parse_file          # noqa: E402
from mcd.triage.attribution import triage          # noqa: E402

GITHUB = os.path.join(ROOT, "corpus", "github")
INDEX = os.path.join(ROOT, "corpus", "index.jsonl")


def load_index() -> dict[str, dict]:
    """repo/issue -> index record (for url + weak-supervision verdict)."""
    idx: dict[str, dict] = {}
    if not os.path.exists(INDEX):
        return idx
    for line in open(INDEX, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        key = f"{d['repo'].split('/')[-1]}/{d['number']}"
        idx[key] = d
    return idx


def source_of(path: str, idx: dict[str, dict]) -> dict:
    rel = os.path.relpath(path, GITHUB).replace(os.sep, "/")
    repo_dir, num = rel.split("/", 1)
    issue = num[:-10] if num.endswith(".crash.txt") else num
    short = repo_dir.split("__")[-1]
    rec = idx.get(f"{short}/{issue}", {})
    return {
        "repo": rec.get("repo", short),
        "issue": int(issue) if issue.isdigit() else issue,
        "url": rec.get("url", ""),
        "verdict": rec.get("verdict"),
    }


def mod_version(rep, modid: str) -> str | None:
    m = rep.mod_by_id(modid)
    return (m.version or None) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "corpus", "compat-edges.jsonl"))
    ap.add_argument("--no-cooccurred", action="store_true",
                    help="emit only caused/suspected (high-signal) edges")
    args = ap.parse_args()

    idx = load_index()
    # (subject, object, relation, loader, mc) -> aggregate
    agg: dict[tuple, dict] = {}

    def bump(subject, obj, relation, loader, mc, src, *,
             version=None, confidence=None, evidence=None):
        if not subject:
            return
        key = (subject, obj, relation, loader or "", mc or "")
        a = agg.get(key)
        if a is None:
            a = agg[key] = {
                "subject": subject, "object": obj, "relation": relation,
                "loader": loader or None, "mc_version": mc or None,
                "mod_version": version,
                "evidence_count": 0, "source_reports": [],
                "maintainer_verdict": None, "confidence": confidence,
                "sample_evidence": evidence,
                "first_seen": None, "last_seen": None,
            }
        a["evidence_count"] += 1
        # keep at most 5 source refs per claim
        if len(a["source_reports"]) < 5:
            a["source_reports"].append(
                {k: src[k] for k in ("repo", "issue", "url")})
        if src.get("verdict") and not a["maintainer_verdict"]:
            a["maintainer_verdict"] = src["verdict"]
        if version and not a["mod_version"]:
            a["mod_version"] = version
        if confidence is not None:
            a["confidence"] = max(a["confidence"] or 0.0, confidence)

    files = sorted(glob.glob(os.path.join(GITHUB, "**", "*.crash.txt"),
                             recursive=True))
    n_caused = n_susp = n_cooc = 0
    for f in files:
        try:
            rep = parse_file(f)
        except Exception:
            continue
        src = source_of(f, idx)
        loader = rep.system.loader or None
        mc = rep.system.minecraft_version or None

        # rank suspects: game's own line first (strongest), then our triage
        game = list(rep.suspected_mods)
        t = triage(rep)
        ours = [(s.modid, s.confidence,
                 (s.reasons[0] if s.reasons else "")) for s in t.suspects]

        blamed = []
        if game:
            blamed.append((game[0], 0.95, "game 'Suspected Mods' (first listed)"))
            blamed.extend((g, 0.8, "game 'Suspected Mods'") for g in game[1:3])
        for mid, conf, reason in ours:
            if mid not in [b[0] for b in blamed]:
                blamed.append((mid, conf, reason))

        if not blamed:
            continue

        top = blamed[0]
        bump(top[0], top[0], "caused", loader, mc, src,
             version=mod_version(rep, top[0]), confidence=top[1],
             evidence=top[2][:160])
        n_caused += 1
        for mid, conf, reason in blamed[1:4]:
            bump(mid, mid, "suspected", loader, mc, src,
                 version=mod_version(rep, mid), confidence=conf,
                 evidence=reason[:160])
            n_susp += 1

        if not args.no_cooccurred and rep.mods:
            blamed_ids = {b[0] for b in blamed}
            for m in rep.mods:
                mid = (m.modid or "").lower()
                if not mid or mid in blamed_ids:
                    continue
                bump(mid, top[0], "co_occurred", loader, mc, src,
                     version=m.version or None)
                n_cooc += 1

    # deterministic order, then write
    rows = sorted(agg.values(),
                  key=lambda a: (a["relation"], -a["evidence_count"],
                                 a["subject"], a["object"]))
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        for a in rows:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    by_rel = defaultdict(int)
    for a in rows:
        by_rel[a["relation"]] += 1
    print(f"fragments scanned : {len(files)}")
    print(f"raw edges         : caused={n_caused} suspected={n_susp} "
          f"co_occurred={n_cooc}")
    print(f"aggregated claims : {len(rows)} -> {args.out}")
    for rel in ("caused", "suspected", "co_occurred"):
        print(f"    {rel:12} {by_rel[rel]}")
    size = os.path.getsize(args.out)
    print(f"file size         : {size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
