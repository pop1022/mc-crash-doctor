"""Pack Doctor and Server Doctor on directories that are not what was promised.

The failure that matters is not a crash -- it is a checker that answers "no
findings" after reading nothing. Each test here pins a message that tells the
difference, and the exit code that goes with it.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from mcd.cli import main
from mcd.pack.doctor import analyse


def test_a_missing_directory_says_so(tmp_path: Path) -> None:
    try:
        analyse(tmp_path / "nope")
    except FileNotFoundError as e:
        assert "does not exist" in str(e)
    else:                                              # pragma: no cover
        raise AssertionError("expected FileNotFoundError")


def test_a_file_says_it_is_a_file(tmp_path: Path) -> None:
    p = tmp_path / "mods.txt"
    p.write_text("x", encoding="utf-8")
    try:
        analyse(p)
    except FileNotFoundError as e:
        assert "is a file, not a directory" in str(e)
    else:                                              # pragma: no cover
        raise AssertionError("expected FileNotFoundError")


def test_an_empty_mods_folder_says_it_holds_no_jars(tmp_path: Path) -> None:
    (tmp_path / "mods").mkdir()
    try:
        analyse(tmp_path)
    except FileNotFoundError as e:
        assert "holds no .jar files" in str(e)
    else:                                              # pragma: no cover
        raise AssertionError("expected FileNotFoundError")


def test_a_pack_of_unreadable_jars_is_not_success(tmp_path: Path, capsys) -> None:
    (tmp_path / "mods").mkdir()
    (tmp_path / "mods" / "broken.jar").write_bytes(b"not a zip")
    assert main(["--pack", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "nothing to compare" in out
    # The reason used to repeat the jar name: "broken.jar: broken.jar: ...".
    assert out.count("broken.jar:") == 1


def test_a_jar_with_no_manifest_also_counts_as_nothing_checked(tmp_path: Path,
                                                              capsys) -> None:
    (tmp_path / "mods").mkdir()
    with zipfile.ZipFile(tmp_path / "mods" / "library.jar", "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    assert main(["--pack", str(tmp_path)]) == 2
    assert "nothing to compare" in capsys.readouterr().out


def test_server_on_an_empty_folder_reports_what_is_missing(tmp_path: Path,
                                                           capsys) -> None:
    assert main(["--server", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "no crash report" in out.lower()
    assert "logs/latest.log -- not found" in out
    assert "mods/ -- not found" in out


def test_server_on_a_missing_folder_is_an_error(tmp_path: Path, capsys) -> None:
    assert main(["--server", str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_server_with_only_a_log_says_the_pack_was_not_checked(tmp_path: Path,
                                                              capsys) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "latest.log").write_text(
        "[12:00:00] [Server thread/INFO]: Done (3.2s)!\n", encoding="utf-8")
    assert main(["--server", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "mods/ -- not found" in out
    assert "read-only snapshot" in out
