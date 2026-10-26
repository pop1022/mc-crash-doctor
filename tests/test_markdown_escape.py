"""Markdown 输出必须能被真正解析成表格。

`--markdown` 的用途是贴进 issue/PR。崩溃报告的异常消息里出现 `|` 完全正常
（位掩码、正则、`a|b` 表示的选择），而一个未转义的 `|` 会把两列表格变成五列，
GitHub 上显示成一堆错位的文字。

这里同时钉住反向：正常内容不能被过度转义。
"""
from __future__ import annotations

from mcd.parser.report import parse_text
from mcd.pack.doctor import PackReport
from mcd.pack.render import render_pack_markdown
from mcd.report.render import render_markdown
from mcd.textfmt import md_cell

REPORT = """\
---- Minecraft Crash Report ----
// Why is it always the bad ones?

Time: 2026-10-26 12:00:00
Description: Ticking entity

java.lang.RuntimeException: expected mask a|b but got c|d (flags 0x1|0x2)
\tat net.minecraft.server.MinecraftServer.tick(MinecraftServer.java:1)
\tat net.minecraft.client.main.Main.main(Main.java:1)
\tat java.lang.Thread.run(Thread.java:1)

-- System Details --
Details:
\tMinecraft Version: 1.21.1
\tJava Version: 17.0.8, Microsoft
"""


def _cells(row: str) -> int:
    """Count table cells the way a markdown parser would."""
    body = row.strip()
    assert body.startswith("|") and body.endswith("|"), row
    return body.count("|") - body.count("\\|") - 1


# --- the helper -------------------------------------------------------------
def test_pipe_is_escaped():
    assert md_cell("a|b") == "a\\|b"


def test_newline_does_not_end_the_row():
    assert md_cell("a\nb") == "a b"
    assert md_cell("a\r\nb") == "a b"


def test_backslash_is_escaped_before_the_pipe():
    """`a\\|b` must not become an escape-of-an-escape that eats the pipe."""
    assert md_cell("a\\|b") == "a\\\\\\|b"


def test_plain_text_is_untouched():
    assert md_cell("fabric 0.16.0") == "fabric 0.16.0"
    assert md_cell(42) == "42"


# --- crash report markdown --------------------------------------------------
def _env_rows(report_text: str) -> list[str]:
    rep = parse_text(report_text)
    out: list[str] = []
    render_markdown(rep, [], None, _Sink(out))
    return [ln for ln in out if ln.startswith("|")]


class _Sink:
    def __init__(self, buf: list[str]):
        self.buf = buf

    def write(self, s: str) -> None:
        self.buf.extend(s.splitlines())


def test_environment_table_keeps_two_columns_when_root_cause_has_pipes():
    """The reported bug: 5 cells instead of 2, table unparseable."""
    rows = [r for r in _env_rows(REPORT) if "Root cause" in r]
    assert rows, "root cause row missing"
    assert _cells(rows[0]) == 2, rows[0]


def test_every_environment_row_has_two_columns():
    for row in _env_rows(REPORT):
        assert _cells(row) == 2, row


def test_clean_report_rows_are_not_over_escaped():
    """Reverse control: escaping must be invisible on ordinary content."""
    clean = REPORT.replace("a|b but got c|d (flags 0x1|0x2)", "something went wrong")
    rows = [r for r in _env_rows(clean) if "Root cause" in r]
    assert rows and "\\|" not in rows[0]


# --- pack markdown ----------------------------------------------------------
def _pack_rows(report: PackReport) -> list[str]:
    out: list[str] = []
    render_pack_markdown(report, _Sink(out))
    return [ln for ln in out if ln.startswith("|")]


def test_pack_table_survives_a_pipe_in_the_subject():
    rep = PackReport(root="/pack", mods_dir="mods", jars=2, declared_mods=2)
    rep.undecided = [{"modid": "a|b", "required_by": "c|d",
                      "range": ">=1.0|<2.0", "installed": "1|1"}]
    rows = [r for r in _pack_rows(rep) if "a\\|b" in r]
    assert rows, "undecided row missing or unescaped"
    assert _cells(rows[0]) == 4, rows[0]
