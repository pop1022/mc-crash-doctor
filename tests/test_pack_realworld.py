"""Pack Doctor against the shapes real jars actually have.

Every fixture here is a synthetic zip, but each one replicates a shape taken
from a real 355-jar NeoForge pack (2026-10-27) that the earlier fixtures never
covered. On that pack the old reader reported **35 findings**; the pack boots
("Done (4.723s)!" in its own latest.log), and 34 of them were wrong. Each test
below is one of those 34:

  34 -> 1    after: bundled jars satisfy dependencies, `file.jarVersion`
             resolves from MANIFEST.MF, an incompatible edge is only a finding
             when its range covers the installed build, and a side-scoped
             requirement is not "missing" on a pack whose side is unknown.

The point is not the count -- it is that every one of these shapes exists in the
wild and none of them appeared in the hand-written fixtures.

    pytest tests/test_pack_realworld.py -v
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from mcd.metadata.manifest import parse_jar
from mcd.pack.doctor import NOT_CHECKED, analyse


# --- builders ---------------------------------------------------------------
def _zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return buf.getvalue()


def jar(path: Path, entries: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return path


def fabric(modid: str, version: str = "1.0.0", *, depends=None,
           environment=None) -> str:
    body = {"schemaVersion": 1, "id": modid, "version": version,
            "depends": depends or {}}
    if environment:
        body["environment"] = environment
    return json.dumps(body)


def toml(modid: str, version: str, deps=()) -> str:
    """`deps` = [(dep_id, range, type, side)] -- type is required|incompatible."""
    lines = ['modLoader="javafml"', 'loaderVersion="[1,)"', 'license="MIT"',
             "", "[[mods]]", f'modId="{modid}"', f'version="{version}"',
             f'displayName="{modid}"']
    for dep_id, rng, kind, side in deps:
        lines += ["", f"[[dependencies.{modid}]]", f'    modId="{dep_id}"',
                  f'    type="{kind}"', f'    versionRange="{rng}"',
                  f'    side="{side}"']
    return "\n".join(lines) + "\n"


def pack(tmp_path: Path, jars: dict[str, dict]) -> Path:
    mods = tmp_path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name, entries in jars.items():
        jar(mods / name, entries)
    return tmp_path


def kinds(rep) -> set[str]:
    return {f.kind for f in rep.findings}


# --- 1. a bundled jar satisfies a dependency --------------------------------
def test_bundled_jar_satisfies_a_dependency(tmp_path):
    """JarJar/Fabric put mods under META-INF/jarjar|jars. A real pack declares
    `ae2wtlib_api` as REQUIRED by four mods and provides it inside
    `ae2wtlib-19.5.1.jar` -- its log says `locator: jarinjar`. Not looking
    inside produced four "no jar in mods/ declares it" findings on a pack that
    boots."""
    inner = _zip_bytes({"fabric.mod.json": fabric("wrapper_api", "1.2.0")})
    root = pack(tmp_path, {
        "wrapper.jar": {
            "fabric.mod.json": fabric("wrapper", "1.0.0"),
            "META-INF/jars/api-1.2.0.jar": inner,
        },
        "consumer.jar": {"fabric.mod.json": fabric(
            "consumer", "1.0.0", depends={"wrapper_api": "[1.0,)"})},
    })
    rep = analyse(root)
    assert "pack.missing-dependency" not in kinds(rep), rep.findings


def test_a_jar_with_only_a_bundled_mod_is_not_unreadable(tmp_path):
    """`kotlinforforge-5.12.0-all.jar` has no top-level manifest at all: its mod
    metadata is inside the bundle. Reporting it as unreadable was wrong."""
    inner = _zip_bytes({"fabric.mod.json": fabric("kotlinforforge", "5.12.0")})
    root = pack(tmp_path, {
        "kotlin-all.jar": {"META-INF/jars/kotlin.jar": inner},
        "other.jar": {"fabric.mod.json": fabric("other", "1.0")},
    })
    rep = analyse(root)
    assert rep.unreadable == [], rep.unreadable


# --- 2. ${file.jarVersion} ---------------------------------------------------
def test_file_jar_version_resolves_from_manifest(tmp_path):
    """Forge substitutes this placeholder from the jar's own MANIFEST.MF. Left
    literal, no range can be compared against it: 25 of 25 jars in the real pack
    used it, and it was the single biggest source of `undecided`."""
    root = pack(tmp_path, {
        "provider.jar": {
            "META-INF/mods.toml": toml("provider", "${file.jarVersion}"),
            "META-INF/MANIFEST.MF":
                "Manifest-Version: 1.0\r\nImplementation-Version: 1.4.2\r\n\r\n",
        },
        "consumer.jar": {"META-INF/mods.toml": toml(
            "consumer", "1.0", [("provider", "[1.0,2.0)", "required", "BOTH")])},
    })
    rep = analyse(root)
    assert rep.findings == [], rep.findings
    assert rep.undecided == [], rep.undecided


def test_placeholder_without_a_manifest_stays_undecided(tmp_path):
    """No Implementation-Version means no answer -- not a guess, and not a
    version-mismatch either."""
    root = pack(tmp_path, {
        "provider.jar": {"META-INF/mods.toml": toml("provider", "${file.jarVersion}")},
        "consumer.jar": {"META-INF/mods.toml": toml(
            "consumer", "1.0", [("provider", "[1.0,2.0)", "required", "BOTH")])},
    })
    rep = analyse(root)
    assert "pack.version-mismatch" not in kinds(rep)
    assert len(rep.undecided) == 1


def test_parse_jar_reports_the_substituted_version(tmp_path):
    p = jar(tmp_path / "x.jar", {
        "META-INF/mods.toml": toml("x", "${file.jarVersion}"),
        "META-INF/MANIFEST.MF": "Implementation-Version: 9.9.9\n\n"})
    assert [m.version for m in parse_jar(p)] == ["9.9.9"]


# --- 3. an incompatible edge is version-scoped -----------------------------
def test_incompatible_edge_outside_its_range_is_not_a_finding(tmp_path):
    """`ae2wtlib` declares extendedae incompatible with `(,1.21-1.1.4-neoforge]`
    -- only the old builds. The pack ships 1.21-2.2.35, and the loader starts
    it. Treating the edge as unconditional produced 9 false conflicts."""
    root = pack(tmp_path, {
        "a.jar": {"META-INF/mods.toml": toml(
            "a", "1.0", [("b", "(,1.0.4]", "incompatible", "BOTH")])},
        "b.jar": {"META-INF/mods.toml": toml("b", "2.0")},
    })
    rep = analyse(root)
    assert "pack.declared-conflict" not in kinds(rep), rep.findings


def test_incompatible_edge_inside_its_range_is_still_a_finding(tmp_path):
    """The reverse control: the check must not have been switched off."""
    root = pack(tmp_path, {
        "a.jar": {"META-INF/mods.toml": toml(
            "a", "1.0", [("b", "(,1.0.4]", "incompatible", "BOTH")])},
        "b.jar": {"META-INF/mods.toml": toml("b", "1.0.2")},
    })
    find = analyse(root).by_kind("pack.declared-conflict")
    assert len(find) == 1
    assert "covers (,1.0.4]" in find[0].detail


def test_unreadable_incompatible_range_becomes_undecided(tmp_path):
    """A range we cannot parse must not become "they conflict"."""
    root = pack(tmp_path, {
        "a.jar": {"META-INF/mods.toml": toml(
            "a", "1.0", [("b", "banana", "incompatible", "BOTH")])},
        "b.jar": {"META-INF/mods.toml": toml("b", "1.0")},
    })
    rep = analyse(root)
    assert "pack.declared-conflict" not in kinds(rep)
    assert len(rep.undecided) == 1


# --- 4. side-scoped requirements -------------------------------------------
def test_side_scoped_requirement_is_not_reported_missing(tmp_path):
    """connectedglass requires fusion `side="CLIENT"`; fancymenu requires melody
    the same way. On a server pack neither is needed, and `--pack DIR` cannot
    tell which side it is looking at. NOT_CHECKED says so instead."""
    root = pack(tmp_path, {
        "clientmod.jar": {"META-INF/mods.toml": toml(
            "clientmod", "1.0", [("fusion", "[1.2.9,)", "required", "CLIENT")])},
    })
    rep = analyse(root)
    assert "pack.missing-dependency" not in kinds(rep), rep.findings
    assert any("side=CLIENT" in line for line in NOT_CHECKED)


def test_both_side_requirement_is_still_reported(tmp_path):
    """Reverse control for the one above."""
    root = pack(tmp_path, {
        "mod.jar": {"META-INF/mods.toml": toml(
            "mod", "1.0", [("fusion", "[1.2.9,)", "required", "BOTH")])},
    })
    find = analyse(root).by_kind("pack.missing-dependency")
    assert len(find) == 1 and find[0].subject == "fusion"


# --- 6. `--side`: what the directory cannot say ----------------------------
def test_client_only_mod_on_a_server_is_reported(tmp_path):
    """Fabric/Quilt declare this per mod; a server pack that has one is
    carrying dead weight. Only checkable when the caller says which side the
    directory is for."""
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8",
                                                 environment="client")},
    })
    find = analyse(root, side="server").by_kind("pack.wrong-side-mod")
    assert len(find) == 1
    assert find[0].subject == "sodium"
    assert find[0].severity.name == "WARNING"
    assert "environment=client" in find[0].detail


def test_server_only_mod_on_a_client_is_reported(tmp_path):
    """The reverse direction, so the check is not one-way."""
    root = pack(tmp_path, {
        "chunky.jar": {"fabric.mod.json": fabric("chunky", "1.3",
                                                 environment="server")},
    })
    find = analyse(root, side="client").by_kind("pack.wrong-side-mod")
    assert len(find) == 1 and find[0].subject == "chunky"


def test_environment_star_or_missing_is_never_a_wrong_side_finding(tmp_path):
    """Reverse control. `*` means both sides; absent means the manifest does not
    say -- which is every Forge/NeoForge mod. Neither may become a finding."""
    root = pack(tmp_path, {
        "star.jar": {"fabric.mod.json": fabric("star", "1.0", environment="*")},
        "quiet.jar": {"fabric.mod.json": fabric("quiet", "1.0")},
        "forge.jar": {"META-INF/mods.toml": toml("forgey", "1.0")},
    })
    for side in ("server", "client"):
        rep = analyse(root, side=side)
        assert "pack.wrong-side-mod" not in kinds(rep), (side, rep.findings)


def test_without_side_nothing_is_claimed_about_it(tmp_path):
    root = pack(tmp_path, {
        "sodium.jar": {"fabric.mod.json": fabric("sodium", "0.5.8",
                                                 environment="client")},
    })
    rep = analyse(root)
    assert "pack.wrong-side-mod" not in kinds(rep)
    assert any("environment" in line for line in rep.not_checked())


def test_side_scoped_requirement_follows_the_side(tmp_path):
    """`connectedglass` requires `fusion` with side="CLIENT". On a server that
    requirement does not apply; on a client it does, and `fusion` really is
    absent. Same directory, two correct answers."""
    root = pack(tmp_path, {
        "glass.jar": {"META-INF/mods.toml": toml(
            "glass", "1.0", [("fusion", "[1.2.9,)", "required", "CLIENT")])},
    })
    assert "pack.missing-dependency" not in kinds(analyse(root))
    assert "pack.missing-dependency" not in kinds(analyse(root, side="server"))
    client = analyse(root, side="client").by_kind("pack.missing-dependency")
    assert len(client) == 1 and client[0].subject == "fusion"


def test_not_checked_shrinks_by_two_when_the_side_is_known(tmp_path):
    root = pack(tmp_path, {"a.jar": {"fabric.mod.json": fabric("a", "1.0")}})
    unknown = analyse(root).not_checked()
    known = analyse(root, side="server").not_checked()
    assert len(unknown) == 3 and len(known) == 1
    assert all(item in unknown for item in known)


def test_json_carries_the_side(tmp_path):
    root = pack(tmp_path, {"a.jar": {"fabric.mod.json": fabric("a", "1.0")}})
    assert analyse(root, side="server").to_dict()["side"] == "server"
    assert analyse(root).to_dict()["side"] is None
    assert len(analyse(root, side="server").to_dict()["not_checked"]) == 1


def test_cli_rejects_side_without_pack(tmp_path, capsys):
    """`--side` with a crash report would look applied and do nothing."""
    from mcd.cli import main

    report = tmp_path / "r.txt"
    report.write_text("---- Minecraft Crash Report ----\nDescription: x\n",
                      encoding="utf-8")
    assert main([str(report), "--side", "client"]) == 2
    assert "--side only applies to --pack" in capsys.readouterr().err


def test_analyse_rejects_an_unknown_side(tmp_path):
    root = pack(tmp_path, {"a.jar": {"fabric.mod.json": fabric("a", "1.0")}})
    try:
        analyse(root, side="both")
    except ValueError as exc:
        assert "side must be" in str(exc)
    else:                                    # pragma: no cover
        raise AssertionError("an unknown side must not be accepted silently")
