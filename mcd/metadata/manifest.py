"""Read mod metadata out of `.jar` manifests (ROADMAP 1D.1).

WHY THIS EXISTS
---------------
`docs/RESEARCH.md` J1: a mod's own manifest declares its hard dependencies and
its negative edges (`conflicts`, `breaks`, `type = "incompatible"`). Those are
author declarations, not statistical inference, so they outrank the 9,721
`co_occurred` pairs in `corpus/compat-edges.jsonl` -- which, notably, contain no
pairwise negative edge at all. This module is the reader for that signal.

SCOPE, DELIBERATELY NARROW
--------------------------
We read metadata only. We never extract classes, never run bytecode, never
verify signatures. A jar is a zip with a small text file in it; treating it as
anything more would mean executing untrusted code from the internet, which this
project will not do.

What is covered:

    fabric.mod.json            Fabric
    quilt.mod.json             Quilt (quilt_loader section)
    META-INF/mods.toml         Forge
    META-INF/neoforge.mods.toml NeoForge

What is NOT covered (documented so callers do not over-trust the result):

  * nested jars (`META-INF/jars/*.jar`) -- Fabric bundles dependencies this way;
    those mods are present in the pack but invisible here.
  * `META-INF/MANIFEST.MF` -- FreeBSD-style attributes, no dependency info.
  * version-range *satisfaction*. Ranges are preserved verbatim as strings
    (`[1.20.1,1.21)`). Interpreting Maven range semantics belongs to the
    version-mismatch check (ROADMAP 2.2), not to the reader.
  * `mcmod.info` (ancient Forge, pre-1.13) -- the ecosystem has moved on and
    those packs are no longer reported against.

VOCABULARY
----------
Four loaders use three different spellings for the same three ideas, so
everything is normalised to one enum-ish string:

    required      depends / mandatory=true / type="required"
    optional      recommends, suggests / mandatory=false / type="optional"
    incompatible  conflicts, breaks / type="incompatible", "discouraged"

`hard` separates the two kinds of negative edge that Fabric distinguishes:
`breaks` and NeoForge `incompatible` mean "must not load together", while
Fabric `conflicts` only means "known to misbehave together". Both are negative
edges; only `hard` ones justify refusing to launch.

Zero dependencies beyond the standard library, and no `tomllib` requirement:
Python 3.9/3.10 have no `tomllib`, so a bounded TOML subset parser lives here.
Its agreement with `tomllib` is asserted by tests on 3.11+ rather than assumed.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:  # Python 3.11+
    import tomllib as _tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on 3.9/3.10
    _tomllib = None

FABRIC_MANIFEST = "fabric.mod.json"
QUILT_MANIFEST = "quilt.mod.json"
FORGE_MANIFEST = "META-INF/mods.toml"
NEOFORGE_MANIFEST = "META-INF/neoforge.mods.toml"

#: Manifest filenames we look for, in priority order (a jar normally has one).
MANIFEST_NAMES: tuple[str, ...] = (
    FABRIC_MANIFEST,
    QUILT_MANIFEST,
    NEOFORGE_MANIFEST,
    FORGE_MANIFEST,
)

_REQUIRED = "required"
_OPTIONAL = "optional"
_INCOMPATIBLE = "incompatible"

# Fabric's two negative relations are not the same strength. `breaks` is fatal,
# `conflicts` is advisory; collapsing them would make us refuse to launch packs
# that only warn.
_NEGATIVE_KEYS = {"conflicts": False, "breaks": True}


class ManifestError(ValueError):
    """The jar could not be read as a jar at all (corrupt, or not a zip)."""


@dataclass(frozen=True)
class Dependency:
    """One declared relationship to another mod."""

    modid: str
    kind: str                                  # required|optional|incompatible
    version_range: str | None = None           # verbatim, e.g. "[1.20.1,1.21)"
    side: str | None = None                    # CLIENT|SERVER|BOTH (Forge family)
    ordering: str | None = None                # BEFORE|AFTER|NONE (load order only)
    hard: bool = False                         # "must not load together"

    def to_dict(self) -> dict[str, Any]:
        return {
            "modid": self.modid,
            "kind": self.kind,
            "version_range": self.version_range,
            "side": self.side,
            "ordering": self.ordering,
            "hard": self.hard,
        }


@dataclass(frozen=True)
class ModManifest:
    """What one mod declares about itself. A jar may declare several mods."""

    modid: str
    name: str
    version: str | None
    loader: str                                # fabric|quilt|forge|neoforge
    source: str                                # manifest filename inside the jar
    depends: tuple[Dependency, ...] = field(default_factory=tuple)
    provides: tuple[str, ...] = field(default_factory=tuple)

    @property
    def hard_requirements(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.depends if d.kind == _REQUIRED)

    @property
    def negatives(self) -> tuple[Dependency, ...]:
        """Declared *negative* edges -- the whole point of this module."""
        return tuple(d for d in self.depends if d.kind == _INCOMPATIBLE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "modid": self.modid,
            "name": self.name,
            "version": self.version,
            "loader": self.loader,
            "source": self.source,
            "depends": [d.to_dict() for d in self.depends],
            "provides": list(self.provides),
        }


# --------------------------------------------------------------------------
# minimal TOML subset (enough for mods.toml, nothing more)
# --------------------------------------------------------------------------
class TomlSubsetError(ValueError):
    """The document uses TOML we deliberately do not implement."""


_STR_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b",
                "f": "\f"}


def _strip_comment(line: str) -> str:
    """Drop a trailing `#` comment, but not one inside a quoted string."""
    out: list[str] = []
    quote = ""
    escaped = False
    for ch in line:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\" and quote:
            out.append(ch)
            escaped = True
            continue
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_scalar(raw: str) -> Any:
    """Parse the value forms that appear in mods.toml."""
    text = raw.strip()
    if not text:
        raise TomlSubsetError("empty value")
    if text.startswith('"'):
        if not text.endswith('"') or len(text) < 2:
            raise TomlSubsetError(f"unterminated string: {text!r}")
        body, out, i = text[1:-1], [], 0
        while i < len(body):
            ch = body[i]
            if ch == "\\":
                nxt = body[i + 1] if i + 1 < len(body) else ""
                out.append(_STR_ESCAPES.get(nxt, nxt))
                i += 2
                continue
            out.append(ch)
            i += 1
        return "".join(out)
    if text.startswith("'"):
        return text[1:-1] if text.endswith("'") else text[1:]
    if text.startswith("["):
        return _parse_array(text)
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    compact = text.replace("_", "")
    try:
        return int(compact)
    except ValueError:
        pass
    try:
        return float(compact)
    except ValueError:
        pass
    raise TomlSubsetError(f"unsupported value: {text!r}")


def _split_array_items(body: str) -> list[str]:
    """Split on commas at depth 0, respecting quotes and nested brackets."""
    items: list[str] = []
    buf: list[str] = []
    quote = ""
    depth = 0
    escaped = False
    for ch in body:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\" and quote:
            buf.append(ch)
            escaped = True
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ('"', "'"):
            quote = ch
            buf.append(ch)
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf)
    if tail.strip():
        items.append(tail)
    return [i for i in (x.strip() for x in items) if i]


def _parse_array(text: str) -> list[Any]:
    body = text.strip()
    if not body.endswith("]"):
        raise TomlSubsetError(f"unterminated array: {text!r}")
    inner = body[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(item) for item in _split_array_items(inner)]


_TABLE_RE = re.compile(r"^\[\[?\s*([A-Za-z0-9_.\-\"]+)\s*\]\]?$")


def parse_toml_subset(text: str) -> dict[str, Any]:
    """Parse the narrow TOML subset used by `mods.toml`.

    Supported: comments, `[table]`, `[[array-of-tables]]`, `key = value` with
    strings, booleans, numbers and arrays (including multi-line arrays).
    Not supported: dates, inline tables, dotted keys, multi-line strings. Those
    never appear in a mod manifest; if one does, we raise instead of guessing,
    because a silently wrong dependency is worse than a loud failure.
    """
    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    pending_key: str | None = None
    pending_buf: list[str] = []

    def flush() -> None:
        nonlocal pending_key, pending_buf
        if pending_key is not None:
            current[pending_key] = _parse_scalar(" ".join(pending_buf))
            pending_key, pending_buf = None, []

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        if pending_key is not None:
            pending_buf.append(line.strip())
            # Balance must be judged on the ACCUMULATED text, not this line:
            # in `depends = [\n "a",\n "b",\n]` the middle lines have zero
            # brackets and would otherwise flush the array early.
            joined = " ".join(pending_buf)
            if joined.count("[") == joined.count("]"):
                flush()
            continue
        if line.lstrip().startswith("["):
            flush()
            is_array = line.lstrip().startswith("[[")
            match = _TABLE_RE.match(line.strip())
            if not match:
                raise TomlSubsetError(f"line {lineno}: bad table header {line!r}")
            path = tuple(
                p.strip().strip('"') for p in match.group(1).split(".") if p.strip()
            )
            node = root
            for part in path[:-1]:
                nxt = node.setdefault(part, {})
                if isinstance(nxt, list):
                    nxt = nxt[-1] if nxt else {}
                node = nxt
            leaf = path[-1]
            if is_array:
                bucket = node.setdefault(leaf, [])
                if not isinstance(bucket, list):
                    raise TomlSubsetError(
                        f"line {lineno}: {leaf!r} was a table, now an array"
                    )
                current = {}
                bucket.append(current)
            else:
                existing = node.setdefault(leaf, {})
                if isinstance(existing, list):
                    existing = existing[-1] if existing else {}
                current = existing
            continue
        if "=" not in line:
            raise TomlSubsetError(f"line {lineno}: expected key = value, got {line!r}")
        key, _, value = line.partition("=")
        key = key.strip().strip('"')
        value = value.strip()
        if value.startswith("[") and value.count("[") != value.count("]"):
            pending_key, pending_buf = key, [value]   # multi-line array
            continue
        current[key] = _parse_scalar(value)
    flush()
    return root


def _load_toml(text: str) -> dict[str, Any]:
    """Prefer `tomllib` (3.11+); fall back to the subset parser, never guess."""
    if _tomllib is not None:
        try:
            return _tomllib.loads(text)
        except Exception as exc:  # noqa: BLE001 - re-raised with context
            raise TomlSubsetError(f"tomllib rejected the manifest: {exc}") from exc
    return parse_toml_subset(text)


# --------------------------------------------------------------------------
# per-loader readers
# --------------------------------------------------------------------------
def _as_str(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _dep_from_value(modid: str, value: Any, *, kind: str, hard: bool) -> Dependency:
    """Fabric expresses a dependency as a bare range string or an object."""
    if isinstance(value, str):
        return Dependency(modid=modid, kind=kind, version_range=value or None,
                          hard=hard)
    if isinstance(value, dict):
        return Dependency(
            modid=modid,
            kind=kind,
            version_range=_as_str(value.get("version") or value.get("versions")),
            hard=hard,
        )
    return Dependency(modid=modid, kind=kind, hard=hard)


def _iter_relation(block: Any) -> Iterable[tuple[str, Any]]:
    """`depends` may be a mapping (Fabric) or a list of {id, ...} (Quilt)."""
    if isinstance(block, dict):
        for key, value in block.items():
            if isinstance(key, str) and key.strip():
                yield key.strip(), value
    elif isinstance(block, list):
        for entry in block:
            if isinstance(entry, str):
                yield entry.strip(), None
            elif isinstance(entry, dict):
                ident = _as_str(entry.get("id") or entry.get("modid"))
                if ident:
                    yield ident, entry


def _parse_fabric_like(data: dict[str, Any], *, loader: str, source: str,
                       section: dict[str, Any]) -> ModManifest | None:
    modid = _as_str(section.get("id"))
    if not modid:
        return None
    metadata = section.get("metadata") if isinstance(section.get("metadata"), dict) else {}
    name = _as_str(metadata.get("name")) or _as_str(data.get("name")) or modid
    version = _as_str(section.get("version")) or _as_str(data.get("version"))

    deps: list[Dependency] = []
    for key, value in _iter_relation(section.get("depends")):
        deps.append(_dep_from_value(key, value, kind=_REQUIRED, hard=False))
    for key in ("recommends", "suggests"):
        for target, value in _iter_relation(section.get(key)):
            deps.append(_dep_from_value(target, value, kind=_OPTIONAL, hard=False))
    for key, hard in _NEGATIVE_KEYS.items():
        for target, value in _iter_relation(section.get(key)):
            deps.append(_dep_from_value(target, value, kind=_INCOMPATIBLE, hard=hard))

    provides: list[str] = []
    raw_provides = section.get("provides")
    if isinstance(raw_provides, list):
        for entry in raw_provides:
            ident = entry if isinstance(entry, str) else _as_str(
                (entry or {}).get("id") if isinstance(entry, dict) else None
            )
            if ident:
                provides.append(ident.strip())

    return ModManifest(
        modid=modid,
        name=name,
        version=version,
        loader=loader,
        source=source,
        depends=tuple(deps),
        provides=tuple(provides),
    )


def parse_fabric_json(text: str, *, source: str = FABRIC_MANIFEST) -> list[ModManifest]:
    """Read a `fabric.mod.json` (a jar declares exactly one mod this way)."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ManifestError(f"{source}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{source}: expected a JSON object")
    manifest = _parse_fabric_like(data, loader="fabric", source=source, section=data)
    return [manifest] if manifest else []


