"""Tell mods apart from loaders and libraries in a crash report's file list.

WHY THIS MODULE EXISTS
---------------------
`corpus/index.jsonl` has a `jars` field holding every `~[...]` token found in the
harvested reports. That field is **raw evidence**: it records what was on the
classpath, and the classpath is mostly *not* mods.

The regex that collects it (`JAR_RE` in `tools/harvest_corpus.py`) matches any
`~[name.jar]` suffix, which covers three very different things:

    ~[guava-32.1.2-jre.jar:?]            a JVM library
    ~[neoforge-21.1.250-universal.jar]   the loader itself
    ~[Jade-1.20.1-Forge-11.13.1.jar]     an actual mod

Crash reports before 1.20 separated these with a `-- Mod List --` section; those
reports are gone from current issue traffic, so mods and libraries now arrive
through the same channel and **cannot be told apart by position**. Any consumer
that treats `jars` as a mod list will therefore report loader internals as
"mods the user installed".

ROADMAP 1D.4 requires consumers to distinguish 库 / 模组 / 未知 explicitly
instead of silently assuming. This module is that distinction, in one place, so
the audit tool and future consumers share one definition rather than each
carrying a private copy.

WHAT THIS CANNOT DO
-------------------
Classification is by **filename only** -- nothing here opens a jar (that is
`mcd.metadata.manifest`) or asks an API (that is `tools/audit_modrinth_mapping.py`).
Two consequences, both deliberate:

1. `"mod"` means **"not a known loader or runtime artifact"**, which is an
   assumption, not proof. It is the weakest of the four verdicts and is named
   as such: see `ASSUMED_MOD`.
2. The two lists below are the entire input. If a name is missing from both,
   it is assumed to be a mod. That keeps the classification auditable -- you
   can read all of it -- at the cost of being incomplete for exotic libraries.

    >>> classify_jar("~[guava-32.1.2-jre.jar:?]")
    'library'
    >>> classify_jar("neoforge-21.1.250-universal.jar")
    'loader'
    >>> classify_jar("Jade-1.20.1-Forge-11.13.1.jar")
    'mod'
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Iterable

__all__ = [
    "ASSUMED_MOD",
    "JAR_KINDS",
    "LOADER_ARTIFACTS",
    "RUNTIME_LIBS",
    "classify_jar",
    "is_loader_artifact",
    "is_runtime_lib",
    "jar_stem",
    "mixin_stem",
    "norm_key",
    "partition_jars",
]

#: The four verdicts. `mod` is an assumption (see module docstring); `unknown`
#: means we could not derive a name at all. Keeping them distinct is the point:
#: collapsing `unknown` into `mod` would hide the weakest evidence.
JAR_KINDS: tuple[str, ...] = ("loader", "library", "mod", "unknown")

#: Alias with a name that cannot be misread as "confirmed mod".
ASSUMED_MOD = "mod"

# --------------------------------------------------------------------------
# the two auditable lists
# --------------------------------------------------------------------------
#: Loader / platform artifacts. These look like mod filenames but no mod site
#: publishes them and no user installs or removes them.
LOADER_ARTIFACTS = frozenset({
    "forge", "neoforge", "fabric", "fabricloader",
    "quilt", "quiltloader", "minecraft", "client", "server", "vanilla",
    "paper", "spigot", "bukkit", "purpur", "mohist", "arclight",
    "java", "jre", "jdk", "installer", "universal", "coremods",
    # FML is Forge's loader itself, not a mod that can be installed or removed.
    "fmlloader", "fmlcore", "javafmllanguage", "lowcodelanguage", "mclanguage",
})

#: Java / Minecraft runtime libraries. These ship with the JVM, the game, or
#: the loader.
#:
#: Every entry is a runtime *namespace* (`com.google.*`, `net.neoforged.bus`,
#: `org.spongepowered.mixin`, `org.objectweb.asm`, `io.netty.*`) -- never
#: "whatever failed to resolve", which would make the list an unfalsifiable
#: dumping ground. Adding a name here lowers reported mod counts, so each
#: addition should be justified by a namespace, not by an inconvenient result.
RUNTIME_LIBS = frozenset({
    "guava", "bus", "mixin", "asm", "netty", "gson", "log4j", "slf4j",
    "jopt-simple", "authlib", "brigadier", "datafixerupper", "fastutil",
    "oshi", "jna", "jline", "joml", "text2speech", "lwjgl",
    "commons-lang3", "commons-io", "commons-codec",
    "httpclient", "httpcore", "eventbus", "mixinextras",
    "jankson", "quilt-json5", "night-config", "toml4j",
    "annotations", "checker-qual", "error_prone_annotations",
    "failureaccess", "jsr305", "j2objc-annotations", "listenablefuture",
    "jarjar", "srgutils", "unsafe", "securejarhandler", "bootstraplauncher",
})

# Two entries that used to sit in the list above are deliberately absent:
# bare `config` and bare `annotations`. Neither can be tied to a namespace by
# filename alone (`org.jetbrains:annotations` and a mod called "Annotations"
# produce the same stem), and both occurred 0 times in the 488-issue corpus, so
# they did no work while adding a way to silently swallow a real mod. Removing
# them is a measured no-op: the audit report is byte-identical either way.
# Missing a library inflates the mod count (a visible, conservative error);
# dropping a mod hides it (an invisible error). Prefer the former.

#: Suffixes that name a build variant of the same mod, not a different mod.
#: `eternal_starlight-common` and `eternal_starlight` are one project.
_VARIANT_SUFFIXES = frozenset({
    "common", "fabric", "forge", "neoforge", "quilt", "xplat", "mojmap",
    "universal", "client", "server", "dev", "api",
})

#: Words that mark a side/build qualifier rather than part of the mod name.
_SIDES = frozenset({
    "forge", "fabric", "neoforge", "quilt", "common", "universal", "client",
    "server", "all", "mc", "xplat", "mojmap", "srg", "official", "dev",
})

#: A version segment is NUMERIC-ONLY ("1.20.1", "v2", "4.8.11+1.21.1"), not
#: merely something starting with a digit -- otherwise `3dskinlayers` (a real
#: mod) would be discarded as if it were a version.
_VERSIONISH = re.compile(r"^(?:v?(?:\d+\.)*\d+(?:\+.*)?|mc\d.*)$", re.IGNORECASE)

_SPLIT = re.compile(r"[-_+. ]+")


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------
def norm_key(text: str) -> str:
    """Collapse to [a-z0-9] so `create_connected` == `Create-Connected`."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def jar_stem(filename: str) -> str:
    """Best-effort mod name from a jar filename.

    Filenames in the wild are hostile: URL-encoded brackets, leading `[1.20.1]`
    markers, version triples, loader suffixes, stack-frame decorations. We keep
    the leading run of non-version segments and stop at the first thing that
    looks like a version or a side tag:

        `Jade-1.20.1-Forge-11.13.1.jar`                 -> `Jade`
        `lambdynamiclights-4.8.11+1.21.1-neoforge.jar`  -> `lambdynamiclights`
        `~[guava-32.1.2-jre.jar:?]`                     -> `guava`
        `[1.20.1] mcmod-2.0.jar`                        -> `mcmod`

    Returns `""` rather than a garbage token when nothing usable remains.

    Bracket handling is three separate steps, because the two shapes are not
    symmetric: a *wrapper* is `[...]` around the whole token, a *prefix* is
    `[1.20.1] name.jar`. Treating them with one rule (the obvious
    `base.rsplit("]", 1)[-1]`) returns `""` for every stack-frame entry, since
    there the `]` is last and everything after it is nothing.
    """
    base = urllib.parse.unquote(filename).rsplit("/", 1)[-1].strip()
    if base.startswith("~"):                  # `~[` stack-frame marker
        base = base[1:]
    if base.startswith("[") and base.endswith("]"):
        base = base[1:-1]                     # `[name.jar:?]` wrapper
    if "]" in base:
        base = base.rsplit("]", 1)[-1]        # `[1.20.1] name.jar` prefix
    base = re.sub(r":.*$", "", base)          # `:?` / `!` stack-frame tail
    base = re.sub(r"\.jar$", "", base, flags=re.IGNORECASE).strip(" ._-")
    keep: list[str] = []
    for part in _SPLIT.split(base):
        if not part:
            continue
        if _VERSIONISH.match(part):
            break
        if keep and part.lower() in _SIDES:
            break
        keep.append(part)
    return "-".join(keep) if keep else ""


