"""Platform / loader fingerprinting.

Two orthogonal axes, because conflating them was a real bug:

* **loader**  -- what runs the game: forge, neoforge, fabric, quilt, the
  bukkit family (paper/spigot/...), hybrids (mohist/magma/arclight),
  proxies (velocity/bungeecord), bedrock-side (bedrock/pocketmine/geyser).
* **launcher** -- what started it: prism-launcher, multimc, the vanilla
  launcher. A Prism-wrapped Fabric client is *both*; the loader axis must win
  the "what platform is this" question and the launcher is reported separately.

Why not bare substring matching: game content poisons it. ``glowstone`` is a
block name, a Paper server legitimately has ``org.geysermc.geyser`` in its
plugin list, and a crash report's Mod List contains *hundreds* of mod names --
so scanning the whole text with weak needles mislabels the server software.

Hence three evidence tiers, resolved by (tier, earliest offset):

* T0 -- authoritative banner signatures: ``git-Paper``, ``git-Magma``,
  ``Loading Minecraft 1.21 with Fabric Loader``, ``Booting up Velocity``.
  These are printed by the software about itself.
* T1 -- strong startup lines: ``This server is running Paper version``,
  ``Fabric Mods:``, ``ModLauncher running: args``.
* T2 -- weak: bare package names, which may merely be a dependency or plugin.

Order matters within a tier, so hybrids/proxies are listed before the generic
families they embed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Evidence tiers. Higher = more authoritative.
T0, T1, T2 = 0, 1, 2


@dataclass(frozen=True)
class Probe:
    loader: str
    tier: int
    pattern: re.Pattern[str]
    axis: str = "loader"      # "loader" | "launcher"


def _p(s: str) -> re.Pattern[str]:
    return re.compile(s, re.I | re.M)


# --- launcher axis ----------------------------------------------------------
LAUNCHER_PROBES: list[Probe] = [
    Probe("prism-launcher", T0, _p(r"^\s*Prism Launcher version:"), axis="launcher"),
    Probe("multimc", T0, _p(r"^\s*MultiMC version:"), axis="launcher"),
    Probe("curseforge-app", T0, _p(r"^\s*CurseForge Launcher|twitch app"), axis="launcher"),
    Probe("gdlauncher", T0, _p(r"^\s*GDLauncher"), axis="launcher"),
    Probe("minecraft-launcher", T0, _p(r"Running launcher bootstrap"), axis="launcher"),
    Probe("minecraft-launcher", T1, _p(r"NetQueue\.cpp"), axis="launcher"),
]

# --- loader axis ------------------------------------------------------------
# Hybrids and proxies first: they embed Forge/Bukkit markers, and their own
# signature is what identifies the actual server software.
PROBES: list[Probe] = [
    # T0 -- software says its own name
    # ── Forge/Bukkit hybrids: their self-identity markers cannot appear in a
    # plain Forge or Bukkit log, so they are T0 and outrank the family probes
    # by list order. This matters because a Forge-family T0 marker
    # (--fml.forgeVersion) sits at offset ~160 in a Mohist log while Mohist's
    # own banner is thousands of characters later.
    Probe("magma", T0, _p(r"git-Magma|Magma version [^\s(]|magmafoundation")),
    Probe("mohist", T0, _p(r"git-Mohist|Mohist version|\bMohist \d+\.\d+|mohistmc")),
    Probe("arclight", T0, _p(r"\[Arclight/|Arclight version|io\.izzel\.arclight")),
    Probe("catserver", T0, _p(r"git-CatServer|CatServer version")),
    Probe("velocity", T0, _p(r"Booting up Velocity")),
    Probe("waterfall", T0, _p(r"git:Waterfall-Bootstrap")),
    Probe("bungeecord", T0, _p(r"git:BungeeCord-Bootstrap|Enabled BungeeCord version")),
    Probe("purpur", T0, _p(r"git-Purpur")),
    Probe("paper", T0, _p(r"git-Paper")),
    Probe("folia", T0, _p(r"git-Folia")),
    Probe("spigot", T0, _p(r"git-Spigot")),
    Probe("craftbukkit", T0, _p(r"git-CraftBukkit")),
    Probe("glowstone", T0, _p(r"git-Glowstone")),
    # Quilt BEFORE fabric: Quilt is a Fabric fork and reuses the Knot class
    # loader, so a Quilt log legitimately contains "Service=Knot/Fabric".
    # Its own banner is the discriminator and must be tested first.
    Probe("quilt", T0, _p(r"Loading Minecraft [\w.\-+]+ with Quilt Loader")),
    Probe("quilt", T0, _p(r"Service=Knot/Quilt")),
    Probe("quilt", T0, _p(r"^\s*Quilt Mods:")),
    Probe("fabric", T0, _p(r"Loading Minecraft [\w.\-+]+ with Fabric Loader")),
    Probe("fabric", T0, _p(r"\[FabricLoader\] Loading \d+ mods:")),
    Probe("fabric", T0, _p(r"Service=Knot/Fabric")),
    # NeoForge prints "NeoForge: net.neoforged:<ver>" in its crash reports.
    Probe("neoforge", T0, _p(r"NeoForge: net\.neoforged:")),
    Probe("neoforge", T0, _p(r"--fml\.neoForgeVersion")),
    Probe("neoforge", T0, _p(r"NeoForge version \d")),
    # Package-qualified references only. A bare "neoforge" is NOT evidence:
    # mod mixin configs are named "balm.neoforge.mixins.json",
    # "curios.neoforge.mixins.json" etc. and appear in plain Forge logs too
    # (5579 hits in one real NeoForge log were almost all of these).
    Probe("neoforge", T1, _p(r"net\.neoforged\.")),
    Probe("neoforge", T1, _p(r"\bneoforge-\d+\.\d+")),
    Probe("forge", T0, _p(r"--fml\.forgeVersion")),
    Probe("forge", T0, _p(r"Forge Mod Loader[ \]]|\bForge\{\d+\.\d+|\[FML/?:\]")),
    Probe("forge", T1, _p(r"net\.minecraftforge\.")),
    # Crash reports carry "Known server brands: fabric|quilt|paper|..." in the
    # Level section -- the most direct self-declaration available.
    Probe("quilt", T0, _p(r"Known server brands:.*\bquilt\b")),
    Probe("fabric", T0, _p(r"Known server brands:.*\bfabric\b")),
    Probe("paper", T0, _p(r"Known server brands:.*\bpaper\b")),
    Probe("purpur", T0, _p(r"Known server brands:.*\bpurpur\b")),
    Probe("spigot", T0, _p(r"Known server brands:.*\bspigot\b")),
    Probe("pocketmine", T0, _p(r"Loading pocketmine\.yml|PocketMine-MP \d")),
    Probe("geyser", T0, _p(r"Loading Geyser version")),
    Probe("bedrock", T0, _p(
        r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.:]?\d* INFO\][^\n]*"
        r"(?:Starting Server|Version [\d.*]+|Session ID|Level Name:)")),
    # Bedrock behaviour/resource-pack content log (a distinct aternos analyser)
    Probe("bedrock-content", T0, _p(
        r"^\d{2}:\d{2}:\d{2}\[(?:Blocks|Items|Scripting)\]\["), axis="loader"),
    Probe("custom-skin-loader", T0, _p(r"CustomSkinLoader \d+\.\d+")),

    # T1 -- strong startup / structural lines.
    # Hybrid identity markers sit here (not T0) but win by rank, since PROBES
    # lists hybrids before the forge/bukkit families they embed.
    Probe("magma", T1, _p(r"Magma version \d")),
    Probe("mohist", T1, _p(r"This server is running Mohist version|Mohist version"
                            r"|\bMohist \d+\.\d+")),
    Probe("arclight", T1, _p(r"Arclight version")),
    Probe("velocity", T1, _p(r"Velocity \d+\.\d+\.\d+")),
    Probe("quilt", T1, _p(r"^\s*Quilt Mods:")),
    Probe("fabric", T1, _p(r"^\s*Fabric Mods:")),
    Probe("fabric", T1, _p(r"Fabric Loader \d+\.\d+")),
    # Fabric-only startup lines (present even in a 1.6 KB truncated log)
    Probe("fabric", T1, _p(r"Found new data pack Fabric Mods")),
    Probe("fabric", T1, _p(r"Applied \d+ biome modifications to")),
    Probe("purpur", T1, _p(r"Purpur version")),
    # Paper BEFORE bukkit: a Paper log is full of org.bukkit.* too, so the
    # generic bukkit probe must not outrank Paper's own package name.
    Probe("paper", T1, _p(r"This server is running Paper version|Running Paper\b"
                          r"|io\.papermc\.(?:paper|folia)")),
    Probe("purpur", T1, _p(r"io\.papermc\.purpur")),
    Probe("folia", T1, _p(r"This server is running Folia version|Folia version")),
    Probe("spigot", T1, _p(r"This server is running Spigot version|Spigot version")),
    Probe("craftbukkit", T1, _p(
        r"This server is running CraftBukkit version|CraftBukkit version")),
    # Glowstone prints no self-identifying banner in short logs; these two
    # lines are its structural signature.
    Probe("glowstone", T1, _p(
        r"Preparing spawn for world: \d+%\n[^\n]*\[\w+\] Preparing spawn for world:")),
    Probe("glowstone", T1, _p(r"Binding query to address")),
    Probe("geyser", T1, _p(r"Geyser version \d")),
    Probe("pocketmine", T1, _p(r"pocketmine\.yml|Selected .* as the base language")),
    Probe("neoforge", T1, _p(r"NeoForge Mod Loader|neoforge-\d+[\w.\-]*-universal\.jar")),
    # "ModLauncher running: args" is the *log* form; crash reports carry the
    # System Details form instead ("ModLauncher: 8.1.3",
    # "ModLauncher launch target: fmlserver").
    Probe("forge", T1, _p(r"Forge Mod Loader version|ModLauncher running: args"
                          r"|cpw\.mods\.modlauncher"
                          r"|^\s*ModLauncher:\s*\d+"
                          r"|ModLauncher launch target: fml")),
    Probe("bukkit", T1, _p(r"org\.bukkit\.|Bukkit version")),

    # T2 -- weak: bare package names (may be a plugin/dependency, not the host)
    # Hybrid package names are T1, not T2: they are as specific as
    # net.minecraftforge. (which is also T1) and can never appear in a plain
    # Forge log, so rank -- hybrids are listed earlier -- decides correctly.
    Probe("mohist", T1, _p(r"mohistmc")),
    Probe("magma", T1, _p(r"magmafoundation")),
    Probe("arclight", T1, _p(r"io\.izzel\.arclight")),
    Probe("velocity", T2, _p(r"com\.velocitypowered")),
    Probe("bungeecord", T2, _p(r"net\.md_5\.bungee")),
    Probe("quilt", T2, _p(r"org\.quiltmc")),
    Probe("fabric", T2, _p(r"net\.fabricmc\.|fabric-loader-\d")),
    Probe("purpur", T2, _p(r"org\.purpurmc")),
    Probe("paper", T2, _p(r"io\.papermc\.")),
    Probe("spigot", T2, _p(r"org\.spigotmc")),
    Probe("craftbukkit", T2, _p(r"org\.bukkit\.craftbukkit")),
    Probe("glowstone", T2, _p(r"net\.glowstone")),
    Probe("geyser", T2, _p(r"org\.geysermc")),
    Probe("bukkit", T2, _p(r"\bbukkit\b")),
]

# Families that collapse to the same coarse label (used by the eval harness).
FAMILY: dict[str, str] = {
    "paper": "bukkit", "spigot": "bukkit", "craftbukkit": "bukkit",
    "purpur": "bukkit", "folia": "bukkit", "glowstone": "bukkit",
    "mohist": "hybrid", "magma": "hybrid", "arclight": "hybrid",
    "catserver": "hybrid",
}


@dataclass
class PlatformHit:
    loader: str
    tier: int
    offset: int
    evidence: str
    axis: str = "loader"
    probe_index: int = 0    # position in PROBES: the specificity rank


def _scan(text: str, probes: list[Probe], window: int, offset: int = 0) -> list[PlatformHit]:
    scope = text[:window]
    hits: list[PlatformHit] = []
    for i, pr in enumerate(probes):
        m = pr.pattern.search(scope)
        if m:
            hits.append(PlatformHit(pr.loader, pr.tier, offset + m.start(),
                                    m.group(0)[:60], pr.axis, probe_index=i))
    return hits


HEAD_WINDOW = 40000


def _collect(text: str) -> list[PlatformHit]:
    """Gather probe hits.

    Scans the head first, then the *rest* of the file whenever the head produced
    no authoritative (T0) hit. Crash reports put their platform banners late --
    a NeoForge report's ``NeoForge: net.neoforged:<ver>`` line sits past 140 KB,
    behind the stack trace and Mod List -- so a head-only scan silently
    downgrades it to plain Forge.
    """
    hits = _scan(text, PROBES + LAUNCHER_PROBES, HEAD_WINDOW)
    if len(text) > HEAD_WINDOW and not any(h.tier == T0 for h in hits):
        tail = text[HEAD_WINDOW:]
        hits += _scan(tail, PROBES + LAUNCHER_PROBES, len(tail), offset=HEAD_WINDOW)
    return hits


def _best(hits: list[PlatformHit], order: list[str]) -> PlatformHit | None:
    """Pick the winner.

    Ordering is (tier, specificity-rank, offset): the most authoritative tier
    wins, and *within* a tier the probe listed first wins -- list order encodes
    specificity (hybrids before the families they embed), which must not be
    overridden by where the marker happens to appear. A Forge-family marker
    sits at offset ~150 in a Magma log while ``git-Magma`` is at ~4000; sorting
    by offset there mislabels the server.

    The rank is the matched probe's own index, not a per-loader lookup: the same
    loader appears at several indices (magma has T0/T1/T2 probes), and a dict
    keyed by loader name would keep only the last -- collapsing Magma's T0
    banner down to its T2 package-name rank and losing it to plain Forge.
    """
    if not hits:
        return None
    return min(hits, key=lambda h: (h.tier, h.probe_index, h.offset))


_ORDER_LOADER = [p.loader for p in PROBES]
_ORDER_LAUNCHER = [p.loader for p in LAUNCHER_PROBES]


def detect_platform_detailed(text: str) -> tuple[PlatformHit | None, PlatformHit | None]:
    """Return (loader_hit, launcher_hit); either may be None."""
    hits = _collect(text)
    loader_hits = [h for h in hits if h.axis == "loader"]
    launcher_hits = [h for h in hits if h.axis == "launcher"]
    return _best(loader_hits, _ORDER_LOADER), _best(launcher_hits, _ORDER_LAUNCHER)


def detect_platform(text: str) -> tuple[str, str]:
    """Return ``(loader_id, evidence)``; ``("vanilla", "")`` when nothing fires."""
    hit, _ = detect_platform_detailed(text)
    if hit is None:
        return "vanilla", ""
    return hit.loader, hit.evidence


def detect_launcher(text: str) -> tuple[str, str]:
    """Return ``(launcher_id, evidence)``; ``("", "")`` when not launcher-wrapped."""
    _, hit = detect_platform_detailed(text)
    if hit is None:
        return "", ""
    return hit.loader, hit.evidence


# --- version extraction -----------------------------------------------------
# Each entry: (loader-agnostic) regex with group 1 = Minecraft version.
_VERSION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # crash report System Details
    ("system-details", re.compile(r"^\s*Minecraft Version:\s*([^\s(]+)", re.M)),
    # FML debug line: VersionInfo[forgeVersion=52.0.24, mcVersion=1.21.1, ...]
    ("forge", re.compile(r"\bmcVersion=([\w.\-]+)")),
    ("forge", re.compile(r"ModLauncher[^\n]*?mcVersion[= ]([\w.\-]+)", re.I)),
    ("forge", re.compile(r"--fml\.mcVersion,\s*([\w.\-]+)")),
    ("forge", re.compile(r"for MC ([\w.\-]+) with MCP", re.I)),
    ("forge", re.compile(
        r"(?:Forge|NeoForge) Mod Loader version [\w.]+ for Minecraft ([\w.\-]+)", re.I)),
    # forge jar naming: forge-1.21.3-53.0.7-client.jar
    ("forge", re.compile(r"\bforge-(\d+\.\d+(?:\.\d+)?)-\d+[\w.\-]*-")),
    # launcher --version arg: "26.1-forge-62.0.3" or "1.20.1-forge-47.1.3"
    ("forge", re.compile(r"--version,\s*(\d+\.\d+(?:\.\d+)?|\d{2}w\d{2}[a-z])-forge-")),
    ("forge", re.compile(r"^.*for Minecraft ([\w.\-]+)(?: loading| version)", re.M)),
    ("fabric", re.compile(
        r"Loading Minecraft ([\w.\-+]+) with (?:Fabric|Quilt) Loader", re.I)),
    ("fabric", re.compile(r"Minecraft Version:\s*([\w.\-+]+)", re.I)),
    ("bukkit", re.compile(r"\(MC:\s*([\w.\-]+)\)")),
    ("bukkit", re.compile(r"Starting minecraft server version ([\w.\-]+)", re.I)),
    ("bukkit", re.compile(
        r"(?:Paper|Spigot|Purpur|CraftBukkit|Folia|Glowstone) version "
        r"[\w.\-]+ \(MC: ([\w.\-]+)\)", re.I)),
    ("neoforge", re.compile(r"NeoForge [\d.]+ for Minecraft ([\w.\-]+)")),
    ("generic", re.compile(r"^.*Minecraft Version ID:\s*([\w.\-]+)", re.M)),
    ("generic", re.compile(r"\bMinecraft ([\w.\-]+)\b(?! Server)")),
    # snapshot startup line: "Starting minecraft server version 19w34a"
    ("generic", re.compile(r"server version (\d{2}w\d{2}[a-z])")),
]

# Accept releases (1.20.1), snapshots (19w34a, 21w05b) and the year-based
# versioning Minecraft moved to (26.1). Rejects mod/loader versions like
# "1.4.3-1.20.1" or "0.11.1" by requiring no leading-zero component and a
# sane length.
_MC_VER_RE = re.compile(r"^(?:\d+\.\d+(?:\.\d+)?(?:[\w.\-+]*)?|\d{2}w\d{2}[a-z])$")


def _looks_like_mc_version(v: str) -> bool:
    v = v.strip()
    if not v or len(v) > 24:
        return False
    if " " in v:
        return False
    return bool(_MC_VER_RE.match(v))


def detect_version(text: str, loader: str = "") -> str:
    """Best-effort Minecraft version.

    Tiered, because widening the scan window naively is unsafe: a 5 MB client
    log contains ``Playing Minecraft 1.21.1`` inside a Discord Rich-Presence
    payload (KDiscordIPC). That string is *usually* right but is not a version
    declaration, so low-confidence patterns are confined to the head window
    while loader-derived patterns may search the whole file.
    """
    head = text[:60000]
    # Tier 1: authoritative declarations, head window
    for tag, pat in _VERSION_PATTERNS:
        if tag in ("system-details", loader):
            m = pat.search(head)
            if m and _looks_like_mc_version(m.group(m.lastindex or 1)):
                return m.group(m.lastindex or 1).strip()
    # Tier 2: loader-derived, full text (NeoForge/Forge versions encode the MC
    # version, and their banners can sit deep in a long log)
    v = _version_from_loader(text, loader)
    if v:
        return v
    for tag, pat in _VERSION_PATTERNS:
        if tag == loader:
            m = pat.search(text)
            if m and _looks_like_mc_version(m.group(m.lastindex or 1)):
                return m.group(m.lastindex or 1).strip()
    # Tier 3: anything plausible, head window only
    for _, pat in _VERSION_PATTERNS:
        m = pat.search(head)
        if m and _looks_like_mc_version(m.group(m.lastindex or 1)):
            return m.group(m.lastindex or 1).strip()
    return ""


# NeoForge versioning is <mc-major>.<mc-minor>.<build>: 21.1.233 targets MC
# 1.21.1. Forge uses its own scheme, so only NeoForge can be reverse-derived.
_NEOFORGE_VER = re.compile(
    r"NeoForge version (\d+)\.(\d+)\.\d+|"
    # jar naming is 4-segment with a build suffix:
    # neoforge-26.1.0.1-beta-universal.jar -- only the first two segments
    # encode the MC version, so do NOT require a trailing "-<digits>" group
    # (a greedy [\w.\-]* would eat ".0.1-beta-universal" and fail the rest).
    r"neoforge-(\d+)\.(\d+)(?:\.\d+)*(?:[\w.\-]*)?\.jar|"
    r"net/neoforged/neoforge/(\d+)\.(\d+)", re.I)


def _version_from_loader(text: str, loader: str) -> str:
    """Derive the MC version from the loader's own version string."""
    if loader == "neoforge":
        for m in _NEOFORGE_VER.finditer(text[:400000]):
            g = [x for x in m.groups() if x is not None]
            if len(g) >= 2:
                maj, minor = int(g[0]), int(g[1])
                # sanity: NeoForge majors track MC minors (17 -> 1.17 ... 26 -> 26.x)
                if 17 <= maj <= 99 and minor < 30:
                    return f"1.{maj}.{minor}" if maj < 25 else f"{maj}.{minor}"
    return ""


