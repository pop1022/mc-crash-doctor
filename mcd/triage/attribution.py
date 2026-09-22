"""Suspect attribution: which mod is actually at fault?

This is the part generic log analysers do not attempt. A crash report gives
three independent provenance signals, and cross-indexing them against the
report's own Mod List turns "something crashed" into "mod X, with this much
confidence".

Signals, strongest first:

1. **Mixin ownership** -- ``pl:mixin:APP:create.mixins.json:Class from mod
   (create)`` names the mod that applied the patch *at the failing frame*.
   A mixin crash is nearly always the mixin owner's fault.
2. **Mod-id stack frames** -- the first non-vanilla, non-loader class in the
   root-cause trace, e.g. ``com.ferreusveritas.dynamictrees.util.CompatHelper``.
   The package root is matched against the Mod List to resolve a mod id.
3. **Jar names** -- ``~[some-mod-1.2.3.jar%2312!/:1.2.3]`` matched against the
   Mod List's file column.

Each candidate gets a score; scores are normalised to 0..1 confidence. The top
few are reported, because sometimes two mods are genuinely interacting (mod A's
mixin breaking mod B's class) and naming only one misleads the user.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..model import CrashReport, Mod, StackFrame

# Weights tuned by hand against real reports; see score() for rationale.
W_MIXIN = 10.0          # explicit ownership at the failing frame
W_MIXIN_CFG = 7.0       # mixin config prefix, ownership not printed
W_FRAME_TOP = 5.0       # mod-owned frame in the top 3 of the root cause
W_FRAME = 2.5           # mod-owned frame deeper in the root cause
W_JAR = 3.0             # jar seen at a failing frame
W_MSG_CLASS = 4.0       # mod class quoted in the exception message (no Mod List needed)
W_DESC = 1.0            # mod named in the description text only

# Vanilla / loader / library roots: a frame starting with one of these is NOT
# evidence of a mod's fault. Kept explicit so new loaders are easy to add.
NON_MOD_ROOTS = (
    "net.minecraft.", "java.", "javax.", "jdk.", "sun.", "com.sun.",
    "net.minecraftforge.", "net.neoforged.", "cpw.mods.", "org.spongepowered.",
    "org.apache.", "com.google.", "com.mojang.", "com.electronwill.",
    "it.unimi.", "oshi.", "io.netty.", "org.lwjgl.", "com.llamalad7.",
    "kotlin.", "kotlinx.", "scala.", "org.jetbrains.", "io.github.",
    "net.fabricmc.", "org.quiltmc.", "com.velocitypowered.", "net.md_5.",
    "io.papermc.", "org.bukkit.", "org.spigotmc.",
)

# Known package-prefix -> mod-id overrides for popular mods whose package root
# does not match their mod id (e.g. "com.ferreusveritas.dynamictrees" -> the
# mod is literally dynamictrees, but many are not that tidy).
PACKAGE_OVERRIDES: dict[str, str] = {
    "com.ferreusveritas.dynamictrees": "dynamictrees",
    "me.jellysquid.mods.lithium": "lithium",
    "me.jellysquid.mods.sodium": "sodium",
    "net.coderbot.iris": "iris",
    "shetiphian.core": "shetiphian_core",
    "vazkii.botania": "botania",
    "vazkii.quark": "quark",
    "vazkii.patchouli": "patchouli",
    "blusunrize.immersiveengineering": "immersiveengineering",
    "mcjty.theoneprobe": "theoneprobe",
    "mcjty.rftools": "rftools",
    "mcjty.xnet": "xnet",
    "mekanism.api": "mekanism",
    "mekanism.common": "mekanism",
    "mekanism.generators": "mekanismgenerators",
    "mekanism.additions": "mekanismadditions",
    "mekanism.tools": "mekanismtools",
    "com.simibubi.create": "create",
    "appeng.core": "ae2",
    "appeng.me": "ae2",
    "twilightforest.": "twilightforest",
    "com.gregtechceu.gtceu": "gtceu",
    "dev.latvian.mods.kubejs": "kubejs",
    "snownee.jade": "jade",
    "top.theillusivec4.curios": "curios",
    "top.theillusivec4.caelus": "caelus",
    "com.hollingsworth.arsnouveau": "ars_nouveau",
    "shadows.apotheosis": "apotheosis",
    "com.teamcofh.": "cofh_core",
    "lumien.hardcorequesting": "hqm",
    "com.github.glitchfiend": "biomesoplenty",
    "biomesoplenty.": "biomesoplenty",
    "com.github.alexthe666": "iceandfire",
    "alexthe666.": "iceandfire",
    "com.harbingerofdoom.": "harbinger",
    "de.maxhenkel.gravestone": "gravestone",
    "com.lothrazar.": "cyclic",
    "net.darkhax.": "bookshelf",
    "com.blakebr0.": "mysticalagriculture",
    "mezz.jei": "jei",
    "com.mrcrayfish": "cfm",
    "com.pam.harvestcraft": "pamhc2",
    "net.silentchaos512": "silentlib",
    "com.refinedmods.refinedstorage": "refinedstorage",
}


@dataclass
class Suspect:
    """One mod suspected of causing the crash."""

    modid: str
    name: str = ""
    file: str = ""
    version: str = ""
    score: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "modid": self.modid, "name": self.name, "file": self.file,
            "version": self.version, "score": round(self.score, 2),
            "confidence": round(self.confidence, 3), "reasons": self.reasons,
        }


@dataclass
class TriageResult:
    suspects: list[Suspect] = field(default_factory=list)
    unresolved_modids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "suspects": [s.to_dict() for s in self.suspects],
            "unresolved_modids": self.unresolved_modids,
            "notes": self.notes,
        }


# --- Mod List indexes -------------------------------------------------------
def _index_mods(rep: CrashReport) -> tuple[dict[str, Mod], dict[str, Mod], dict[str, Mod]]:
    """Return (by_modid, by_jarfile, by_package_root) indexes."""
    by_id: dict[str, Mod] = {}
    by_jar: dict[str, Mod] = {}
    for m in rep.mods:
        if m.modid:
            by_id[m.modid.lower()] = m
        if m.file:
            by_jar[_norm_jar(m.file).lower()] = m
    return by_id, by_jar, {}


_JAR_NOISE = re.compile(
    r"^(?:\[?[^\]]*\]?\s*)?|[-_]?(?:mc|forge|neoforge|fabric|quilt|universal|"
    r"client|server|all|release|snapshot)[-_]?\d*[\w.\-]*$", re.I)


def _norm_jar(name: str) -> str:
    """Reduce a jar filename to a comparable stem: 'create-1.20.1-0.5.1.jar' -> 'create'."""
    n = name
    n = re.sub(r"\.jar$", "", n, flags=re.I)
    # strip trailing version-ish chunks
    n = re.sub(r"[-_+]?(?:\d+\.\d+[\w.\-+]*)$", "", n)
    n = re.sub(r"[-_+]?(?:mc|forge|neoforge|fabric|quilt|universal|client|server)[-_]?\d*[\w.\-]*$",
               "", n, flags=re.I)
    n = re.sub(r"[-_+]?\d+\.\d+[\w.\-+]*$", "", n)
    n = re.sub(r"^\[[^\]]*\]\s*", "", n)   # "[1.20.1] foo" prefix
    return n.strip("-_ ")


def _jar_candidates(jar: str) -> list[str]:
    """Possible mod-id / jar-stem forms for a frame's jar marker."""
    base = jar.replace("%23", "#").split("!")[0]
    base = base.split("/")[-1].split("\\")[-1]
    out = [base.lower()]
    stem = _norm_jar(base).lower()
    if stem and stem not in out:
        out.append(stem)
    # mod jars are often "modid-<version>-<loader>.jar"
    parts = re.split(r"[-_+]", stem)
    if parts and parts[0] and parts[0] not in out:
        out.append(parts[0])
    return [o for o in out if o]


