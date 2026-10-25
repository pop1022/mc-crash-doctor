"""Mod manifest reader contract (ROADMAP 1D.1).

The point of 1D.1 is to turn "the author declared these two mods cannot live
together" from a hope into a parsed fact. So these tests are written as
*parse-level* assertions on all four loader formats, not as smoke tests -- the
value is entirely in the edge cases (mandatory vs optional, conflicts vs
breaks, multi-mod jars, hostile filenames).

Fixtures are generated as real zip archives in `tmp_path` rather than checked
in as binaries: a `.jar` in a repo is opaque, unreviewable, and would be the
only binary in a text-only codebase. The manifest TEXTS below are transcribed
from the documented formats of each loader, which is what we actually parse.

Known gap, stated here rather than hidden: these are transcribed fixtures, not
20 jars pulled from live modpacks. Downloading third-party binaries is out of
scope for an automated suite, so validation against a real `mods/` folder is
deferred until someone points the tool at one. What that gap can hide is
malformed-but-loadable manifests in the wild; what it cannot hide is a
misunderstanding of the declared format, because each format is pinned below.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mcd.metadata.manifest import (
    FABRIC_MANIFEST,
    FORGE_MANIFEST,
    NEOFORGE_MANIFEST,
    QUILT_MANIFEST,
    ManifestError,
    TomlSubsetError,
    parse_fabric_json,
    parse_jar,
    parse_mods_toml,
    parse_quilt_json,
    parse_toml_subset,
)

# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
FABRIC_JSON = json.dumps(
    {
        "schemaVersion": 1,
        "id": "examplemod",
        "version": "1.2.3",
        "name": "Example Mod",
        "environment": "*",
        "depends": {
            "fabricloader": ">=0.15.0",
            "fabric-api": "*",
            "minecraft": "~1.20.1",
        },
        "recommends": {"modmenu": "*"},
        "suggests": {"jei": "*"},
        "conflicts": {"optifine": "*"},
        "breaks": {"oldlib": "<2.0"},
        "provides": ["example-api"],
    }
)

QUILT_JSON = json.dumps(
    {
        "schema_version": 1,
        "quilt_loader": {
            "group": "com.example",
            "id": "qmod",
            "version": "0.1.0",
            "metadata": {"name": "Quilt Mod"},
            "provides": [{"id": "qapi"}],
            "depends": [
                {"id": "quilt_loader", "versions": ">=0.19"},
                {"id": "minecraft", "versions": "1.20.x"},
            ],
        },
    }
)

FORGE_TOML = """
modLoader="javafml"
loaderVersion="[47,)"
license="MIT"

[[mods]]
modId="examplemod"
version="1.0.0"
displayName="Example Mod"

[[dependencies.examplemod]]
    modId="forge"
    mandatory=true
    versionRange="[47,)"
    ordering="NONE"
    side="BOTH"

[[dependencies.examplemod]]
    modId="jei"
    mandatory=false
    versionRange="[15,)"
    ordering="AFTER"
    side="CLIENT"
"""

NEOFORGE_TOML = """
modLoader="javafml"
loaderVersion="[21.1,)"
license="MIT"

[[mods]]
modId="neomod"
version="2.0.0"
displayName="Neo Mod"

[[dependencies.neomod]]
modId="neoforge"
type="required"
versionRange="[21.1,)"
ordering="NONE"
side="BOTH"

[[dependencies.neomod]]
modId="oldlib"
type="incompatible"
versionRange="[1.0,2.0)"
ordering="NONE"
side="BOTH"

[[dependencies.neomod]]
modId="createlib"
type="discouraged"
versionRange="*"
ordering="NONE"
side="BOTH"
"""

MULTI_MOD_TOML = """
modLoader="javafml"
loaderVersion="[47,)"

[[mods]]
modId="alpha"
version="1.0"

[[mods]]
modId="beta"
version="2.0"

[[dependencies.alpha]]
    modId="beta"
    mandatory=true
    versionRange="[2.0,)"
"""


def make_jar(path: Path, members: dict[str, str]) -> Path:
    """Write a real zip archive with the given text members."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return path


# --------------------------------------------------------------------------
# Fabric
# --------------------------------------------------------------------------
def test_fabric_core_fields():
    (mod,) = parse_fabric_json(FABRIC_JSON)
    assert mod.modid == "examplemod"
    assert mod.name == "Example Mod"
    assert mod.version == "1.2.3"
    assert mod.loader == "fabric"
    assert mod.source == FABRIC_MANIFEST
    assert mod.provides == ("example-api",)


