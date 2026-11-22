"""Pack Doctor: two jars declaring the same mixin config collide at load time."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mcd.metadata.jars import mixin_config_names
from mcd.pack.doctor import analyse


def jar(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return path


def fabric(modid: str, *, config: str | None = None) -> dict[str, str]:
    body = {"schemaVersion": 1, "id": modid, "version": "1.0.0", "depends": {}}
    if config:
        body["mixins"] = [config]
    entries = {"fabric.mod.json": json.dumps(body)}
    if config:
        entries[config] = json.dumps({"required": True, "package": modid,
                                      "mixins": [], "client": []})
    return entries


def test_mixin_config_names_reads_basenames(tmp_path: Path) -> None:
    j = jar(tmp_path / "a.jar", {"common.mixins.json": "{}",
                                 "deep/dir/client.mixins.json": "{}",
                                 "fabric.mod.json": "{}",
                                 "assets/x.txt": "x"})
    assert mixin_config_names(j) == ["client.mixins.json", "common.mixins.json"]


def test_broken_jar_yields_no_names(tmp_path: Path) -> None:
    p = tmp_path / "broken.jar"
    p.write_bytes(b"not a zip")
    assert mixin_config_names(p) == []


def test_collision_is_reported_once(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    jar(mods / "alpha.jar", fabric("alpha", config="shared.mixins.json"))
    jar(mods / "beta.jar", fabric("beta", config="shared.mixins.json"))

    rep = analyse(mods)
    hits = [f for f in rep.findings if f.kind == "pack.mixin-config-collision"]
    assert len(hits) == 1
    assert hits[0].subject == "shared.mixins.json"
    assert sorted(hits[0].evidence) == ["alpha.jar", "beta.jar"]


def test_distinct_configs_are_not_a_collision(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    jar(mods / "alpha.jar", fabric("alpha", config="alpha.mixins.json"))
    jar(mods / "beta.jar", fabric("beta", config="beta.mixins.json"))
    rep = analyse(mods)
    assert not [f for f in rep.findings if f.kind == "pack.mixin-config-collision"]
