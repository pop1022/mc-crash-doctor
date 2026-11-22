"""Two inputs that are not crash reports, and must not be diagnosed anyway.

An hs_err log is a native crash (driver, native library); an exit code on its
own says the process died, not why. Both used to come out as "no rule matched",
which reads like the tool looked and found nothing -- it looked at the wrong
thing.
"""
from __future__ import annotations

import io

from mcd.cli import main
from mcd.input_kind import classify, is_exit_code_only, is_hs_err

HS = """#
# A fatal error has been detected by the Java Runtime Environment:
#
#  EXCEPTION_ACCESS_VIOLATION (0xc0000005) at pc=0x0000000000000000
# Problematic frame:
# C  [ig8icd64.dll+0x1f10]
#
"""

REPORT = """---- Minecraft Crash Report ----
Description: Ticking entity

java.lang.OutOfMemoryError: Java heap space
\tat a.b.C.d(C.java:1)
"""


def test_an_hs_err_log_is_named_as_such() -> None:
    assert is_hs_err(HS)
    assert classify(HS) == "hs_err"
    assert not is_hs_err(REPORT)


def test_a_bare_exit_code_is_recognised() -> None:
    assert is_exit_code_only("exit code: 1")
    assert is_exit_code_only("Process finished with exit code -1073741819")
    assert classify("exit status 1") == "exit_code"


def test_a_log_that_mentions_an_exit_code_is_not_just_an_exit_code() -> None:
    log = "\n".join(["[12:00:00] [Server thread/INFO]: start"] * 5 +
                    ["exit code: 1"])
    assert not is_exit_code_only(log)
    assert classify(log) == "report"


def test_a_crash_report_is_still_a_report() -> None:
    assert classify(REPORT) == "report"


def test_the_cli_refuses_an_hs_err_file(tmp_path, capsys) -> None:
    p = tmp_path / "hs_err_pid1234.log"
    p.write_text(HS, encoding="utf-8")
    assert main([str(p), "--text"]) == 2
    err = capsys.readouterr().err
    assert "hs_err" in err and "Problematic frame" in err


def test_the_cli_refuses_a_bare_exit_code(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("exit code: 1\n"))
    assert main(["--stdin", "--text"]) == 2
    assert "latest.log" in capsys.readouterr().err
