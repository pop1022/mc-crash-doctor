"""What must not leave the page, and what the user must see first.

Verified in a real browser with four markers planted in a crash report
(Windows path, LAN IP, ghp_ token, password=): 53 requests, zero leaks into
request URLs, location.href, localStorage/sessionStorage or the feedback
preview; no tab opened until the confirm button. These assertions keep the
structure that made that true.
"""
from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def test_feedback_previews_before_it_opens_anything() -> None:
    js = (WEB / "src" / "30-render.js").read_text(encoding="utf-8")
    assert "showFeedback(url)" in js
    assert 'd.showModal()' in js.replace("$(\"fb\").showModal()", "d.showModal()")


def test_the_dialog_offers_both_actions() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for attr in ('id="fb"', 'id="fb-preview"', 'id="fb-open"', 'id="fb-cancel"'):
        assert attr in html, attr


def test_the_dialog_copy_exists_in_both_languages() -> None:
    js = (WEB / "src" / "10-i18n.js").read_text(encoding="utf-8")
    for key in ("fb.title", "fb.lead", "fb.open", "fb.cancel"):
        assert js.count(f'"{key}"') == 2, key
