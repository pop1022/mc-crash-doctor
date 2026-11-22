"""What a jar's mixins actually modify, read from the refmaps it ships.

WHY REFMAPS AND NOT BYTECODE
  The authoritative answer lives in @Mixin(targets = "...") annotations inside
  the class files, which means implementing a class-file parser. Every mixin
  built by Loom or by the Mixin annotation processor also ships a refmap JSON:
  the compiler writes it so the runtime can remap names, and it lists, per mixin
  class, the target class and the mapped names of the members it references.
  Reading that file is exact, needs no bytecode reader, and cannot invent a
  target that is not there.

  A jar without a refmap is not covered -- and the report says so with a count
  instead of a silent zero. See doctor.py, which prints coverage next to the
  overlaps.

WHAT THE TWO SHAPES LOOK LIKE
  Forge / Mixin AP:   {"mappings": {"pkg/FooMixin": {"target": "net/minecraft/X",
                       "method": {"handler": "func_12345_a"}}}}
  Fabric / Loom:      {"mappings": {}, "data": {"named:intermediary":
                       {"pkg/FooMixin": {"target": "net/minecraft/class_123",
                       "method": {"handler": "method_1"}}}}

  The "method" dict maps the name used in the annotation to the real member, so
  its VALUES are what two jars collide on. Keys are per-mod and never collide.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from pathlib import Path

__all__ = ["JarMixins", "mixin_references"]


@dataclass
class JarMixins:
    """Targets a single jar declares, grouped the way a collision is detected.

    targets:  target class -> mixin classes that touch it
    methods:  (target class, mapped member) -> mixin classes that touch it

    Both are keyed by name as it appears in the refmap: obfuscated names for
    Forge jars, intermediary for Fabric ones. Two jars from the same loader
    namespace therefore compare correctly; two different loaders do not, and
    they would never be installed together anyway.
    """

    targets: dict[str, set[str]] = field(default_factory=dict)
    methods: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    refmaps: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.targets


def _body(raw: bytes) -> dict:
    """The mapping body of one refmap: "mappings", else the first "data" ns.

    Both keys existing is normal (Loom writes an empty "mappings" next to a
    populated "data"), so an empty dict must not win over a populated one.
    A refmap that parses to neither is skipped -- it tells us nothing, and
    guessing targets from filenames would be exactly the kind of invention
    this project avoids.
    """
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    body = obj.get("mappings")
    if isinstance(body, dict) and body:
        return body
    data = obj.get("data")
    if isinstance(data, dict):
        for ns_body in data.values():
            if isinstance(ns_body, dict) and ns_body:
                return ns_body
    return body if isinstance(body, dict) else {}


def _refmap_names(zf: zipfile.ZipFile, configs: list[str]) -> list[str]:
    """Refmaps this jar ships: the ones its mixin configs name, plus any
    filename that ends in "refmap.json" (Loom and Mixin AP both name them that
    way, with either a dot or a dash before the suffix)."""
    names = set(zf.namelist())
    out: list[str] = []
    for cfg in configs:
        try:
            obj = json.loads(zf.read(cfg).decode("utf-8", errors="replace"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        ref = obj.get("refmap") if isinstance(obj, dict) else None
        if isinstance(ref, str) and ref:
            # Configs name the refmap relative to the jar root, sometimes
            # relative to the config's own directory. Try both.
            base = str(PurePosixPath(cfg).parent)
            for cand in (ref, f"{base}/{ref}" if base != "." else ref):
                cand = cand.lstrip("/")
                if cand in names:
                    out.append(cand)
                    break
    for name in sorted(names):
        if name.lower().endswith("refmap.json"):
            out.append(name)
    return sorted(set(out))


def mixin_references(jar: str | Path) -> JarMixins:
    """Targets declared by the jar's refmaps. Unreadable jar -> empty result."""
    result = JarMixins()
    try:
        with zipfile.ZipFile(jar) as zf:
            configs = [n for n in zf.namelist() if n.endswith(".mixins.json")]
            for name in _refmap_names(zf, configs):
                result.refmaps.append(str(PurePosixPath(name).name))
                body = _body(zf.read(name))
                for mixin, entry in body.items():
                    if not isinstance(entry, dict):
                        continue
                    target = entry.get("target")
                    if not isinstance(target, str) or not target:
                        continue
                    short = str(PurePosixPath(mixin.replace(".", "/")).name)
                    result.targets.setdefault(target, set()).add(short)
                    methods = entry.get("method")
                    if not isinstance(methods, dict):
                        continue
                    for mapped in methods.values():
                        if isinstance(mapped, str) and mapped:
                            result.methods.setdefault((target, mapped), set()).add(short)
    except (OSError, zipfile.BadZipFile):
        return JarMixins()
    return result
