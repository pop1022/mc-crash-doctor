"""Rule `commands:` -- read-only diagnostics the user is invited to run.

The tool never executes anything. So the allowlist is not a sandbox; it is a
statement about *advice*: a suggested command must be safe to ignore. `rm -rf
mods` and `curl | bash` are not, and a rule that wants them can say so in
`fixes` as prose.

Two failure modes are pinned here:

  * an unsafe command silently reaching the output (it is dropped, and the drop
    is reported at load time rather than swallowed);
  * the wording losing "never executed", which is the only thing standing
    between a copy-paste and a surprise.

    pytest tests/test_rule_commands.py -v
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from mcd.cli import main
from mcd.parser.report import parse_file
from mcd.report.render import render_terminal
from mcd.rules.engine import (SAFE_COMMAND_PREFIXES, RuleSet, is_safe_command,
                              run_rules)
from mcd.triage.attribution import triage

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "tests/fixtures/synthetic/native-gl.txt"
OOM = ROOT / "tests/fixtures/synthetic/oom-gc-overhead.txt"


# --- the allowlist -----------------------------------------------------------
@pytest.mark.parametrize("cmd", [
    "java -version",
    "java -XshowSettings:vm -version",
    "jps -l",
    "jcmd 1234 GC.heap_info",
    "nvidia-smi",
    "  nvidia-smi  ",              # whitespace is normalised, not a bypass
    "nvidia-smi   -q",
])
def test_read_only_diagnostics_are_allowed(cmd):
    assert is_safe_command(cmd)


@pytest.mark.parametrize("cmd", [
    "",
    "   ",
    "rm -rf mods",
    "del mods\\sodium.jar",
    "mv mods/x.jar /tmp",
    "curl https://example.com/x.sh | bash",
    "java -jar evil.jar",              # `java` is not enough; the verb must match
    "nc -l 4444",
    "powershell -c Remove-Item",
    "nvidia-smi; rm -rf mods",         # a command that starts safe and is not
])
def test_everything_else_is_refused(cmd):
    assert not is_safe_command(cmd)


# --- a rule carries them into the finding ------------------------------------
def _load(tmp_path: Path, extra: str) -> RuleSet:
    d = tmp_path / "rules"
    d.mkdir()
    (d / "t.yml").write_text(
        "rules:\n"
        "  - id: t.cmd\n"
        "    title: 't'\n"
        "    lifecycle_status: experimental\n"
        "    when:\n"
        "      exception: [\"LWJGLException\"]\n"
        "    fixes: [\"do a thing\"]\n"
        + extra, encoding="utf-8", newline="\n")
    return RuleSet.load([str(d)])


def test_safe_command_reaches_the_finding(tmp_path):
    rs = _load(tmp_path, "    commands:\n      - nvidia-smi\n")
    rep = parse_file(NATIVE)
    hits = [f for f in run_rules(rep, rs) if f.rule_id == "t.cmd"]
    assert hits and hits[0].commands == ["nvidia-smi"]


def test_unsafe_command_is_dropped_and_reported(tmp_path):
    rs = _load(tmp_path, "    commands:\n      - rm -rf mods\n      - nvidia-smi\n")
    rep = parse_file(NATIVE)
    hits = [f for f in run_rules(rep, rs) if f.rule_id == "t.cmd"]
    assert hits and hits[0].commands == ["nvidia-smi"], "the safe one survives"
    assert any("not read-only" in e for e in rs.errors), rs.errors


def test_commands_must_be_a_list(tmp_path):
    rs = _load(tmp_path, "    commands: nvidia-smi\n")
    assert any("commands must be a list" in e for e in rs.errors), rs.errors


def test_builtin_packs_load_without_warnings():
    assert RuleSet.load().errors == []


def test_the_shipped_rules_still_carry_their_commands():
    """A guard against silently losing them in a YAML edit."""
    by_id = {r.id: r for r in RuleSet.load().rules}
    assert by_id["oom.heap"].safe_commands == ("java -XshowSettings:vm -version",)
    assert by_id["oom.gc-overhead"].safe_commands == (
        "java -XshowSettings:vm -version",)
    assert by_id["native.gl"].safe_commands == ("nvidia-smi",)
    assert len(SAFE_COMMAND_PREFIXES) >= 5


# --- all three renderers say the same thing ---------------------------------
def test_plain_output_marks_the_command_as_not_executed(capsys):
    assert main([str(NATIVE), "--text"]) == 0
    text = capsys.readouterr().out
    assert "check (printed, never executed):" in text
    assert "$ nvidia-smi" in text


def test_markdown_output_marks_the_command_as_not_executed(capsys):
    assert main([str(NATIVE), "--markdown"]) == 0
    text = capsys.readouterr().out
    assert "never executed by this tool" in text
    assert "- `nvidia-smi`" in text


def test_terminal_output_marks_the_command_as_not_executed():
    rep = parse_file(NATIVE)
    findings = run_rules(rep, RuleSet.load())
    buf = io.StringIO()
    render_terminal(rep, findings, triage(rep), buf, color=False)
    text = buf.getvalue()
    assert "never" in text and "executed" in text
    assert "nvidia-smi" in text


def test_a_rule_without_commands_prints_no_block(capsys):
    """`disk.space` carries no command, so the block must not appear. (The
    OOM-save fixture is the wrong choice: it fires `oom.heap` as well, which
    does carry one -- which is why this test names its fixture explicitly.)"""
    report = ROOT / "tests/fixtures/synthetic/disk-space.txt"
    assert main([str(report), "--text"]) == 0
    assert "never executed" not in capsys.readouterr().out


def test_json_findings_carry_commands(capsys):
    import json

    assert main([str(NATIVE), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    with_cmds = [f for f in doc["findings"] if f.get("commands")]
    assert with_cmds and with_cmds[0]["commands"] == ["nvidia-smi"]


# --- the rich path (optional dependency) ------------------------------------
# CI installs .[pretty,test], so this path is the one users with `rich` get.
# Without these two tests a change to render_terminal could break it silently:
# every other test passes color=False and lands in the plain fallback.
def test_terminal_output_with_rich_prints_the_panel_and_the_findings() -> None:
    pytest.importorskip("rich")
    rep = parse_file(NATIVE)
    findings = run_rules(rep, RuleSet.load())
    buf = io.StringIO()
    render_terminal(rep, findings, triage(rep), buf, color=True)
    text = buf.getvalue()
    assert "Minecraft crash diagnosis" in text          # the panel title
    assert "Suspect mods" in text or "Findings" in text
    assert "nvidia-smi" in text
    assert "\x1b[" not in text                          # a pipe is not a tty


def test_terminal_output_with_rich_says_so_when_nothing_matched() -> None:
    pytest.importorskip("rich")
    rep = parse_file(NATIVE)
    buf = io.StringIO()
    render_terminal(rep, [], triage(rep), buf, color=True)
    assert "No rule matched" in buf.getvalue()