def _class_root(cls: str) -> str:
    """'com.foo.bar.Baz' -> 'com.foo.bar' (drop the class segment)."""
    if not cls:
        return ""
    segs = cls.split(".")
    if len(segs) >= 2 and segs[-1][:1].isupper():
        segs = segs[:-1]
    return ".".join(segs)


def _modid_from_class(cls: str, by_id: dict[str, Mod]) -> str | None:
    """Resolve a frame's class to a mod id via overrides, then by-id matching."""
    if not cls or cls.startswith(NON_MOD_ROOTS):
        return None
    root = _class_root(cls)
    # longest-prefix override match
    best = ""
    best_id = None
    for prefix, mid in PACKAGE_OVERRIDES.items():
        if (cls.startswith(prefix) or root.startswith(prefix.rstrip("."))) \
                and len(prefix) > len(best):
            best, best_id = prefix, mid
    if best_id:
        return best_id
    # heuristic: third-level package token is often the mod id
    # com.foo.<modid>.Thing  /  <org>.<modid>.Thing
    segs = [s for s in root.split(".") if s]
    for cand in reversed(segs[1:]):
        c = cand.lower().replace("_", "")
        if c in by_id:
            return c
    # also try the segment with underscores restored
    for cand in reversed(segs[1:]):
        if cand.lower() in by_id:
            return cand.lower()
    return None


