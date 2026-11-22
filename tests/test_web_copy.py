"""Wording the product promises: evidence strength, and two refusals.

The 97% number is a weighted score, not a calibrated chance of being right.
Saying "confidence" made it read as the latter in three places (label, hero,
rules section). These assertions keep the correction from being undone.
"""
from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def test_the_label_is_evidence_strength_in_both_languages() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    assert js.count('"verdict.confidence": "证据强度"') == 1
    assert js.count('"verdict.confidence": "evidence"') == 1
    assert "置信度" not in js


def test_the_card_says_what_the_number_is_not() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    assert js.count('"verdict.strengthNote"') == 2
    assert "不是校准过的" in js


def test_both_languages_can_refuse_an_hs_err_and_an_exit_code() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    for key in ("val.hsErr", "val.exitCode"):
        assert js.count(f'"{key}"') == 2, key


def test_the_page_copy_stopped_calling_it_confidence() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "置信度" not in html

# --- where the file is ------------------------------------------------------
def test_the_page_answers_where_the_file_is() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<details class="where">' in html
    assert html.count('class="where__row"') == 5
    for launcher in ("官方启动器", "Prism", "Modrinth", "服务端"):
        assert launcher in html


def test_the_paths_are_not_double_escaped() -> None:
    # A doubled backslash renders as "C:\\Users" and looks like a bug in the
    # product, not a path. Both languages and the static markup are checked.
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "\\\\\\\\." not in js.split('"where.vanilla"')[1][:160]
    assert "\\\\\\\\.minecraft" not in html


def test_both_languages_explain_the_four_launchers() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    for key in ("where.summary", "where.lead", "where.vanilla", "where.prism",
                "where.modrinth", "where.server"):
        assert js.count(f'"{key}"') == 2, key

def test_the_status_line_keeps_its_base_class() -> None:
    """Assigning only the kind wiped "status" after the first paint."""
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    assert 'el.className = "status" +' in js

# --- the four-part card -----------------------------------------------------
def test_the_card_reads_what_evidence_action_then_verification() -> None:
    js = (WEB / "src" / "30-render.js").read_text(encoding="utf-8")
    anchor = js.index('class="anchor"')
    start = js.index('class="starthere"')
    verify = js.index('class="verify"')
    assert anchor < start < verify, (anchor, start, verify)


def test_every_card_label_exists_in_both_languages() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    for key in ("verdict.anchor", "verify.title", "verify.body",
                "verify.undoTitle", "verify.undo", "verify.anchorFallback"):
        assert js.count(f'"{key}"') == 2, key


def test_verification_uses_the_specific_evidence_line() -> None:
    """The first evidence entry is the exception class; every Java crash has it."""
    js = (WEB / "src" / "30-render.js").read_text(encoding="utf-8")
    assert "ev[ev.length - 1]" in js
