"""A missing dependency says who pulls it in, one hop past the direct requirer.

"Install flywheel" is a chore; "install flywheel, because create needs it and
the pack needs create" is a reason. The chain is capped and cycle-safe, and a
single-link chain is not printed, so the common case keeps its short line.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mcd.pack.doctor import analyse


def fabric(modid: str, depends: dict[str, str] | None = None) -> str:
    return json.dumps({"schemaVersion": 1, "id": modid, "version": "1.0.0",
                       "depends": depends or {}})


def pack(tmp_path: Path, jars: dict[str, str]) -> Path:
    mods = tmp_path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name, manifest in jars.items():
        with zipfile.ZipFile(mods / name, "w") as z:
            z.writestr("fabric.mod.json", manifest)
    return tmp_path


def test_two_hop_chain_is_printed(tmp_path: Path) -> None:
    # delta is missing; gamma needs it and epsilon needs gamma. One hop would
    # just repeat "required by gamma", so the chain only appears from two on.
    root = pack(tmp_path, {
        "a.jar": fabric("epsilon", {"gamma": "*"}),
        "c.jar": fabric("gamma", {"delta": "*"}),
    })
    miss = analyse(root).by_kind("pack.missing-dependency")
    assert [f.subject for f in miss] == ["delta"]
    assert "chain: delta <- gamma <- epsilon" in miss[0].detail


def test_long_chain_is_walked_upward(tmp_path: Path) -> None:
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", {"beta": "*"}),
        "b.jar": fabric("beta", {"gamma": "*"}),
        "c.jar": fabric("gamma", {"omega": "*"}),
    })
    miss = analyse(root).by_kind("pack.missing-dependency")
    assert [f.subject for f in miss] == ["omega"]
    assert "chain: omega <- gamma <- beta <- alpha" in miss[0].detail


def test_single_hop_keeps_the_short_line(tmp_path: Path) -> None:
    # nobody requires create, so there is no second hop to print.
    root = pack(tmp_path, {"a.jar": fabric("alpha", {"create": "*"})})
    detail = analyse(root).by_kind("pack.missing-dependency")[0].detail
    assert "chain:" not in detail


def test_cycle_terminates_and_does_not_repeat_ids(tmp_path: Path) -> None:
    # alpha <-> beta is a circular requirement; gamma is missing. The walk must
    # stop rather than loop, and must not list a mod twice.
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", {"beta": "*", "gamma": "*"}),
        "b.jar": fabric("beta", {"alpha": "*"}),
    })
    detail = analyse(root).by_kind("pack.missing-dependency")[0].detail
    assert detail.count("alpha") == 2      # "required by alpha" + one chain slot
    assert detail.count("beta") == 1


def test_chain_only_names_mods_that_declare_a_hard_requirement(tmp_path: Path) -> None:
    # A `breaks` edge is not a requirement: beta must not appear in alpha's chain.
    breaks = json.dumps({"schemaVersion": 1, "id": "beta", "version": "1.0.0",
                         "depends": {}, "breaks": {"alpha": "*"}})
    root = pack(tmp_path, {
        "a.jar": fabric("alpha", {"gamma": "*"}),
        "b.jar": breaks,
    })
    detail = analyse(root).by_kind("pack.missing-dependency")[0].detail
    assert "beta" not in detail
