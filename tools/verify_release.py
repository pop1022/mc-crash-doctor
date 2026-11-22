"""Install the built artifacts and check them the way a user would.

The release workflow used to assert `mc-crash-doctor --version` in a venv
created with `--no-deps`, which cannot import mcd at all (PyYAML is a hard
dependency), so the step only ever proved that a broken install stays broken
quietly. This script does the real check and is the one place it happens:
release.yml calls it, and it can be run locally on a developer machine.

    python -m build
    python tools/verify_release.py dist --sums

Exit code 0 only if every check passes. Nothing here publishes anything.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CRASH = """---- Minecraft Crash Report ----
// There are four lights!

Time: 2026-09-08 18:01:19
Description: Exception ticking world

java.lang.OutOfMemoryError: Java heap space
\tat net.minecraft.world.level.Level.tick(Level.java:1)
"""

LOG = """[12:00:00] [Server thread/INFO]: Starting minecraft server version 1.20.1
[12:03:10] [Server thread/WARN]: Can't keep up! Is the server overloaded?
[12:03:11] [Server thread/FATAL]: Unreported exception thrown!
java.lang.OutOfMemoryError: Java heap space
"""


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def expected_rule_ids() -> set[str]:
    """What the source tree says the rule set is.

    corpus/rule-lifecycle.json is the snapshot the lifecycle tests keep equal to
    RuleSet.load(); using it here means a stale wheel is caught by id, not by a
    hard-coded number that someone forgets to bump.
    """
    snap = ROOT / "corpus" / "rule-lifecycle.json"
    if snap.exists():
        data = json.loads(snap.read_text(encoding="utf-8"))
        rules = data.get("rules") or {}
        if rules:
            return set(rules)
    ids: set[str] = set()
    for path in (ROOT / "mcd" / "rules" / "builtin").glob("*.yaml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- id:"):
                ids.add(line.split(":", 1)[1].strip())
    return ids


def tag_matches(tag: str, version: str) -> bool:
    """v0.1.0 == 0.1.0; v0.2.0 != 0.1.0 (PyPI would publish the wrong version)."""
    return tag.lstrip("v") == version


def newest(dist: Path, pattern: str) -> Path | None:
    found = sorted(glob.glob(str(dist / pattern)))
    return Path(found[-1]) if found else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_wheel_contents(wheel: Path, failures: list[str]) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    packs = [n for n in names if n.endswith((".yaml", ".yml"))]
    if not packs:
        failures.append(f"{wheel.name}: ships no YAML rule packs")
    bad = [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    if bad:
        failures.append(f"{wheel.name}: ships bytecode ({bad[:2]})")
    print(f"  wheel contents: {len(packs)} rule pack(s), no bytecode")


def venv_python(venv: Path) -> Path:
    win = venv / "Scripts" / "python.exe"
    return win if win.exists() else venv / "bin" / "python"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dist", nargs="?", default="dist", help="directory with sdist + wheel")
    ap.add_argument("--sums", action="store_true", help="write SHA256SUMS into dist/")
    ap.add_argument("--tag", help="release tag to compare against the built version")
    ap.add_argument("--keep", action="store_true", help="keep the temporary venv")
    args = ap.parse_args(argv)

    dist = Path(args.dist)
    wheel = newest(dist, "*.whl")
    sdist = newest(dist, "*.tar.gz")
    if not wheel or not sdist:
        print(f"error: need a wheel and an sdist in {dist}", file=sys.stderr)
        return 2

    failures: list[str] = []
    print(f"artifacts: {wheel.name} + {sdist.name}")
    check_wheel_contents(wheel, failures)

    tmp = Path(tempfile.mkdtemp(prefix="mcd-verify-"))
    venv = tmp / "venv"
    print(f"creating venv: {venv}")
    r = _run([sys.executable, "-m", "venv", str(venv)])
    if r.returncode:
        print(r.stderr, file=sys.stderr)
        return 2
    py = venv_python(venv)

    # Dependencies, not --no-deps: PyYAML is required at import time, and the
    # old workflow's --no-deps install could never have run this line.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)          # prove the wheel, not the checkout
    print("pip install (with dependencies)")
    r = _run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
              str(wheel.resolve())], env=env, cwd=str(tmp))
    if r.returncode:
        print(r.stdout[-2000:] + r.stderr[-2000:], file=sys.stderr)
        failures.append("pip install failed")
        report(failures)
        return 1

    def installed(expr: str) -> tuple[int, str, str]:
        p = _run([str(py), "-c", expr], env=env, cwd=str(tmp))
        return p.returncode, p.stdout.strip(), p.stderr.strip()

    # 1. import comes from site-packages, not from a checkout
    rc, out, err = installed("import mcd, sys; print(mcd.__file__); print(sys.version.split()[0])")
    if rc:
        failures.append(f"import mcd failed: {err[-200:]}")
    else:
        path, pyver = out.splitlines()
        print(f"  import: {path} (python {pyver})")
        if "site-packages" not in path.replace("\\", "/"):
            failures.append(f"mcd imported from {path}, not site-packages")

    # 2. version
    rc, out, _ = installed("import mcd; print(mcd.__version__)")
    print(f"  version: {out or '?'}")
    src_version = _run([sys.executable, "-c",
                        "import mcd; print(mcd.__version__)"], cwd=str(ROOT))
    if src_version.returncode == 0 and src_version.stdout.strip() != out:
        failures.append(f"wheel version {out!r} != source {src_version.stdout.strip()!r}")
    if args.tag:
        if tag_matches(args.tag, out):
            print(f"  tag {args.tag}: matches {out}")
        else:
            failures.append(f"tag {args.tag!r} != version {out!r} -- PyPI would "
                            f"publish the wrong version")

    # 3. rules match the source manifest, by id
    rc, out, err = installed(
        "from mcd.rules.engine import RuleSet;"
        "print('\\n'.join(sorted(r.id for r in RuleSet.load().rules)))")
    if rc:
        failures.append(f"RuleSet.load() failed in the wheel: {err[-300:]}")
    else:
        got = set(out.splitlines())
        want = expected_rule_ids()
        missing, extra = want - got, got - want
        print(f"  rules: {len(got)} installed, {len(want)} expected")
        if missing:
            failures.append(f"wheel is missing rules: {sorted(missing)[:5]}")
        if extra:
            failures.append(f"wheel has unknown rules: {sorted(extra)[:5]}")

    # 4. diagnose a crash from stdin, as JSON
    p = _run([str(py), "-m", "mcd", "--stdin", "--json"], input=CRASH, env=env, cwd=str(tmp))
    if p.returncode != 0:
        failures.append(f"--stdin --json exited {p.returncode}: {p.stderr[-300:]}")
    else:
        doc = json.loads(p.stdout)
        ids = [f["rule_id"] for f in doc.get("findings", [])]
        print(f"  diagnosis: {ids or 'no findings'}")
        if "oom.heap" not in ids:
            failures.append(f"expected oom.heap, got {ids}")

    # 5. timeline entry point
    p = _run([str(py), "-m", "mcd", "--stdin", "--timeline"], input=LOG, env=env, cwd=str(tmp))
    if p.returncode != 0 or "events in window" not in p.stdout:
        failures.append(f"--timeline did not report events: {p.stderr[-200:]}")

    # 6. pack entry point (exit 2 on an empty dir is the documented answer)
    empty = tmp / "empty-pack"
    empty.mkdir()
    p = _run([str(py), "-m", "mcd", "--pack", str(empty)], env=env, cwd=str(tmp))
    if p.returncode != 2 or "no `mods/` directory" not in p.stderr:
        failures.append(f"--pack on an empty dir: exit {p.returncode}")

    # 7. checksums
    sums = dist / "SHA256SUMS"
    lines = []
    for f in (wheel, sdist):
        lines.append(f"{sha256(f)}  {f.name}")
    if args.sums:
        sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  wrote {sums}")
    for line in lines:
        print(f"  sha256 {line}")

    if not args.keep:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"kept venv at {venv}")
    return report(failures)


def report(failures: list[str]) -> int:
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nrelease verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
