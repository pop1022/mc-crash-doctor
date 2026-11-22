"""Terminal output must fit the banner, in both languages.

The old wrapper split on spaces. Chinese has none, so a 117-character
explanation came out as one 117-character line -- about twice the width of the
banner above it -- and the terminal wrapped it at arbitrary places. Display
width, not character count, is the property that matters.
"""
from __future__ import annotations

import io
from pathlib import Path

from mcd.parser.report import parse_file
from mcd.report.render import (_basename, _display_width, _wrap, render_plain)
from mcd.rules.engine import RuleSet, run_rules
from mcd.triage.attribution import triage

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"
WATCHDOG = GT / "crash-2026-09-08_22.42.32-server.txt"     # suspect + long text
BANNER = 74


def render(lang: str) -> str:
    rep = parse_file(str(WATCHDOG))
    findings = run_rules(rep, RuleSet.load(), lang=lang)
    buf = io.StringIO()
    render_plain(rep, findings, triage(rep), buf)
    return buf.getvalue()


def test_every_line_fits_the_banner_in_chinese() -> None:
    for line in render("zh").splitlines():
        assert _display_width(line) <= BANNER, line


def test_every_line_fits_the_banner_in_english() -> None:
    for line in render("en").splitlines():
        assert _display_width(line) <= BANNER, line


def test_chinese_is_wrapped_not_one_long_line() -> None:
    text = "单个 tick 花了 120.00 秒" * 8
    lines = _wrap(text, 66)
    assert len(lines) >= 3
    assert all(_display_width(ln) <= 66 for ln in lines)
    # Numbers and latin words stay whole.
    assert not any(ln.startswith("00") for ln in lines), lines


def test_a_line_never_starts_with_closing_punctuation() -> None:
    text = "看最上面的栈帧，找被阻塞的代码路径：同步 IO、超大的区块操作，或者死锁。" * 3
    for ln in _wrap(text, 40):
        assert ln[0] not in "、。，；：）", ln


def test_wide_characters_count_two() -> None:
    assert _display_width("abc") == 3
    assert _display_width("中文") == 4
    assert _display_width("中a") == 3


def test_the_source_line_shows_a_basename() -> None:
    out = render("en")
    assert "crash-2026-09-08_22.42.32-server.txt" in out
    assert "tests" not in out.split("source")[1].splitlines()[0]

def test_an_embedded_newline_starts_a_new_line() -> None:
    assert _wrap("first line\nsecond line", 40) == ["first line", "second line"]


def test_hanging_punctuation_is_allowed_one_column_over() -> None:
    lines = _wrap("abc。", 4)
    assert lines == ["abc。"], lines        # 5 columns on a 66-column page is fine


def test_latin_words_are_not_split_when_a_space_is_available() -> None:
    assert _wrap("hello world", 10) == ["hello", "world"]


def test_a_long_run_without_spaces_is_broken_hard() -> None:
    lines = _wrap("a" * 12, 5)
    assert lines == ["aaaaa", "aaaaa", "aa"]


def test_basename_handles_both_separators() -> None:
    assert _basename("C:\\Users\\x\\crash.txt") == "crash.txt"
    assert _basename("logs/crash.txt") == "crash.txt"
    assert _basename("<stdin>") == "<stdin>"

def test_explain_output_fits_the_banner(capsys) -> None:
    from mcd.cli import main
    assert main([str(WATCHDOG), "--text", "--explain"]) == 0
    text = capsys.readouterr().out
    for line in text.splitlines():
        assert _display_width(line) <= BANNER, line


def test_explain_footer_does_not_suggest_the_flag_already_passed(capsys) -> None:
    from mcd.cli import main
    assert main([str(WATCHDOG), "--text", "--explain"]) == 0
    assert "--explain  shows how the score was built" not in capsys.readouterr().out


def test_a_dotted_class_name_breaks_at_its_dot_not_mid_name(capsys) -> None:
    from mcd.cli import main
    assert main([str(WATCHDOG), "--text"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.rstrip().endswith("ReflectionUtil.") for ln in lines), lines
    assert not any("ReflectionUtil.ha" in ln for ln in lines)
    assert not any(ln.strip().startswith("sMethodOverride") for ln in lines)


def test_root_cause_does_not_end_in_a_half_word(capsys) -> None:
    from mcd.cli import main
    assert main([str(WATCHDOG), "--text"]) == 0
    out = capsys.readouterr().out
    # signature (the grouping key) cuts at 80 chars; the terminal header must
    # not inherit that cut and print "(shoul" as if the report had a typo.
    assert "(should be max 0.05)" in out
