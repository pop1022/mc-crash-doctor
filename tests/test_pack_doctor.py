"""Pack Doctor: what a `mods/` directory says about itself.

Every fixture here is a real zip built in `tmp_path`, because the whole point
of this check is that it reads jars -- a mocked `parse_jar` would test the mock.

The tests are grouped by the four buckets the report separates, and the
distinction is the feature:

    findings    a declared contradiction
    undecided   the range was read but not understood
    unreadable  a jar with no manifest we can read
    (silence)   nothing declared

A checker that merged `undecided` into "ok" would look better and be wrong, so
`test_unparseable_range_becomes_undecided_not_ok` is the load-bearing one.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mcd.cli import main
from mcd.pack.doctor import BUILTIN_IDS, analyse


# --- fixture builders -------------------------------------------------------
def jar(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return path


def fabric(modid: str, version: str | None = "1.0.0", *, depends=None,
           breaks=None, conflicts=None, provides=None) -> str:
    body = {"schemaVersion": 1, "id": modid,
            "version": version if version is not None else "${file.jarVersion}",
            "depends": depends or {}}
    if breaks:
        body["breaks"] = breaks
    if conflicts:
        body["conflicts"] = conflicts
    if provides:
        body["provides"] = provides
    return json.dumps(body)


def forge_toml(modid: str, version: str, deps: list[tuple[str, str]] = ()) -> str:
    lines = ['modLoader="javafml"', 'loaderVersion="[47,)"', 'license="MIT"',
             "", "[[mods]]", f'modId="{modid}"', f'version="{version}"',
             f'displayName="{modid}"']
    for dep_id, rng in deps:
        lines += ["", f"[[dependencies.{modid}]]", f'    modId="{dep_id}"',
                  "    mandatory=true", f'    versionRange="{rng}"',
                  '    ordering="NONE"', '    side="BOTH"']
    return "\n".join(lines) + "\n"


def pack(tmp_path: Path, jars: dict[str, dict[str, str]]) -> Path:
    mods = tmp_path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name, entries in jars.items():
        jar(mods / name, entries)
    return tmp_path


def kinds(rep) -> set[str]:
    return {f.kind for f in rep.findings}


# --- findings ---------------------------------------------------------------
def test_missing_dependency_names_the_requiring_mod_and_its_range(tmp_path):
    root = pack(tmp_path, {
        "create.jar": {"fabric.mod.json": fabric(
            "create", "0.5.1", depends={"flywheel": "[1.20,)"})},
    })
    rep = analyse(root)
    missing = rep.by_kind("pack.missing-dependency")
    assert [f.subject for f in missing] == ["flywheel"]
    assert "create" in missing[0].detail and "[1.20,)" in missing[0].detail
    assert missing[0].evidence == ["create.jar"]


def test_version_mismatch_uses_range_semantics(tmp_path):
    """sodium 0.5.8 installed, another mod needs >=0.6 -- a real mismatch."""
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "extra.jar": {"fabric.mod.json": fabric(
            "extra", "1.0", depends={"sodium": "[0.6,)"})},
    })
    rep = analyse(root)
    mm = rep.by_kind("pack.version-mismatch")
    assert len(mm) == 1
    assert mm[0].subject == "sodium"
    assert "0.5.8" in mm[0].detail and "[0.6,)" in mm[0].detail


def test_a_satisfied_range_produces_no_finding(tmp_path):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "create.jar": {"fabric.mod.json": fabric(
            "create", "1.0", depends={"sodium": "[0.5.0,0.6)"})},
    })
    assert analyse(root).findings == []


def test_duplicate_mod_across_two_jars(tmp_path):
    root = pack(tmp_path, {
        "sodium-a.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "sodium-b.jar": {"fabric.mod.json": fabric("sodium", "0.4.0")},
    })
    dup = analyse(root).by_kind("pack.duplicate-mod")
    assert len(dup) == 1
    assert "0.4.0" in dup[0].detail and "0.5.8" in dup[0].detail
    assert sorted(dup[0].evidence) == ["sodium-a.jar", "sodium-b.jar"]


def test_mixed_loaders_is_an_error(tmp_path):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "jei.jar": {"META-INF/mods.toml": forge_toml("jei", "15.2.0")},
    })
    rep = analyse(root)
    mixed = rep.by_kind("pack.mixed-loaders")
    assert len(mixed) == 1
    assert rep.worst.name == "ERROR"
    assert set(rep.loaders) == {"fabric", "forge"}


def test_declared_negative_edge_is_reported_only_when_both_are_installed(tmp_path):
    root = pack(tmp_path, {
        "a.jar": {"fabric.mod.json": fabric("moda", "1.0",
                                            breaks={"modb": "*"})},
        "b.jar": {"fabric.mod.json": fabric("modb", "2.0")},
    })
    rep = analyse(root)
    conflict = rep.by_kind("pack.declared-conflict")
    assert len(conflict) == 1
    assert conflict[0].subject == "moda x modb"
    assert conflict[0].severity.name == "ERROR"          # `breaks` is fatal

    # ... and absent when the other side is not installed
    alone = pack(tmp_path / "alone", {
        "a.jar": {"fabric.mod.json": fabric("moda", "1.0",
                                            breaks={"modb": "*"})},
    })
    assert analyse(alone).by_kind("pack.declared-conflict") == []


# --- the invariant: unknown is printed, never swallowed ---------------------
def test_unparseable_range_becomes_undecided_not_ok(tmp_path):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "weird.jar": {"fabric.mod.json": fabric(
            "weird", "1.0", depends={"sodium": "banana-runtime"})},
    })
    rep = analyse(root)
    assert rep.findings == [], "an unreadable range must not become a finding"
    assert len(rep.undecided) == 1
    u = rep.undecided[0]
    assert u["modid"] == "sodium" and u["range"] == "banana-runtime"
    assert u["installed"] == "0.5.8"
    assert "undecided" in rep.summary_line()


def test_jar_without_a_known_manifest_is_listed_not_skipped(tmp_path):
    root = pack(tmp_path, {
        "guava-32.1.2-jre.jar": {"META-INF/MANIFEST.MF": "Manifest-Version: 1.0\n"},
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
    })
    rep = analyse(root)
    assert [u["jar"] for u in rep.unreadable] == ["guava-32.1.2-jre.jar"]
    assert "no fabric.mod.json" in rep.unreadable[0]["reason"]
    assert rep.jars == 2 and rep.declared_mods == 1


def test_a_corrupt_jar_is_listed_with_its_reason(tmp_path):
    root = pack(tmp_path, {"sodium.jar": {"fabric.mod.json": fabric("sodium")}})
    (root / "mods" / "broken.jar").write_bytes(b"not a zip at all")
    rep = analyse(root)
    broken = [u for u in rep.unreadable if u["jar"] == "broken.jar"]
    assert broken and "not a readable jar" in broken[0]["reason"]


# --- things that must NOT be reported --------------------------------------
def test_platform_ids_are_not_missing_dependencies(tmp_path):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric(
            "sodium", "0.5.8",
            depends={"minecraft": ">=1.20.1", "fabricloader": ">=0.15",
                     "java": ">=17"})},
    })
    rep = analyse(root)
    assert rep.findings == []
    assert {"minecraft", "java", "fabricloader"} <= BUILTIN_IDS


def test_a_provided_id_satisfies_the_dependency(tmp_path):
    """Flywheel is commonly satisfied by a jar that declares `provides`."""
    root = pack(tmp_path, {
        "provider.jar": {"fabric.mod.json": fabric(
            "create-core", "1.0", provides=["flywheel"])},
        "create.jar": {"fabric.mod.json": fabric(
            "create", "1.0", depends={"flywheel": "[0.6,)"})},
    })
    rep = analyse(root)
    assert rep.by_kind("pack.missing-dependency") == []


# --- context and CLI --------------------------------------------------------
def test_pack_manifest_is_read_as_context_only(tmp_path):
    root = pack(tmp_path, {"a.jar": {"fabric.mod.json": fabric("moda")}})
    (root / "manifest.json").write_text(json.dumps({
        "minecraft": {"version": "1.20.1",
                      "modLoaders": [{"id": "fabric-0.15.11", "primary": True}]},
        "files": [{"projectID": 1}]}), encoding="utf-8")
    rep = analyse(root)
    assert rep.context["mc_version"] == "1.20.1"
    assert rep.context["loader"] == "fabric-0.15.11"
    assert rep.context["declared_files"] == 1


def test_no_mods_dir_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="no `mods/` directory"):
        analyse(tmp_path)


def test_cli_pack_json_and_exit_code(tmp_path, capsys):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8")},
        "create.jar": {"fabric.mod.json": fabric(
            "create", "1.0", depends={"flywheel": "[1.20,)"})},
    })
    assert main(["--pack", str(root), "--json"]) == 0        # no --exit-code
    data = json.loads(capsys.readouterr().out)
    assert data["jars"] == 2
    assert data["findings"][0]["kind"] == "pack.missing-dependency"
    assert data["not_checked"], "limitations must travel with the JSON"

    assert main(["--pack", str(root), "--json", "--exit-code"]) == 1


def test_cli_pack_missing_dir_returns_2(tmp_path, capsys):
    assert main(["--pack", str(tmp_path / "nope")]) == 2
    assert "no `mods/` directory" in capsys.readouterr().err
