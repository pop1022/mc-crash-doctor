#!/usr/bin/env python
"""Snapshot the parser's output over the whole harvested corpus, then diff.

WHY THIS EXISTS
  Refactors of `mcd/parser/` are supposed to be behaviour-preserving, and the
  claim "output is byte-identical" is normally checked by... reading the diff
  and hoping. That works for a 3-line change and fails for a regex rewrite in
  the middle of a table parser, where the interesting cases are the 40 reports
  nobody opened.

  This tool turns the claim into a comparison. It records, for every report,
  what the parser extracted -- mod rows (as a hash, so the diff line names the
  report, not 1,047 lines of mod list), exception and frame counts, suspected
  mods, loader, kind.

    python tools/parser_snapshot.py --write /tmp/before.json
    ... refactor ...
    python tools/parser_snapshot.py --check /tmp/before.json

  `--check` exits 1 and prints the differing reports. Used for the
  `_parse_forge_modlist` rewrite (ROADMAP 1E.2), where it confirmed 454/454
  reports unchanged and 11,583 mod rows preserved while the corpus pass went
  from 250.8 s to 30.7 s.

  A snapshot is a *tool artifact*, not fixtures: keep it outside the repo (or
  gitignore it). It is only meaningful against the same corpus revision.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GITHUB = ROOT / "corpus" / "github"


def _mods_sig(mods) -> str:
    blob = "\n".join(f"{m.file}|{m.name}|{m.modid}|{m.version}|{m.status}"
                     for m in mods)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _frames_sig(exceptions) -> str:
    """Hash of every frame's (cls, method, line).

    Counts alone cannot tell a frame *normalisation* change from a no-op: the
    number of frames stays the same while every `cls` moves. In the frame-parse
    repair (ROADMAP 1E.5) this field is what named the 148 affected reports.
    """
    blob = "\n".join(f"{f.cls}|{f.method}|{f.line_no or ''}"
                     for e in exceptions for f in e.frames)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _frame_defects(exceptions) -> int:
    """Frames whose `cls` still holds brackets/parens -- i.e. the parser gave up
    and copied the whole line. Should be 0; any other value is a regression."""
    return sum(1 for e in exceptions for f in e.frames
               if ")" in (f.cls or "") or "]" in (f.cls or ""))


def _frames_glued(exceptions) -> int:
    """Frames whose raw line still contains a second frame after the first `)`.

    Separate from `_frame_defects` on purpose: that one spots the damage (a `)`
    inside `cls`), this one spots the *cause* (two frames on one line) and stays
    meaningful even if a future change stops copying the debris into `cls`.
    Both should be 0 on the current corpus.
    """
    from mcd.parser.report import GLUED_FRAME_RE
    return sum(1 for e in exceptions for f in e.frames
               if GLUED_FRAME_RE.search(f.raw or ""))


def snapshot() -> dict:
    from mcd.parser.report import parse_file

    files = sorted(glob.glob(str(GITHUB / "*" / "*.crash.txt")))
    if not files:
        sys.exit("no harvested corpus -- run tools/harvest_corpus.py")

    out: dict[str, dict] = {}
    t0 = time.perf_counter()
    for i, p in enumerate(files, 1):
        rep = parse_file(p)
        key = os.path.relpath(p, GITHUB).replace(os.sep, "/")
        out[key] = {
            "mods": len(rep.mods),
            "mods_sig": _mods_sig(rep.mods),
            "exc": len(rep.exceptions),
            "frames": sum(len(e.frames) for e in rep.exceptions),
            "frames_sig": _frames_sig(rep.exceptions),
            "frame_defects": _frame_defects(rep.exceptions),
            "frames_glued": _frames_glued(rep.exceptions),
            "suspected": rep.suspected_mods,
            "loader": rep.system.loader,
            "kind": rep.kind,
        }
        if i % 100 == 0:
            print(f"  {i}/{len(files)} ...", file=sys.stderr)
    dt = time.perf_counter() - t0

    print(f"{len(out)} reports in {dt:.1f}s "
          f"({sum(v['mods'] for v in out.values())} mod rows in "
          f"{sum(1 for v in out.values() if v['mods'])} reports)")
    return out


def compare(before: dict, after: dict) -> list[str]:
    diffs = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        if a is None:
            diffs.append(f"+ {key} (new report)")
        elif b is None:
            diffs.append(f"- {key} (report gone)")
        elif a != b:
            fields = [f for f in a if a.get(f) != b.get(f)]
            detail = "; ".join(
                f"{f}: {a.get(f)!r} -> {b.get(f)!r}" for f in fields)
            diffs.append(f"~ {key}: {detail}")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", metavar="PATH", help="record a snapshot")
    ap.add_argument("--check", metavar="PATH",
                    help="compare the current parser against a snapshot")
    args = ap.parse_args()
    if not (args.write or args.check):
        ap.error("pass --write PATH or --check PATH")

    current = snapshot()

    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=0, sort_keys=True) + "\n",
                        encoding="utf-8")
        print(f"wrote {path}")
    if args.check:
        before = json.loads(Path(args.check).read_text(encoding="utf-8"))
        diffs = compare(before, current)
        if diffs:
            print(f"\n{len(diffs)} report(s) differ:", file=sys.stderr)
            for line in diffs[:40]:
                print("  " + line, file=sys.stderr)
            if len(diffs) > 40:
                print(f"  ... and {len(diffs) - 40} more", file=sys.stderr)
            return 1
        print(f"identical: {len(current)} reports, "
              f"{sum(v['mods'] for v in current.values())} mod rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
