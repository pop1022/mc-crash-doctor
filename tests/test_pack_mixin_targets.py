"""Pack Doctor reads mixin targets from refmaps, and reports overlap as a lead.

The distinction under test: overlap is NOT a finding. A pack where two mods
mix into the same class is ordinary; what this check buys is the ability to
answer "which jars touch this target" when a crash names a mixin. The tests
also pin the coverage numbers, because "no overlaps" and "no jar shipped a
refmap" are different answers and must not look the same.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mcd.pack.doctor import analyse
from mcd.pack.mixins import mixin_references


def jar(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return path


FORGE_REFMAP = {
    "mappings": {
        "pkg/mixin/FooMixin": {
            "target": "net/minecraft/client/Minecraft",
            "method": {"onTick": "m_12345_"},
        }
    }
}

FABRIC_REFMAP = {
    "mappings": {},
    "data": {
        "named:intermediary": {
            "pkg/mixin/BarMixin": {
                "target": "net/minecraft/class_310",
                "method": {"onTick": "method_1"},
            }
        }
    },
}


def fabric(modid: str, *, config: str | None = None,
           refmap: str | None = "", body: dict | None = None) -> dict[str, str]:
    # Per-mod names by default: two jars sharing a config file name would fire
    # the separate pack.mixin-config-collision finding and muddy these tests.
    config = config or f"{modid}.mixins.json"
    refmap = f"{modid}-refmap.json" if refmap == "" else refmap
    manifest = {"schemaVersion": 1, "id": modid, "version": "1.0.0",
                "depends": {}, "mixins": [config]}
    entries = {"fabric.mod.json": json.dumps(manifest)}
    cfg = {"required": True, "package": modid, "mixins": [], "client": []}
    if refmap:
        cfg["refmap"] = refmap
    entries[config] = json.dumps(cfg)
    if refmap and body is not None:
        entries[refmap] = json.dumps(body)
    entries["pkg/x.txt"] = "x"
    return entries


def pack(tmp_path: Path, jars: dict[str, dict[str, str]]) -> Path:
    mods = tmp_path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name, entries in jars.items():
        jar(mods / name, entries)
    return tmp_path


# --- the reader -------------------------------------------------------------
def test_forge_shaped_refmap(tmp_path: Path) -> None:
    path = jar(tmp_path / "a.jar", {"mod.refmap.json": json.dumps(FORGE_REFMAP)})
    refs = mixin_references(path)
    assert refs.targets == {"net/minecraft/client/Minecraft": {"FooMixin"}}
    assert refs.methods == {("net/minecraft/client/Minecraft", "m_12345_"): {"FooMixin"}}
    assert refs.refmaps == ["mod.refmap.json"]


def test_fabric_shaped_refmap_uses_data_namespace(tmp_path: Path) -> None:
    path = jar(tmp_path / "b.jar", {"mod-refmap.json": json.dumps(FABRIC_REFMAP)})
    refs = mixin_references(path)
    assert "net/minecraft/class_310" in refs.targets
    assert ("net/minecraft/class_310", "method_1") in refs.methods


def test_refmap_named_by_the_config_is_found_even_without_the_suffix(tmp_path: Path) -> None:
    # A dash and no ".refmap" substring: only the config field can lead here.
    path = jar(tmp_path / "c.jar", {
        "m.mixins.json": json.dumps({"refmap": "map.json", "package": "p"}),
        "map.json": json.dumps(FORGE_REFMAP),
    })
    assert mixin_references(path).targets


def test_broken_refmap_is_ignored_not_guessed(tmp_path: Path) -> None:
    path = jar(tmp_path / "d.jar", {"m.refmap.json": "{not json"})
    refs = mixin_references(path)
    assert refs.targets == {} and refs.methods == {}


def test_non_zip_yields_empty(tmp_path: Path) -> None:
    p = tmp_path / "broken.jar"
    p.write_bytes(b"not a zip")
    assert mixin_references(p).targets == {}


# --- what the pack report does with them ------------------------------------
def test_two_jars_on_the_same_member_list_one_row(tmp_path: Path) -> None:
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", body={"mappings": {"pkg/a/A": {
            "target": "net/minecraft/X", "method": {"h": "m_1_"}}}}),
        "b.jar": fabric("beta", body={"mappings": {"pkg/b/B": {
            "target": "net/minecraft/X", "method": {"g": "m_1_"}}}}),
    })
    rep = analyse(root)
    assert len(rep.overlaps) == 1
    row = rep.overlaps[0]
    assert row["scope"] == "member"
    assert row["member"] == "m_1_"
    assert row["jars"] == ["a.jar", "b.jar"]


def test_same_class_different_members_is_a_class_row(tmp_path: Path) -> None:
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", body={"mappings": {"pkg/a/A": {
            "target": "net/minecraft/X", "method": {"h": "m_1_"}}}}),
        "b.jar": fabric("beta", body={"mappings": {"pkg/b/B": {
            "target": "net/minecraft/X", "method": {"g": "m_2_"}}}}),
    })
    rows = analyse(root).overlaps
    assert [r["scope"] for r in rows] == ["class"]
    assert rows[0]["member"] == ""


def test_a_single_jar_never_overlaps_itself(tmp_path: Path) -> None:
    root = pack(tmp_path, {"a.jar": fabric("alpha", body={"mappings": {
        "pkg/a/A": {"target": "net/minecraft/X", "method": {"h": "m_1_"}},
        "pkg/a/B": {"target": "net/minecraft/X", "method": {"i": "m_1_"}},
    }})})
    rep = analyse(root)
    assert rep.overlaps == []
    assert rep.mixin_coverage["jars_with_refmap"] == 1


def test_overlap_is_not_a_finding(tmp_path: Path) -> None:
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", body={"mappings": {"pkg/a/A": {
            "target": "net/minecraft/X", "method": {"h": "m_1_"}}}}),
        "b.jar": fabric("beta", body={"mappings": {"pkg/b/B": {
            "target": "net/minecraft/X", "method": {"g": "m_1_"}}}}),
    })
    rep = analyse(root)
    assert not [f for f in rep.findings if "mixin" in f.kind]


def test_coverage_distinguishes_no_overlap_from_no_refmap(tmp_path: Path) -> None:
    with_refmap = pack(tmp_path / "one", {
        "a.jar": fabric("alpha", body={"mappings": {"pkg/a/A": {
            "target": "net/minecraft/X", "method": {"h": "m_1_"}}}}),
    })
    without = pack(tmp_path / "two", {"b.jar": fabric("beta", refmap=None)})

    cov_a = analyse(with_refmap).mixin_coverage
    cov_b = analyse(without).mixin_coverage
    assert cov_a["jars_with_refmap"] == 1 and cov_a["targets"] == 1
    assert cov_b["jars_with_refmap"] == 0 and cov_b["targets"] == 0


def test_json_export_carries_the_bucket(tmp_path: Path) -> None:
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", body={"mappings": {"pkg/a/A": {
            "target": "net/minecraft/X", "method": {"h": "m_1_"}}}}),
        "b.jar": fabric("beta", body={"mappings": {"pkg/b/B": {
            "target": "net/minecraft/X", "method": {"g": "m_1_"}}}}),
    })
    data = analyse(root).to_dict()
    assert data["overlaps"][0]["scope"] == "member"
    assert data["mixin_coverage"]["jars_with_refmap"] == 2
