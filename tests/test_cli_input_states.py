"""What the CLI does with input that is not a report.

Diagnosis is forgiving by design, but three states must not pretend to work:
an empty file, a file too large to be a crash report, and prose. The old
behaviour printed a full diagnosis header for an empty file and told a Chinese
sentence that it "matched no rule" -- true, and about the wrong question.
"""
from __future__ import annotations

from pathlib import Path

from mcd.cli import MAX_INPUT_BYTES, _looks_like_report, main

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"
REAL = GT / "crash-2026-09-08_18.01.19-server.txt"


def test_the_heuristic_recognises_the_shapes_that_are_reports() -> None:
    assert _looks_like_report("---- Minecraft Crash Report ----\nboom")
    assert _looks_like_report("Description: Ticking entity\n")
    assert _looks_like_report("\tat a.b.C.d(C.java:1)\n\tat a.b.C.e(C.java:2)")
    assert _looks_like_report("[12:00:00] [Server thread/INFO]: x\n[12:00:01] [Server thread/INFO]: y")
    assert _looks_like_report("Starting minecraft server version 1.20.1")


def test_the_heuristic_rejects_prose() -> None:
    assert not _looks_like_report("我的服务器一直崩，是哪个模组的问题？")
    assert not _looks_like_report("hello world")


def test_an_empty_file_is_an_error_not_an_empty_diagnosis(tmp_path: Path, capsys) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    assert main([str(p), "--text"]) == 2
    err = capsys.readouterr().err
    assert "empty" in err and "nothing to diagnose" in err


def test_an_oversize_file_is_refused_with_the_limit(tmp_path: Path, capsys) -> None:
    p = tmp_path / "huge.log"
    p.write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
    assert main([str(p), "--text"]) == 2
    assert "limit 8 MB" in capsys.readouterr().err


def test_prose_exits_2_and_says_why(tmp_path: Path, capsys) -> None:
    p = tmp_path / "prose.txt"
    p.write_text("我的服务器一直崩，帮我看看到底是哪个模组的问题，谢谢。\n",
                 encoding="utf-8")
    assert main([str(p), "--text"]) == 2
    out = capsys.readouterr().out
    assert "nothing diagnosable" in out


def test_a_report_named_without_txt_is_still_diagnosed(tmp_path: Path, capsys) -> None:
    # The suffix filter used to answer "no crash reports found under x.crash",
    # blaming a directory scan for a file the user had named.
    p = tmp_path / "2026-09-08.crash"
    p.write_text(REAL.read_text(encoding="utf-8"), encoding="utf-8")
    assert main([str(p), "--text"]) == 0
    assert "FINDINGS" in capsys.readouterr().out


def test_a_real_report_still_exits_zero(capsys) -> None:
    assert main([str(REAL), "--text"]) == 0
    assert "oom.heap" in capsys.readouterr().out


def test_a_batch_counts_prose_as_failed(tmp_path: Path, capsys) -> None:
    for i in range(2):
        (tmp_path / f"p{i}.txt").write_text("这不是报告，是描述。\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 2
    assert "0/2 diagnosed" in capsys.readouterr().err

def test_empty_stdin_is_refused(monkeypatch, capsys) -> None:
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["--stdin"]) == 2
    assert "empty" in capsys.readouterr().err