def parse_quilt_json(text: str, *, source: str = QUILT_MANIFEST) -> list[ModManifest]:
    """Read a `quilt.mod.json`; the payload lives under `quilt_loader`."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ManifestError(f"{source}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{source}: expected a JSON object")
    section = data.get("quilt_loader")
    if not isinstance(section, dict):
        return []
    manifest = _parse_fabric_like(data, loader="quilt", source=source, section=section)
    return [manifest] if manifest else []


_NEOFORGE_KIND = {
    "required": (_REQUIRED, False),
    "optional": (_OPTIONAL, False),
    "incompatible": (_INCOMPATIBLE, True),
    "discouraged": (_INCOMPATIBLE, False),
}


def parse_mods_toml(text: str, *, loader: str = "forge",
                    source: str = FORGE_MANIFEST) -> list[ModManifest]:
    """Read `mods.toml` / `neoforge.mods.toml`; one jar may declare many mods."""
    try:
        data = _load_toml(text)
    except TomlSubsetError as exc:
        raise ManifestError(f"{source}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - tomllib raises its own types
        raise ManifestError(f"{source}: unreadable TOML ({exc})") from exc

    blocks = data.get("mods")
    if not isinstance(blocks, list):
        return []
    deps_by_mod = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}

    out: list[ModManifest] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        modid = _as_str(block.get("modId") or block.get("modid"))
        if not modid:
            continue
        name = _as_str(block.get("displayName")) or modid
        version = _as_str(block.get("version"))
        deps: list[Dependency] = []
        for entry in deps_by_mod.get(modid) or []:
            if not isinstance(entry, dict):
                continue
            target = _as_str(entry.get("modId") or entry.get("modid"))
            if not target:
                continue
            kind_raw = _as_str(entry.get("type"))
            if kind_raw and kind_raw.lower() in _NEOFORGE_KIND:
                kind, hard = _NEOFORGE_KIND[kind_raw.lower()]
            elif "mandatory" in entry:
                kind = _REQUIRED if entry.get("mandatory") else _OPTIONAL
                hard = False
            else:
                kind, hard = _REQUIRED, False
            deps.append(
                Dependency(
                    modid=target,
                    kind=kind,
                    version_range=_as_str(entry.get("versionRange")),
                    side=(_as_str(entry.get("side")) or "").upper() or None,
                    ordering=(_as_str(entry.get("ordering")) or "").upper() or None,
                    hard=hard,
                )
            )
        out.append(
            ModManifest(
                modid=modid,
                name=name,
                version=version,
                loader=loader,
                source=source,
                depends=tuple(deps),
                provides=(),
            )
        )
    return out


def _decode(raw: bytes) -> str:
    """Manifests are UTF-8; a BOM happens, a hard failure should not."""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_jar(path: str | Path) -> list[ModManifest]:
    """Read every mod a jar declares. Empty list means "no known manifest".

    An empty list is a legitimate answer -- libraries, resource packs and
    shader packs live in `mods/` too. It is NOT an error, so the caller can
    report "this jar declares nothing we can check" instead of crashing.
    """
    jar = Path(path)
    try:
        with zipfile.ZipFile(jar) as zf:
            names = set(zf.namelist())
            for candidate in MANIFEST_NAMES:
                if candidate not in names:
                    continue
                text = _decode(zf.read(candidate))
                if candidate == FABRIC_MANIFEST:
                    return parse_fabric_json(text, source=candidate)
                if candidate == QUILT_MANIFEST:
                    return parse_quilt_json(text, source=candidate)
                if candidate == NEOFORGE_MANIFEST:
                    return parse_mods_toml(text, loader="neoforge", source=candidate)
                return parse_mods_toml(text, loader="forge", source=candidate)
    except zipfile.BadZipFile as exc:
        raise ManifestError(f"{jar.name}: not a readable jar/zip ({exc})") from exc
    except OSError as exc:
        raise ManifestError(f"{jar.name}: {exc}") from exc
    return []


__all__ = [
    "Dependency",
    "ModManifest",
    "ManifestError",
    "TomlSubsetError",
    "MANIFEST_NAMES",
    "parse_fabric_json",
    "parse_quilt_json",
    "parse_mods_toml",
    "parse_jar",
    "parse_toml_subset",
]