def mixin_stem(cfg: str) -> str:
    """`balm.neoforge` -> `balm`, `eternal_starlight-common` -> `eternal_starlight`.

    Mixin configs are namespaced by the owning mod (`pl:mixin:APP:<config>`), so
    a trailing dot segment or a build-variant suffix names the same project.
    Leaving them on guarantees a miss: `eternal_starlight-common` appeared in 10
    reports and resolves to nothing, while `eternal-starlight` resolves.
    """
    out = re.sub(r"\.mixins(\.json)?$", "", cfg.strip(), flags=re.IGNORECASE)
    for side in ("client", "common", "server", "forge", "fabric",
                 "neoforge", "quilt", "mojmap"):
        out = re.sub(rf"\.{side}$", "", out, flags=re.IGNORECASE)
    match = re.match(r"^(.+?)[-_]([A-Za-z]+)$", out)
    if match and match.group(2).lower() in _VARIANT_SUFFIXES:
        out = match.group(1)
    # `flywheel.backend` -> `flywheel`: the first segment is the mod id
    if "." in out:
        out = out.split(".", 1)[0]
    return out


#: Pre-normalised lookup sets. Comparing a normalised key against the raw
#: literals silently fails for every hyphenated entry: `commons-lang3` normalises
#: to `commonslang3`, which is not the string `"commons-lang3"`, so the family
#: check fell through to `commons` and the answer was False. That bug was live in
#: tools/audit_modrinth_mapping.py before this module existed.
_RUNTIME_KEYS = frozenset(norm_key(x) for x in RUNTIME_LIBS)
_LOADER_KEYS = frozenset(norm_key(x) for x in LOADER_ARTIFACTS)