def test_fabric_dependency_kinds():
    (mod,) = parse_fabric_json(FABRIC_JSON)
    kinds = {d.modid: d.kind for d in mod.depends}
    assert kinds["fabricloader"] == "required"
    assert kinds["modmenu"] == "optional"
    assert kinds["jei"] == "optional"
    assert kinds["optifine"] == "incompatible"
    assert kinds["oldlib"] == "incompatible"


def test_fabric_conflicts_is_soft_and_breaks_is_hard():
    """`conflicts` warns; `breaks` refuses. Collapsing them would be a bug."""
    (mod,) = parse_fabric_json(FABRIC_JSON)
    hard = {d.modid: d.hard for d in mod.negatives}
    assert hard["optifine"] is False
    assert hard["oldlib"] is True


def test_fabric_version_ranges_are_preserved_verbatim():
    (mod,) = parse_fabric_json(FABRIC_JSON)
    ranges = {d.modid: d.version_range for d in mod.depends}
    assert ranges["fabricloader"] == ">=0.15.0"
    assert ranges["minecraft"] == "~1.20.1"


def test_fabric_requirements_exclude_optional():
    (mod,) = parse_fabric_json(FABRIC_JSON)
    assert {d.modid for d in mod.hard_requirements} == {
        "fabricloader",
        "fabric-api",
        "minecraft",
    }
    assert mod.negatives and all(d.kind == "incompatible" for d in mod.negatives)


def test_fabric_depends_as_list_is_tolerated():
    """Loose manifests in the wild use a list; refusing it would lose data."""
    text = json.dumps({"id": "loose", "version": "1", "depends": ["fabric-api"]})
    (mod,) = parse_fabric_json(text)
    assert [d.modid for d in mod.depends] == ["fabric-api"]
    assert mod.depends[0].kind == "required"


def test_fabric_bad_json_raises_with_context():
    with pytest.raises(ManifestError) as exc:
        parse_fabric_json("{not json")
    assert "fabric.mod.json" in str(exc.value)


def test_fabric_without_id_yields_nothing():
    assert parse_fabric_json(json.dumps({"version": "1"})) == []


# --------------------------------------------------------------------------
# Quilt
# --------------------------------------------------------------------------
def test_quilt_reads_quilt_loader_section():
    (mod,) = parse_quilt_json(QUILT_JSON)
    assert mod.modid == "qmod"
    assert mod.name == "Quilt Mod"
    assert mod.loader == "quilt"
    assert mod.provides == ("qapi",)
    ranges = {d.modid: d.version_range for d in mod.depends}
    assert ranges["quilt_loader"] == ">=0.19"


def test_quilt_without_loader_section_yields_nothing():
    assert parse_quilt_json(json.dumps({"schema_version": 1})) == []


# --------------------------------------------------------------------------
# Forge / NeoForge
# --------------------------------------------------------------------------
def test_forge_mandatory_true_is_required_and_false_is_optional():
    (mod,) = parse_mods_toml(FORGE_TOML, loader="forge", source=FORGE_MANIFEST)
    assert mod.modid == "examplemod"
    assert mod.version == "1.0.0"
    assert mod.loader == "forge"
    by_id = {d.modid: d for d in mod.depends}
    assert by_id["forge"].kind == "required"
    assert by_id["jei"].kind == "optional"
    assert by_id["jei"].version_range == "[15,)"
    assert by_id["jei"].side == "CLIENT"
    assert by_id["jei"].ordering == "AFTER"


def test_neoforge_type_incompatible_is_a_hard_negative_edge():
    (mod,) = parse_mods_toml(
        NEOFORGE_TOML, loader="neoforge", source=NEOFORGE_MANIFEST
    )
    assert mod.loader == "neoforge"
    by_id = {d.modid: d for d in mod.depends}
    assert by_id["neoforge"].kind == "required"
    assert by_id["oldlib"].kind == "incompatible"
    assert by_id["oldlib"].hard is True
    assert by_id["oldlib"].version_range == "[1.0,2.0)"
    # discouraged is negative but not fatal: refusing to launch would be wrong
    assert by_id["createlib"].kind == "incompatible"
    assert by_id["createlib"].hard is False


def test_forge_multiple_mods_in_one_jar():
    mods = parse_mods_toml(MULTI_MOD_TOML, loader="forge", source=FORGE_MANIFEST)
    assert [m.modid for m in mods] == ["alpha", "beta"]
    alpha = mods[0]
    assert [d.modid for d in alpha.depends] == ["beta"]
    assert mods[1].depends == ()


