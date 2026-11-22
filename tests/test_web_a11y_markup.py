"""Markup-level accessibility: the parts that can regress in a diff.

Browser-level behaviour (focus after a diagnosis, contrast ratios) was checked
by hand with a headless browser; these assertions are the ones that would
otherwise disappear silently the next time someone edits index.html.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"


class _Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def parsed() -> _Collect:
    p = _Collect()
    p.feed(INDEX.read_text(encoding="utf-8"))
    return p


def find(tag: str, **attrs) -> list[dict]:
    out = []
    for name, got in parsed().tags:
        if name != tag:
            continue
        if all(got.get(k) == v for k, v in attrs.items()):
            out.append(got)
    return out


def test_the_skip_link_targets_a_focusable_main() -> None:
    skip = [a for a in find("a") if a.get("href") == "#main"]
    assert skip, "skip link missing"
    main = find("main")
    assert main and main[0].get("id") == "main"
    # Without tabindex=-1 the browser moves the scroll position but leaves
    # focus on <body>, so the next Tab starts from the top again.
    assert main[0].get("tabindex") == "-1"


def test_language_buttons_are_buttons_and_announce_state() -> None:
    for lang in ("zh", "en"):
        btn = find("button", id=f"lang-{lang}")
        assert btn, lang
        assert btn[0].get("type") == "button"
        assert btn[0].get("aria-pressed") in ("true", "false")


def test_the_result_container_is_a_named_region() -> None:
    out = find("div", id="out")
    assert out, "#out missing"
    # aria-label on a plain div is ignored by assistive tech.
    assert out[0].get("role") == "region"
    assert out[0].get("aria-label")


def test_the_status_line_is_a_live_region() -> None:
    status = find("p", id="status") or find("div", id="status") or find("span", id="status")
    assert status, "#status missing"
    assert status[0].get("role") == "status"
    assert status[0].get("aria-live") == "polite"


def test_every_image_has_alt_text() -> None:
    for img in find("img"):
        assert img.get("alt"), img


def test_every_button_has_a_name() -> None:
    """A button with no text and no aria-label is announced as "button"."""
    html = INDEX.read_text(encoding="utf-8")
    for chunk in html.split("<button")[1:]:
        body = chunk.split("</button>")[0]
        head, _, text = body.partition(">")
        assert "aria-label" in head or text.strip(), body[:80]