# Well-known top-level org tokens that say nothing about the mod; used to
# decide whether a message class name is worth attributing at all.
_GENERIC_ROOTS = (
    "java", "javax", "jdk", "sun", "com.sun", "org.apache", "com.google",
    "com.mojang", "net.minecraft", "it.unimi", "oshi", "io.netty",
    "org.lwjgl", "kotlin", "scala", "org.spongepowered", "cpw", "dev.architectury",
)

_FQCN_RE = re.compile(r"\b((?:[\w$]+\.)+[A-Z][\w$]*)")


def message_modids(rep: CrashReport) -> list[tuple[str, str]]:
    """Mine exception messages for fully-qualified class names.

    Reports harvested from issue trackers are often fragments with no Mod
    List, but Java 14+ NPE messages quote the exact class and method:
    ``Cannot invoke "mekanism.common.lib.frequency.FrequencyController...``.
    That names the mod as surely as a stack frame does. Resolution order:
    PACKAGE_OVERRIDES, then Mod List match, then the package token heuristic.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for e in rep.exceptions:
        for m in _FQCN_RE.finditer(e.message or ""):
            cls = m.group(1)
            if cls in seen or cls.startswith(_GENERIC_ROOTS):
                continue
            seen.add(cls)
            mid = _modid_from_class(cls, {})
            if mid:
                out.append((mid, f"exception message references {cls}"))
    return out


def _mixin_config_modid(cfg: str, by_id: dict[str, Mod]) -> str | None:
    """'create.mixins.json' -> 'create'; 'harium.mixins' -> 'harium'."""
    c = cfg.replace(".mixins.json", "").replace(".mixins", "")
    c = c.split(".")[-1].lower()
    if not c:
        return None
    if c in by_id:
        return c
    for mid in by_id:
        if mid.replace("_", "") == c or c.replace("_", "") == mid:
            return mid
        if mid.endswith(c) or c.endswith(mid):
            if abs(len(mid) - len(c)) <= 3:
                return mid
    return c  # unresolved but still informative


def triage(rep: CrashReport, *, top_n: int = 5) -> TriageResult:
    """Attribute the crash to mods, strongest evidence first."""
    by_id, by_jar, _ = _index_mods(rep)
    res = TriageResult()
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)
    unresolved: list[str] = []

    def add(mid: str | None, weight: float, reason: str) -> None:
        if not mid:
            return
        scores[mid] += weight
        if reason not in reasons[mid]:
            reasons[mid].append(reason)

    # 1. mixin ownership -- the strongest signal
    seen_cfgs: set[str] = set()
    for e in rep.exceptions:
        for i, f in enumerate(e.frames[:25]):
            if f.mixin_owner_mod and f.mixin_owner_mod != "unknown":
                add(f.mixin_owner_mod.lower(), W_MIXIN,
                    f"mixin from mod '{f.mixin_owner_mod}' at frame #{i} "
                    f"({f.mixin_class or f.cls})")
            if f.mixin_config and f.mixin_config not in seen_cfgs:
                seen_cfgs.add(f.mixin_config)
                mid = _mixin_config_modid(f.mixin_config, by_id)
                if mid and mid in by_id:
                    add(mid, W_MIXIN_CFG,
                        f"mixin config '{f.mixin_config}.mixins.json' patches the failing path")
                elif mid:
                    unresolved.append(f"{mid} (from mixin config {f.mixin_config})")

    # 2. mod-owned frames in the root-cause trace
    rc = rep.root_cause
    trace_blocks = [rc] if rc else list(rep.exceptions[:1])
    for block in trace_blocks:
        if not block:
            continue
        for i, f in enumerate(block.frames[:40]):
            mid = _modid_from_class(f.cls, by_id)
            if not mid:
                continue
            w = W_FRAME_TOP if i < 3 else W_FRAME
            add(mid, w, f"stack frame #{i}: {f.cls}.{f.method}"
                        + (f" (line {f.line_no})" if f.line_no else ""))

    # 3. jar markers at failing frames
    for block in trace_blocks:
        if not block:
            continue
        for f in block.frames[:25]:
            if not f.jar:
                continue
            for cand in _jar_candidates(f.jar):
                if cand in by_id:
                    add(cand, W_JAR, f"jar on the failing path: {f.jar}")
                    break
                hit = by_jar.get(cand)
                if hit:
                    add(hit.modid or cand, W_JAR, f"jar on the failing path: {f.jar}")
                    break
            else:
                stem = _norm_jar(f.jar)
                if stem and not f.jar.startswith(("server-", "client-", "forge-",
                                                 "neoforge-", "minecraft-")):
                    unresolved.append(f"{stem} (jar {f.jar})")

    # 3.5 classes quoted in exception messages -- the only signal that works
    # on issue-tracker fragments, which often carry the NPE/ISE message but no
    # Mod List at all (by_id empty). Java 14+ messages name the exact class.
    for mid, reason in message_modids(rep):
        add(mid, W_MSG_CLASS, reason)

    # 4. mod named in the description / exception message
    blob = f"{rep.description} {' '.join(e.message for e in rep.exceptions)}".lower()
    for mid, m in by_id.items():
        if mid and len(mid) >= 4 and mid in blob:
            add(mid, W_DESC, f"named in the crash description/message")

    if not scores:
        if unresolved:
            res.notes.append(
                "No mod could be tied to the failing frames. The stack stays in "
                "vanilla/loader/library code, so the trigger may be world data, "
                "a resource/config, or a mod acting indirectly.")
        else:
            res.notes.append(
                "No mod attribution possible from this report: no mixin markers, "
                "no mod-owned stack frames, and no mod jars on the failing path.")
        res.unresolved_modids = sorted(set(unresolved))[:8]
        return res

    total = sum(scores.values()) or 1.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_score = ranked[0][1] if ranked else 0.0
    for mid, sc in ranked[:top_n]:
        m = by_id.get(mid.lower()) or by_id.get(mid)
        s = Suspect(
            modid=mid,
            name=m.name if m else "",
            file=m.file if m else "",
            version=m.version if m else "",
            score=sc,
            # confidence: share of total evidence, damped when the leader is
            # barely ahead of the runner-up (a genuine two-mod interaction).
            confidence=min(0.97, (sc / total) * (1.0 if sc == top_score else 0.85)),
            reasons=reasons[mid][:4],
        )
        res.suspects.append(s)
    res.unresolved_modids = sorted(set(unresolved))[:8]
    if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.8:
        a, b = ranked[0][0], ranked[1][0]
        res.notes.append(
            f"'{a}' and '{b}' score almost equally -- this looks like an "
            f"interaction between the two rather than one broken mod. "
            f"Remove one at a time to confirm.")
    return res


def suspects_for_rules(rep: CrashReport, sources: list[str],
                       caps: dict | None = None) -> list[str]:
    """Adapter used by the rule engine's ``suspects_from`` field."""
    t = triage(rep, top_n=3)
    out: list[str] = []
    for src in sources:
        if src == "mod_from_triage" or src == "frame_mods":
            for s in t.suspects:
                if s.modid not in out:
                    out.append(s.modid)
        elif src == "mixin":
            for f in rep.all_frames[:40]:
                if f.mixin_owner_mod and f.mixin_owner_mod != "unknown":
                    if f.mixin_owner_mod not in out:
                        out.append(f.mixin_owner_mod)
                elif f.mixin_config:
                    mid = _mixin_config_modid(f.mixin_config,
                                              {m.modid.lower(): m for m in rep.mods})
                    if mid and mid not in out:
                        out.append(mid)
        elif src == "jar":
            for f in rep.all_frames[:40]:
                if f.jar:
                    stem = _norm_jar(f.jar)
                    if stem and stem not in out:
                        out.append(stem)
        elif src.startswith("mod:"):
            mid = src[4:]
            if mid not in out:
                out.append(mid)
    return out[:6]