def test_mods_toml_without_mods_table_yields_nothing():
    assert parse_mods_toml('modLoader="javafml"\n', source=FORGE_MANIFEST) == []


def test_comment_inside_string_is_not_a_comment():
    """`#` inside a quoted value must survive -- a naive strip would truncate."""
    text = 'license="MIT # not a comment"\n\n[[mods]]\nmodId="x"\nversion="1"\n'
    parsed = parse_toml_subset(text)
    assert parsed["license"] == "MIT # not a comment"


def test_multiline_array_in_toml_subset():
    """Middle lines of a multi-line array carry no brackets; they must not flush."""
    text = 'a = [\n  "one",\n  "two",\n]\n'
    assert parse_toml_subset(text) == {"a": ["one", "two"]}


def test_unsupported_toml_raises_instead_of_guessing():
    with pytest.raises(TomlSubsetError):
        parse_toml_subset("when = 2026-10-21\n")


# --------------------------------------------------------------------------
# TOML subset vs tomllib
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text", [FORGE_TOML, NEOFORGE_TOML, MULTI_MOD_TOML]
)
def test_subset_parser_agrees_with_tomllib(text):
    """The fallback exists for Python 3.9/3.10; its correctness is asserted
    against the real parser here rather than assumed."""
    tomllib = pytest.importorskip("tomllib")
    assert parse_toml_subset(text) == tomllib.loads(text)


# --------------------------------------------------------------------------
# jar-level behaviour
# --------------------------------------------------------------------------
def test_parse_jar_reads_fabric_manifest(tmp_path: Path):
    jar = make_jar(tmp_path / "m.jar", {FABRIC_MANIFEST: FABRIC_JSON})
    (mod,) = parse_jar(jar)
    assert mod.modid == "examplemod"


def test_parse_jar_reads_each_loader(tmp_path: Path):
    cases = [
        ({QUILT_MANIFEST: QUILT_JSON}, "qmod"),
        ({FORGE_MANIFEST: FORGE_TOML}, "examplemod"),
        ({NEOFORGE_MANIFEST: NEOFORGE_TOML}, "neomod"),
    ]
    for index, (members, expected) in enumerate(cases):
        jar = make_jar(tmp_path / f"c{index}.jar", members)
        mods = parse_jar(jar)
        assert [m.modid for m in mods] == [expected], members.keys()


def test_parse_jar_prefers_fabric_over_forge(tmp_path: Path):
    """A jar carrying both is a Fabric mod with a Forge shim; Fabric wins."""
    jar = make_jar(
        tmp_path / "both.jar",
        {FABRIC_MANIFEST: FABRIC_JSON, FORGE_MANIFEST: FORGE_TOML},
    )
    (mod,) = parse_jar(jar)
    assert mod.loader == "fabric"


def test_parse_jar_without_manifest_returns_empty(tmp_path: Path):
    """Libraries and resource packs sit in mods/ too; that is not an error."""
    jar = make_jar(tmp_path / "lib.jar", {"some/Class.class": "x"})
    assert parse_jar(jar) == []


def test_parse_jar_rejects_non_zip(tmp_path: Path):
    bad = tmp_path / "broken.jar"
    bad.write_text("this is not a jar", encoding="utf-8")
    with pytest.raises(ManifestError) as exc:
        parse_jar(bad)
    assert "broken.jar" in str(exc.value)


def test_parse_jar_rejects_missing_file(tmp_path: Path):
    with pytest.raises(ManifestError):
        parse_jar(tmp_path / "absent.jar")


def test_parse_jar_decodes_utf8_bom(tmp_path: Path):
    jar = make_jar(tmp_path / "bom.jar", {FABRIC_MANIFEST: "\ufeff" + FABRIC_JSON})
    (mod,) = parse_jar(jar)
    assert mod.modid == "examplemod"


# --------------------------------------------------------------------------
# regression guard: the gap RESEARCH J1 depends on
# --------------------------------------------------------------------------
def test_negatives_exist_at_all():
    """If this ever returns empty for a manifest that declares `breaks`,
    the whole 'declared edges beat co-occurrence' argument silently dies."""
    (mod,) = parse_fabric_json(FABRIC_JSON)
    assert mod.negatives, "fabric.mod.json `breaks`/`conflicts` not surfaced"
    (neo,) = parse_mods_toml(
        NEOFORGE_TOML, loader="neoforge", source=NEOFORGE_MANIFEST
    )
    assert [d.modid for d in neo.negatives] == ["oldlib", "createlib"]
