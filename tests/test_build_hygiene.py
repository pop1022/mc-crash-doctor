"""What web/ is allowed to contain, and what used to sneak in.

A screenshot left in web/ during a manual check became part of the shipped
payload (520 KB, caught only because it blew the total budget). A small stray
would have shipped silently. The allowlist makes "served" an explicit list.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_web():
    spec = importlib.util.spec_from_file_location("build_web", ROOT / "tools" / "build_web.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_stray_screenshot_is_reported(tmp_path: Path, monkeypatch) -> None:
    bw = build_web()
    (tmp_path / "app.js").write_text("x", encoding="utf-8")
    (tmp_path / "_shot.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(bw, "WEB", tmp_path)
    assert bw.stray_files() == ["_shot.png"]
    report = "\n".join(bw.budget_report(bw.payload_sizes()))
    assert "_shot.png" in report and "shipped set" in report


def test_the_shipped_files_are_all_known(tmp_path: Path, monkeypatch) -> None:
    bw = build_web()
    for name in bw.SHIPPED:
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "mc_crash_doctor-0.1.0-py3-none-any.whl").write_bytes(b"x")
    monkeypatch.setattr(bw, "WEB", tmp_path)
    assert bw.stray_files() == []


def test_the_dead_count_up_script_stays_deleted() -> None:
    # moment.js looked for [data-count], an attribute only the removed mock
    # verdict ever emitted: 1.3 KB and a request that did nothing.
    assert not (ROOT / "web" / "moment.js").exists()
    assert "moment.js" not in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
