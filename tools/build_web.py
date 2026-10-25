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
    (WEB / "wheel-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"web/{wheel.name}")
    print("web/wheel-manifest.json ->", json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
