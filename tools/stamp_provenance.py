#!/usr/bin/env python
"""Stamp `provenance` + `lifecycle_status` into every builtin rule (ROADMAP 1A.3).

Single source of truth: each rule's YAML carries the real report(s) or
synthetic fixture(s) that prove it, and tests/test_gaps.py reads its pins
from that metadata instead of a hardcoded dict.

Provenance sources, in priority order:
  1. hand-written pins (the historical test_gaps PINS -- the reports that
     motivated each rule),
  2. corpus scan evidence: up to 3 files per rule where it actually fires
     (ground-truth / aternos / harvested), scanned live unless --skip-scan.

lifecycle_status:
  - rules with a REAL-corpus fixture (harvested issue, ground truth, or an
    aternos hit) -> verified
  - rules proven only by synthetic fixtures -> experimental (upgrade to
    verified when a real report fires them)

Text-level insertion on purpose: the rule YAMLs are heavily commented and
PyYAML round-trips destroy comments. Idempotent -- re-running replaces the
previous provenance block.

    python tools/stamp_provenance.py [--skip-scan] [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BUILTIN = os.path.join(ROOT, "mcd", "rules", "builtin")

# Hand-written pins carried over from tests/test_gaps.py (reports that
# motivated the rule) and tests/test_rule_fixtures.py (synthetic proofs).
HARVESTED_PINS = {
    "mod.load-failed.neoforge": ["mekanism/8631", "mekanism/8633"],
    "mod.load-failed.fabric-entry": ["mekanism/8391", "mekanism/8479",
                                     "mekanism/8539"],
    "mod.client-class-on-server": ["mekanism/8354"],
    "crash.threading-race": ["mekanism/8531"],
    "crash.datapack-book": ["mekanism/8423"],
    "crash.rendering-blockentity": ["mekanism/8518"],
    "crash.runtime-mod": ["mekanism/8590", "mekanism/8483"],
    "mod.incompatible-set": ["sodium/3524", "sodium/3813"],
    "mod.corrupt-jar": ["fabric-loader/685", "fabric-api/4907"],
    "mod.binary-incompat": ["fabric-loader/611", "sodium/3711"],
    "mod.linkage-duplicate": ["quilt-loader/232"],
    "quilt.config-broken": ["quilt-loader/261"],
    "loader.namespace-missing": ["quilt-loader/497"],
    "mixin.injection-failed": ["fabric-api/5097"],
    "crash.registry-load-failed": ["fabric-api/4862"],
    "net.connectivity": ["quilt-loader/344"],
    "env.headless-jvm": ["quilt-loader/398"],
}
EXPECT_SUSPECTS = {
    "crash.runtime-mod": {"mekanism/8590": "mekanism",
                          "mekanism/8483": "create"},
}
SYNTHETIC_PINS = {
    "oom.save-time": ["synthetic/oom-save-time.txt"],
    "oom.gc-overhead": ["synthetic/oom-gc-overhead.txt"],
    "disk.space": ["synthetic/disk-space.txt"],
    "native.gl": ["synthetic/native-gl.txt"],
}


def scan_corpus() -> dict[str, list[str]]:
    """rule_id -> up to 3 representative corpus files where it fires.

    Keys: 'gt:<name>' (ground truth), 'aternos:<name>', 'harvested:<repo>/<n>'.
    Slow (~5 min: parses every corpus file once)."""
    from mcd.parser.report import parse_file
    from mcd.rules.engine import RuleSet, run_rules
    rs = RuleSet.load()
    hits: dict[str, list[str]] = {r.id: [] for r in rs.rules}

    def note(rid: str, key: str, limit: int) -> None:
        lst = hits.setdefault(rid, [])
        if len(lst) < limit and key not in lst:
            lst.append(key)

    # ground truth first (strongest), then harvested (breadth), aternos last
    for f in sorted(glob.glob(os.path.join(
            ROOT, "tests/fixtures/ground-truth/*.txt"))):
        rep = parse_file(f)
        for fd in run_rules(rep, rs):
            note(fd.rule_id, f"gt:{os.path.basename(f)}", 1)
    for f in sorted(glob.glob(os.path.join(
            ROOT, "corpus/github/**/*.crash.txt"), recursive=True)):
        rel = os.path.relpath(f, os.path.join(ROOT, "corpus/github"))
        rel = rel.replace(os.sep, "/")
        repo, num = rel.split("/", 1)
        key = f"harvested:{repo.split('__')[-1]}/{num[:-10]}"
        rep = parse_file(f)
        for fd in run_rules(rep, rs):
            note(fd.rule_id, key, 2)
    for f in sorted(glob.glob(os.path.join(
            ROOT, "corpus/aternos/**/*.log"), recursive=True)):
        rep = parse_file(f)
        for fd in run_rules(rep, rs):
            note(fd.rule_id, f"aternos:{os.path.basename(f)}", 1)
    return {k: v for k, v in hits.items() if v}


def rule_blocks(text: str, id_indent: str) -> list[tuple[int, int, str]]:
    """[(start, end, rule_id)] line-index spans for each '- id:' block."""
    lines = text.splitlines()
    pat = re.compile(rf"^{re.escape(id_indent)}- id:\s*(\S+)\s*$")
    starts = [(i, m.group(1)) for i, l in enumerate(lines)
              if (m := pat.match(l))]
    out = []
    for n, (i, rid) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        out.append((i, end, rid))
    return out


def strip_old_provenance(block_lines: list[str], fld: str) -> list[str]:
    """Remove an existing provenance:/lifecycle_status: field from a block."""
    out, skipping, skip_indent = [], False, 0
    for l in block_lines:
        m = re.match(r"^(\s*)(provenance|lifecycle_status):", l)
        if m and m.group(2) == fld:
            skipping = True
            skip_indent = len(m.group(1))
            continue
        if skipping:
            # continuation lines are deeper-indented or list items
            if l.strip() and (len(l) - len(l.lstrip())) > skip_indent:
                continue
            if l.strip().startswith("- ") and \
                    (len(l) - len(l.lstrip())) >= skip_indent:
                continue
            skipping = False
        out.append(l)
    return out


def make_provenance(rid: str, fld: str, scanned: dict[str, list[str]]) -> list[str]:
    fixtures = list(HARVESTED_PINS.get(rid, []))
    fixtures += SYNTHETIC_PINS.get(rid, [])
    seen = set(fixtures)
    for k in scanned.get(rid, []):
        if k not in seen:
            fixtures.append(k)
            seen.add(k)
    real = any(not f.startswith("synthetic/") for f in fixtures)
    status = "verified" if real else "experimental"

    lines = [f"{fld}provenance:"]
    sub = fld + "  "
    if fixtures:
        lines.append(f"{sub}fixtures:")
        for f in fixtures[:6]:
            lines.append(f"{sub}- {f}")
    sus = EXPECT_SUSPECTS.get(rid)
    if sus:
        lines.append(f"{sub}expect_suspects:")
        for k, v in sus.items():
            lines.append(f'{sub}  "{k}": {v}')
    if not real:
        lines.append(f"{sub}notes: synthetic-fixture proof only -- upgrade to"
                     f" verified when a real report fires this rule")
    lines.append(f"{fld}lifecycle_status: {status}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-scan", action="store_true",
                    help="use hand pins only (fast; no corpus evidence)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    scanned = {} if args.skip_scan else scan_corpus()
    if not args.skip_scan:
        print(f"corpus scan: {len(scanned)} rules with evidence")

    for name in sorted(os.listdir(BUILTIN)):
        if not name.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(BUILTIN, name)
        text = open(path, encoding="utf-8").read()
        # detect indent: '- id:' at col 0 (memory-performance) or col 2
        id_indent = "" if re.search(r"^- id:", text, re.M) else "  "
        fld = id_indent + "  "
        lines = text.splitlines()
        changed = False
        # process blocks bottom-up so line indices stay valid
        for start, end, rid in reversed(rule_blocks(text, id_indent)):
            block = lines[start:end]
            block = strip_old_provenance(block, "provenance")
            block = strip_old_provenance(block, "lifecycle_status")
            # trim trailing blanks, remember them
            tail = []
            while block and not block[-1].strip():
                tail.insert(0, block.pop())
            block.extend(make_provenance(rid, fld, scanned))
            block.extend(tail)
            lines[start:end] = block
            changed = True
        new = "\n".join(lines)
        if not text.endswith("\n"):
            pass
        else:
            new += "\n"
        if new != text:
            if args.dry_run:
                print(f"would update {name}")
            else:
                open(path, "w", encoding="utf-8", newline="").write(new)
                print(f"stamped {name}")
        elif changed:
            print(f"unchanged {name}")

    # verify the engine still loads and every rule has provenance
    if not args.dry_run:
        from mcd.rules.engine import RuleSet
        rs = RuleSet.load()
        assert not rs.errors, rs.errors
        missing = [r.id for r in rs.rules if not r.provenance.get("fixtures")]
        exp = [r.id for r in rs.rules if r.lifecycle_status == "experimental"]
        print(f"\nrules: {len(rs.rules)}  without fixtures: {missing or 'none'}")
        print(f"experimental: {exp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
