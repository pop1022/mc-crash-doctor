#!/usr/bin/env python
"""Coverage floors for the modules where a silent gap would cost the most.

    python tools/coverage_gate.py --run     # measure, then check
    python tools/coverage_gate.py           # check the existing .coverage

WHY FLOORS, NOT A TARGET
  "Raise coverage" is not a task anyone finishes; a floor is. Each number below
  is the measured baseline minus one or two points, so a real regression trips
  it while a refactor that moves lines between files does not. Floors are per
  package, not per file: mcd/pack/render.py sitting at 80% is a rendering
  branch, not a hole in the pack checker, and splitting the threshold per file
  would turn every rename into a gate edit.

WHY SOME FILES ARE EXEMPT (each with its reason, printed)
  cli.py, extract.py, __main__.py and __init__.py are entry points and network
  plumbing. Gate 5 runs the CLI end to end in a subprocess and gate 4 exercises
  diagnose() in-process, so the behaviour is covered even though the lines are
  not. Listing them is the point: "exempt" is a decision, silence is not.

WHY metadata SITS BELOW 85
  Measured 84.9: 67 of its 76 missed statements are manifest.py TOML error
  branches (malformed mods.toml, wrong types). They are real paths worth
  testing, but padding the floor to look uniform would hide exactly this.

Without coverage installed the gate exits 0 with a visible skip -- CI installs
.[test], which carries it; a contributor without it should not be blocked.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: package prefix -> floor. Baseline measured 2026-11-17 on Python 3.12.
FLOORS = {
    "mcd/parser": 93.0,
    "mcd/triage": 92.0,
    "mcd/rules": 86.0,
    "mcd/pack": 90.0,
    "mcd/report": 91.0,
    "mcd/metadata": 83.0,
}

TOTAL_FLOOR = 85.0

#: file -> (floor, reason). Checked, reported, and never silently ignored.
EXEMPT = {
    "mcd/cli.py": (65.0, "argparse plumbing; gate 5 runs the CLI end to end"),
    "mcd/extract.py": (60.0, "URL fetch + decode; needs the network to reach"),
    "mcd/__main__.py": (0.0, "two-line entry point, covered by gate 5"),
    "mcd/__init__.py": (50.0, "re-export shim, imported by every test"),
}


def _rel(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def measure() -> dict[str, tuple[int, int]]:
    """rel path -> (statements, missed) for everything under mcd/."""
    import coverage

    cov = coverage.Coverage()
    cov.load()
    out: dict[str, tuple[int, int]] = {}
    for f in cov.get_data().measured_files():
        rel = _rel(f)
        if not rel.startswith("mcd/"):
            continue
        _name, stmts, _excl, missing, _fmt = cov.analysis2(f)
        out[rel] = (len(stmts), len(missing))
    return out


def check(sizes: dict[str, tuple[int, int]]) -> list[str]:
    bad: list[str] = []
    total_s = sum(s for s, _ in sizes.values())
    total_m = sum(m for _, m in sizes.values())

    print(f"{'package':<18}{'cover':>8}{'floor':>8}   result")
    for prefix, floor in FLOORS.items():
        files = [(s, m) for p, (s, m) in sizes.items()
                 if p == prefix or p.startswith(prefix + "/")]
        if not files:
            bad.append(f"{prefix}: no measured file (did the package move?)")
            print(f"{prefix:<18}{'-':>8}{floor:>7.1f}%   MISSING")
            continue
        s = sum(a for a, _ in files)
        m = sum(b for _, b in files)
        pct = 100.0 * (s - m) / s if s else 100.0
        ok = pct >= floor
        print(f"{prefix:<18}{pct:>7.1f}%{floor:>7.1f}%   "
              + ("ok" if ok else "BELOW FLOOR"))
        if not ok:
            bad.append(f"{prefix}: {pct:.1f}% < {floor:.1f}%")

    pct = 100.0 * (total_s - total_m) / total_s if total_s else 100.0
    ok = pct >= TOTAL_FLOOR
    print(f"{'TOTAL':<18}{pct:>7.1f}%{TOTAL_FLOOR:>7.1f}%   "
          + ("ok" if ok else "BELOW FLOOR"))
    if not ok:
        bad.append(f"total: {pct:.1f}% < {TOTAL_FLOOR:.1f}%")

    print("\nexempt (floor still enforced, reason printed):")
    for name, (floor, reason) in EXEMPT.items():
        s, m = sizes.get(name, (0, 0))
        pct = 100.0 * (s - m) / s if s else 100.0
        print(f"  {name:<20}{pct:>6.1f}%  floor {floor:.0f}%  -- {reason}")
        if pct < floor:
            bad.append(f"{name}: {pct:.1f}% < exempt floor {floor:.0f}%")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true",
                    help="run the suite under coverage first (~55 s)")
    args = ap.parse_args()

    try:
        import coverage  # noqa: F401
    except ImportError:
        print("coverage not installed -- gate skipped (pip install coverage)")
        return 0

    if args.run:
        r = subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--source=mcd",
             "-m", "pytest", "tests/", "-q",
             f"--basetemp=tmp/.cov-{os.getpid()}"],
            cwd=ROOT)
        if r.returncode != 0:
            print("the suite failed under coverage; fix that before the floors",
                  file=sys.stderr)
            return 1

    sizes = measure()
    if not sizes:
        print("no coverage data -- run with --run first", file=sys.stderr)
        return 2
    bad = check(sizes)
    if bad:
        print("\nbelow floor:")
        for line in bad:
            print("  " + line)
        return 1
    print("\nall floors met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
