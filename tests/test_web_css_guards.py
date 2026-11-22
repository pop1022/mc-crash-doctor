"""Two CSS decisions that are invisible until they are wrong.

Both were verified in a headless browser first (reduced motion zeroed the
420 ms entrance animation; a light OS preference still produced a dark page).
These assertions keep the declarations from being deleted by a later cleanup.
"""
from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def test_reduced_motion_is_honoured_in_one_place() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1][:300]
    assert "--dur-long: 0ms" in block


def test_the_page_declares_its_dark_scheme() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    tokens = (WEB / "tokens.css").read_text(encoding="utf-8")
    assert "color-scheme: dark" in css or "color-scheme: dark" in tokens


def test_the_hero_statement_may_wrap() -> None:
    import re
    css = re.sub(r"/\*.*?\*/", "", (WEB / "styles.css").read_text(encoding="utf-8"), flags=re.S)
    statement = css.split(".statement {", 1)[1].split("}", 1)[0]
    # A no-wrap declaration made the block 329 px wide in a 288 px column.
    assert "nowrap" not in statement
