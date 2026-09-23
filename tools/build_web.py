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

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


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

    manifest = {"file": wheel.name}
    (WEB / "wheel-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"web/{wheel.name}")
    print("web/wheel-manifest.json ->", json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
