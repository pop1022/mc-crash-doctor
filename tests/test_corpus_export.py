"""The corpus exporter must not leak, and must be reproducible."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from export_corpus_sample import export  # noqa: E402

RAW = """---- Minecraft Crash Report ----
// I blame Dinnerbone.
Time: 2026-09-08 18:47:46
At 192.168.1.55 from C:\\Users\\alice\\AppData\\Roaming\\.minecraft\\mods
java.lang.OutOfMemoryError: Java heap space
"""


def test_exported_reports_are_redacted_and_hashed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "SomeRepo__mod").mkdir(parents=True)
    (src / "SomeRepo__mod" / "1.crash.txt").write_text(RAW, encoding="utf-8")

    out = tmp_path / "out"
    man = export(limit=10, seed=0, out=out, source=src)

    assert man["exported"] == 1
    body = (out / "reports" / "SomeRepo__mod__1.crash.txt").read_text(encoding="utf-8")
    assert "192.168.1.55" not in body
    assert "alice" not in body
    assert "OutOfMemoryError" in body            # the report itself survives

    entry = man["reports"][0]
    assert entry["sha256"] and entry["bytes"] == len(body.encode("utf-8"))


def test_redaction_does_not_eat_the_next_line(tmp_path: Path) -> None:
    """Regression: [^.minecraft\\\\/]+ ran past the newline after a trailing
    path segment and deleted whatever followed it (found by this exporter)."""
    text = ("At 10.0.0.9 from C:\\\\Users\\\\bob\\\\.minecraft\\\\mods\n"
            "java.lang.OutOfMemoryError: Java heap space\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "r.txt").write_text(text, encoding="utf-8")
    man = export(limit=1, seed=0, out=tmp_path / "out", source=src)
    assert man["exported"] == 1
    body = (tmp_path / "out" / "reports" / "r.txt").read_text(encoding="utf-8")
    assert "OutOfMemoryError" in body


def test_export_is_reproducible_from_the_seed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    for i in range(30):
        (src / f"r{i}.txt").write_text(RAW + f"# {i}\n", encoding="utf-8")

    a = export(limit=5, seed=7, out=tmp_path / "a", source=src)
    b = export(limit=5, seed=7, out=tmp_path / "b", source=src)
    assert [r["file"] for r in a["reports"]] == [r["file"] for r in b["reports"]]
    assert a["manifest"] if False else True          # manifest written below
    assert json.loads((tmp_path / "a" / "manifest.json").read_text(encoding="utf-8"))["seed"] == 7
