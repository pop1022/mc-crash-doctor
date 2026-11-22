"""web/app.js is built from web/src/*.js -- and the build is checked.

Why a build step at all: Pyodide loads through a classic script tag and the page
has to work over file:// as well as Pages, so the runtime must stay one script.
The split exists for the reader (55 KB in one file meant scrolling a thousand
lines to change one label). This test is what keeps the two honest: edit a
source and app.js must be rebuilt, not hand-edited.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SRC = WEB / "src"

#: A logic part bigger than this is drifting back into a monolith. The i18n
#: table is excluded: it is data, and it grows with translation, not with code.
LOGIC_CAP = 16 * 1024


def parts() -> list[Path]:
    return sorted(SRC.glob("*.js"))


def test_sources_exist_and_are_ordered() -> None:
    names = [p.name for p in parts()]
    assert names == ["00-config.js", "10-i18n.js", "20-engine.js",
                     "30-render.js", "40-wire.js"]


def test_app_js_is_exactly_the_concatenation() -> None:
    built = "".join(p.read_text(encoding="utf-8") for p in parts())
    assert (WEB / "app.js").read_text(encoding="utf-8") == built, (
        "web/app.js is stale: run python tools/build_web.py (edit web/src, "
        "never app.js itself)")


def test_logic_parts_stay_small() -> None:
    for p in parts():
        if p.name == "10-i18n.js":
            continue
        size = len(p.read_text(encoding="utf-8").encode("utf-8"))
        assert size <= LOGIC_CAP, f"{p.name} is {size:,} B, over {LOGIC_CAP:,}"


def test_index_html_still_loads_one_classic_script() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in html
    assert 'type="module"' not in html
    assert 'src="src/' not in html


def test_no_source_file_contains_a_script_close_tag() -> None:
    # A literal </script> inside the concatenated bundle would end the tag the
    # page uses to load it, which fails at runtime and nowhere else.
    for p in parts():
        assert "</script>" not in p.read_text(encoding="utf-8"), p.name