def _family_root(name: str) -> str:
    return norm_key(_SPLIT.split(name)[0]) if name else ""


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------
def is_runtime_lib(name: str) -> bool:
    """True for Java/Minecraft runtime libraries, which are not mods.

    Matches the full normalised name and the family root, so `netty-transport`
    and `asm-util` are caught via `netty` / `asm`.
    """
    key = norm_key(name)
    if key in _RUNTIME_KEYS:
        return True
    return _family_root(name) in _RUNTIME_KEYS


def is_loader_artifact(name: str) -> bool:
    """True for loader / platform jars (`neoforge-...-universal.jar`)."""
    return norm_key(name) in _LOADER_KEYS


def classify_jar(filename: str) -> str:
    """One of `JAR_KINDS`, by filename only.

    ORDER IS THE CONTRACT -- loader, then library, then assumed mod, then
    unknown. `coremods` appears in both lists; it is a loader component, so the
    loader check must come first. `tests/test_jar_kinds.py` pins this.
    """
    stem = jar_stem(filename)
    if not stem:
        return "unknown"
    if is_loader_artifact(stem):
        return "loader"
    if is_runtime_lib(stem):
        return "library"
    return ASSUMED_MOD


def partition_jars(jars: Iterable[str]) -> dict[str, list[str]]:
    """Split a raw `jars` field into the four kinds, preserving input order.

    Every input lands in exactly one bucket, so `sum(len(v)) == len(input)`.
    That invariant is what lets a consumer print "of 312 classpath entries,
    68 are mods" without losing or double-counting an entry.
    """
    out: dict[str, list[str]] = {kind: [] for kind in JAR_KINDS}
    for jar in jars:
        out[classify_jar(jar)].append(jar)
    return out