# --- software version (for platforms whose "version" is not Minecraft's) -----
SOFTWARE_VERSION: dict[str, list[re.Pattern[str]]] = {
    "bedrock": [_p(r"\]\s*Version (\d+\.\d+\.\d+\.\d+)"),
                _p(r"Bedrock version (\d+\.\d+\.\d+\.\d+)")],
    # PocketMine's "version" is the Bedrock Edition protocol version it speaks
    # ("Starting Minecraft: Bedrock Edition server version v1.9.0"), NOT the
    # PocketMine-MP build (3.6.2). Two different numbers on two different lines.
    "pocketmine": [_p(r"Bedrock Edition server version v?(\d+\.\d+[\w.\-]*)"),
                   _p(r"PocketMine-MP (\d+\.\d+\.\d+[\w.\-]*)")],
    "geyser": [_p(r"Loading Geyser version ([\w.\-]+)")],
    # must not capture "CustomSkinLoader Core" (the logger name)
    "custom-skin-loader": [_p(r"CustomSkinLoader (\d+\.\d+[\w.\-]*)")],
    "velocity": [_p(r"Booting up Velocity ([\w.\-]+)")],
    "bungeecord": [_p(r"Enabled BungeeCord version ([\w:\.\-]+)")],
    "waterfall": [_p(r"Enabled Waterfall version ([\w:\.\-]+)")],
    "prism-launcher": [_p(r"^\s*Prism Launcher version:\s*([\w.\-]+)")],
    "multimc": [_p(r"^\s*MultiMC version:\s*([\w.\-]+)")],
}


