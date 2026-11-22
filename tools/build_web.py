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
    # 58 -> 60 -> 64 KB on 2026-11-18: the app grew a not-a-report card, an
    # oversize-paste guard (MAX_BYTES used to cover file drops only) and the
    # precomputed-sample path with its note. UI states, not features; still one
    # classic script.
    # 64 -> 68 KB on 2026-11-22: two refusals (hs_err, bare exit code) plus the
    # bilingual "where is the file" block. Both are copy, and copy is what the
    # two languages cost; no new dependency.
    "app.js": 68_000,
    "index.html": 30_000,
    "sample.js": 105_000,
    # 125 KB -> 145 KB on 2026-11-17: the Chinese rule copy (title_zh /
    # explanation_zh / fixes_zh) ships inside the YAML, so every translated
    # rule adds to the wheel -- 46/46 rules now carry it. Real content, not a
    # dependency, and it compresses away in transit.
    # 145 -> 150 KB on 2026-11-17: mcd/pack/mixins.py (refmap reader) joined the
    # package; it is small but it is code, not a dependency.
    # 150 -> 155 KB the same day: mcd/rules/expect.py (per-rule fixture
    # assertions). Both are engine code the browser wheel legitimately carries;
    # the next KB has to be argued here again.
    # 155 -> 160 KB on 2026-11-18: input guards in mcd/cli.py (empty, oversize,
    # not-a-report) and the heuristic they share with the web box. Behaviour,
    # not dependencies.
    # 160 -> 165 KB on 2026-11-19: headline vs signature split in the model, the
    # markdown table fixes (_md_code, numbered fixes), and the batch summary.
    # All of it is shipped code; the wheel is the browser's engine, so it moves
    # with the CLI -- that is the point of shipping one wheel.
    "wheel": 165_000,
    "wheel-manifest.json": 1_000,
}
# 330 -> 340 KB for the same reason: the wheel is ~99% of the payload, so a new
# module moves the total with it. Growth still has to be argued here, which is
# the point of having the number at all.
# 345 -> 360 KB on 2026-11-18: two precomputed sample diagnoses (zh/en, ~4 KB
# each) plus the loader that shows one before Pyodide is ready. They buy the
# first click an instant answer instead of a nine-second wait.
# 360 -> 370 KB on 2026-11-19: the same engine growth (headline, markdown,
# batch summary). Still dominated by the wheel (~45%) and sample.js (~22%).
# 370 -> 385 KB on 2026-11-22: the same copy, now in two languages and two
# places (bundle + static markup). The alternative was trimming the guidance a
# first-time user needs; keeping the number tight is only useful if it still
# leaves room for one honest section.
TOTAL_BUDGET = 385_000

#: Assets live in subdirectories, which the file-level loop below skips ("only
#: files, no directories"). That blind spot is how 560 KB of images and 60 KB of
#: self-hosted fonts arrived without a single failing gate. Budgeted per folder
#: so the page's real weight stays a decision, not an accident.
ASSET_BUDGET = {
    "img": 700_000,
    "fonts": 90_000,
}


APP_PARTS = WEB / "src"


def build_app_js() -> tuple[int, int]:
    """Concatenate web/src/*.js into web/app.js. Returns (files, bytes).

    Why a build step and not ES modules: Pyodide is loaded by a classic script
    tag and the page has to work from file:// as well as Pages. One script keeps
    the runtime shape fixed -- the split is for whoever reads the code, and a
    load-order mistake would surface as a blank page, not a failing test. The
    test suite compares the concatenation with the committed app.js, so editing
    app.js directly fails loudly instead of being overwritten later.
    """
    parts = sorted(APP_PARTS.glob("*.js"))
    if not parts:
        return 0, 0
    text = "".join(p.read_text(encoding="utf-8") for p in parts)
    # newline="": write_text would turn \n into \r\n on Windows, making the
    # built file differ from its sources byte-for-byte and dirtying the diff.
    with (WEB / "app.js").open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return len(parts), len(text.encode("utf-8"))


#: Files web/ is allowed to serve. Anything else is a stray (a screenshot, a
#: scratch script) that would otherwise ship and, if small enough, slip under
#: the total budget without anyone noticing.
SHIPPED = {
    "app.js", "index.html", "styles.css", "tokens.css", "base.css",
    "sample.js", "sample-diagnosis.zh.json", "sample-diagnosis.en.json",
    "wheel-manifest.json",
}


def stray_files() -> list[str]:
    """Top-level files under web/ that are not part of the shipped set."""
    out = []
    for p in sorted(WEB.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix == ".whl" or p.name in SHIPPED:
            continue
        out.append(p.name)
    return out


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


def asset_sizes() -> dict[str, int]:
    """Total bytes per asset folder under ``web/`` (img, fonts, ...)."""
    out: dict[str, int] = {}
    for d in sorted(WEB.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            out[d.name] = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
    return out


def budget_report(sizes: dict[str, int]) -> list[str]:
    """Return one line per violation; empty list means inside budget."""
    bad = []
    for name in stray_files():
        bad.append(f"web/{name}: not part of the shipped set -- delete it or "
                   f"add it to SHIPPED in tools/build_web.py")
    for name, limit in ASSET_BUDGET.items():
        got = asset_sizes().get(name, 0)
        if got > limit:
            bad.append(f"web/{name}/: {got:,} B > {limit:,} B asset budget")
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
    files, app_bytes = build_app_js()
    if files:
        print(f"app.js <- {files} source files ({app_bytes:,} B)")
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

    # `bytes` lets the page notice a stale folder before booting: the CLI
    # already learned that a wheel which is not rebuilt after a source edit
    # imports the wrong code silently (test_manifest_source_digest_matches_mcd).
    manifest = {"file": wheel.name, "source_digest": source_digest(),
                "bytes": wheel.stat().st_size,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
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
