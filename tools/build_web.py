#!/usr/bin/env python
"""Build the static web app: wheel + manifest into web/.

The browser app (web/index.html) loads Pyodide, micropip-installs the wheel
listed in web/wheel-manifest.json, and runs the SAME diagnosis code as the
CLI -- one engine, two frontends. Run this after any mcd/ change:

    python tools/build_web.py

CI (.github/workflows/pages.yml) runs it too, so the committed web/ assets
are only the fallback; Pages always deploys a fresh build.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

#: Files that end up inside the wheel.
_SHIPPED_SUFFIXES = (".py", ".yaml", ".yml")

#: What a visitor actually downloads when the page opens, measured on
#: 2026-10-25. This is a *structural* budget, not a byte-perfect one: ~30% of
#: headroom over the measured size, so ordinary edits pass and the failure modes
#: that matter do not --
#:
#:   * a new runtime dependency landing inside the wheel (the wheel is the only
#:     artifact that can grow by hundreds of KB overnight),
#:   * corpus data or a redacted report leaking into web/ (sample.js is
#:     generated from a 277 KB report; inlining the wrong one triples it),
#:   * a build that stops pruning ``__pycache__``/``.pyc``.
#:
#: Growth that is genuinely wanted is fine -- raise the number **here**, in the
#: same commit, and say why. The number is the record of a decision, not a
#: ceiling to route around. Measured then: app.js 35,376; index.html 13,841;
#: sample.js 78,366; wheel 92,551; manifest 146; total 220,280.
SIZE_BUDGET = {
    "app.js": 60_000,
    "index.html": 30_000,
    "sample.js": 105_000,
    "wheel": 125_000,
    "wheel-manifest.json": 1_000,
}
TOTAL_BUDGET = 330_000


def payload_sizes() -> dict[str, int]:
    """Size of every file web/ ships, with the wheel keyed as ``wheel``.

    Keyed by name rather than by path so the check survives the version bump in
    the wheel filename. Only files, no directories: browsers download files.
    """
    out: dict[str, int] = {}
    for p in sorted(WEB.iterdir()):
        if not p.is_file():
            continue
        out["wheel" if p.suffix == ".whl" else p.name] = p.stat().st_size
    return out


def budget_report(sizes: dict[str, int]) -> list[str]:
    """Return one line per violation; empty list means inside budget."""
    bad = []
    for name, limit in SIZE_BUDGET.items():
        got = sizes.get(name)
        if got is None:
            bad.append(f"{name}: missing from web/ (budget expects it)")
        elif got > limit:
            bad.append(f"{name}: {got:,} B > {limit:,} B budget")
    total = sum(sizes.values())
    if total > TOTAL_BUDGET:
        bad.append(f"web/ total: {total:,} B > {TOTAL_BUDGET:,} B budget")
    return bad


def source_digest() -> str:
    """sha256 over every shipped file under ``mcd/`` (path + bytes).

    WHY THIS EXISTS
    ---------------
    ``tests/test_web_bundle.py`` compared module *names*: it caught a wheel
    with a missing or deleted module, but not a wheel shipping last week's
    *contents*. That gap is not hypothetical -- fixing catastrophic regex
    backtracking in ``mcd/parser/report.py`` changed no file name, so the
    committed wheel kept the 9-second parser and every guard stayed green.

    The digest makes "run tools/build_web.py after any mcd/ change" an
    assertion instead of a comment in a docstring.
    """
    h = hashlib.sha256()
    for p in sorted((ROOT / "mcd").rglob("*")):
        if p.is_file() and p.suffix in _SHIPPED_SUFFIXES:
            h.update(p.relative_to(ROOT).as_posix().encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def main() -> int:
    WEB.mkdir(exist_ok=True)
    # drop old wheels so the manifest never points at a stale artifact
    for old in WEB.glob("*.whl"):
        old.unlink()

    print("building wheel ...")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(WEB)],
        cwd=ROOT, check=True,
        stdout=subprocess.DEVNULL,
    )
    wheels = sorted(WEB.glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected exactly 1 wheel in web/, found {len(wheels)}", file=sys.stderr)
        return 1
    wheel = wheels[0]

    # regenerate the demo report (redacted real fixture) so the committed
    # web/sample.js never drifts from the engine that diagnoses it
    print("building web/sample.js ...")
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_web_sample.py")],
                   cwd=ROOT, check=True)

    manifest = {"file": wheel.name, "source_digest": source_digest()}
    # newline="\n" on purpose: this is a committed artifact, and letting Python
    # translate to CRLF on Windows turns every rebuild on a Windows machine into
    # a whole-file diff on a repo that stores LF.
    with open(WEB / "wheel-manifest.json", "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2) + "\n")
    print(f"web/{wheel.name}")
    print("web/wheel-manifest.json ->", json.dumps(manifest))

    sizes = payload_sizes()
    print("web/ payload: " + ", ".join(f"{k} {v:,}" for k, v in sizes.items())
          + f" (total {sum(sizes.values()):,} B)")
    # Warn here, fail in tests/test_web_bundle.py: a build that cannot produce
    # an artifact is worse than a build that says it is over budget.
    for line in budget_report(sizes):
        print(f"OVER BUDGET: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