def detect_software_version(text: str, loader: str = "", launcher: str = "") -> str:
    """Version of the platform software itself (Bedrock/PocketMine/Geyser/...)."""
    scope = text[:40000]
    for key in (loader, launcher):
        for pat in SOFTWARE_VERSION.get(key, []):
            m = pat.search(scope)
            if m:
                return m.group(1).strip()
    return ""


# --- loader version (distinct from Minecraft version) ------------------------
_LOADER_VERSION: dict[str, list[re.Pattern[str]]] = {
    "neoforge": [
        _p(r"NeoForge (\d+\.\d+[\w.\-+]*)"),
        _p(r"--fml\.neoForgeVersion,\s*([\w.\-]+)"),
        _p(r"neoforge-(\d+[\w.\-+]*)-universal\.jar"),
    ],
    "forge": [
        _p(r"Forge Mod Loader version ([\w.\-]+)"),
        _p(r"--fml\.forgeVersion,\s*([\w.\-]+)"),
        _p(r"\bforgeVersion=([\w.\-]+)"),
        # Crash reports name the loader jar: fmlloader-<mcver>-<forgever>.jar
        _p(r"fmlloader-(?:\d+\.\d+[\w.\-]*-)?(\d+\.\d+\.\d+[\w.\-]*)\.jar"),
        # .../libraries/net/minecraftforge/forge/<mcver>-<forgever>/
        _p(r"net[/\\]minecraftforge[/\\]forge[/\\][\w.\-]+-(\d+\.\d+\.\d+[\w.\-]*)"),
        # Only a path-anchored "forge-<ver>" -- a bare pattern also matches mod
        # jars in the Mod List such as "smsn-forge-1.4.3-1.20.1.jar".
        _p(r"[/\\]forge-(\d+\.\d+\.\d+[\w.\-]*)"),
        _p(r"MinecraftForge v([\w.\-]+)"),
    ],
    "fabric": [
        _p(r"Fabric Loader (\d+\.\d+[\w.\-+]*)"),
        _p(r"with Fabric Loader (\d+[\w.\-+]*)"),
        _p(r"fabric-loader-(\d+\.\d+[\w.\-+]*)"),
    ],
    "quilt": [
        _p(r"Quilt Loader (\d+\.\d+[\w.\-+]*)"),
        _p(r"with Quilt Loader (\d+[\w.\-+]*)"),
    ],
    "paper": [_p(r"git-Paper-(\d+)")],
    "spigot": [_p(r"git-Spigot-([\w.\-]+)")],
    "craftbukkit": [_p(r"git-CraftBukkit-([\w.\-]+)")],
    "purpur": [_p(r"git-Purpur-(\d+)")],
    "mohist": [_p(r"Mohist-(\d+\.\d+\.\d+-[\w.\-]+)")],
    "magma": [_p(r"Magma-(\d+\.\d+[\w.\-]*)")],
    "arclight": [_p(r"arclight-(\d+\.\d+[\w.\-]*)")],
    "velocity": [_p(r"Booting up Velocity ([\w.\-]+)")],
    "bungeecord": [_p(r"BungeeCord-Bootstrap:([\w.\-]+)")],
}


def detect_loader_version(text: str, loader: str) -> str:
    """Version of the loader/server software itself (not Minecraft's)."""
    pats = _LOADER_VERSION.get(loader) or []
    scope = text[:60000]
    for p in pats:
        m = p.search(scope)
        if m:
            return m.group(1).strip()
    return ""
