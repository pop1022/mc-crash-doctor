"""Pack Doctor: check a `mods/` directory against what its jars declare.

WHY THIS EXISTS
  Every diagnosis so far starts from a crash. That is one crash too late: half
  the packs people bring here are broken *before* launch -- a missing
  dependency, two versions of the same mod, a Forge jar in a Fabric pack -- and
  the loader's own message for that is a stack trace nobody enjoys reading.

  `mcd/metadata/manifest.py` (1D.1) already reads what each jar declares:
  `depends`, `conflicts`, `breaks`, `versionRange`. What was missing is the
  step that compares those declarations *against each other*. That is this
  module, and it needs no network -- which is why it can ship before the
  Modrinth work in 2.1/1D.2.

THE RULE THIS FILE IS BUILT AROUND
  ROADMAP 2.2: "认不出清单的 jar 必须显式列出，不许静默跳过". So there are
  four buckets, and only one of them is silent:

    findings    a declared problem (missing dep, version mismatch, duplicate,
                mixed loaders)
    undecided   we saw the constraint and could not interpret it
    unreadable  a jar we could not open, or that declares no known manifest
    checked     the counts behind the above, so "0 findings" can be told apart
                from "0 jars"

  `undecided` is the important one. `mcd/pack/version.py` returns None instead
  of guessing, and this module turns every None into a printed row. A checker
  that answers "ok" for a range it did not understand is the failure mode this
  project keeps finding.

TWO KINDS OF ANSWER, KEPT APART
  findings are contradictions between declarations. overlaps are two jars
  touching the same mixin target -- read from refmaps, printed with the coverage
  that produced them, and never counted as a problem. Mixin overlap is normal;
  it becomes evidence only when a crash names one of those mixins.

WHAT IS NOT CHECKED (deliberate, listed so callers do not over-trust)
  * nested jars (`META-INF/jars/*.jar`, Fabric's bundled libraries) -- their ids
    are read so they can satisfy a dependency, their own dependencies are not.
  * a jar that ships no refmap contributes no mixin targets; the coverage line
    says how many jars were actually read, so "no overlaps" cannot be mistaken
    for "no mixins".
  * whether a version actually exists / is the latest -- that needs 2.1.
  * load order (`ordering: BEFORE/AFTER`) -- conflicts are not decided by it.

    from mcd.pack.doctor import analyse
    rep = analyse("C:/servers/atm10")
    print(rep.summary_line())
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .mixins import mixin_references
from ..metadata.jars import mixin_config_names
from ..metadata.manifest import (ManifestError, ModManifest, nested_modids,
                                parse_jar)
from ..model import Severity
from .version import satisfies

__all__ = ["PackReport", "PackFinding", "analyse", "BUILTIN_IDS",
           "NOT_CHECKED", "not_checked"]

#: Ids the loader/platform always satisfies, so a `depends` on them is never a
#: missing dependency. Kept explicit rather than "anything without a version":
#: a library that is genuinely absent must still be reported.
BUILTIN_IDS = frozenset({
    "minecraft", "java", "forge", "neoforge", "fabricloader", "fabric-loader",
    "fabric", "fabric_loader", "quilt_loader", "quilt-loader", "quilted_fabric_api",
    "modlauncher", "securejarhandler", "bootstraplauncher", "fmlloader",
})

#: ROADMAP 2.2 asks for five finding families; one needs a reader change.
#: What this checker does not look at, printed with every report so nobody has to
#: infer it from silence. Two of the three entries disappear once the caller says
#: which side the directory is for -- that is what `--side` buys.
_NOT_CHECKED_ALWAYS = (
    "what a bundled jar (META-INF/jars, META-INF/jarjar) itself requires -- its "
    "mod ids are read, so it can satisfy a dependency, but its own declared "
    "dependencies are not checked",
)
_NOT_CHECKED_WITHOUT_SIDE = (
    "client-only mod installed on a server (pass `--side server|client` to check "
    "Fabric/Quilt's `environment` field)",
    "dependencies declared for one side only (side=CLIENT/SERVER) -- whether "
    "they are required depends on which side this directory runs",
)


def not_checked(side: str | None = None) -> tuple[str, ...]:
    """The limitations for a scan of `side` (None = the side is unknown)."""
    if side in ("client", "server"):
        return _NOT_CHECKED_ALWAYS
    return _NOT_CHECKED_WITHOUT_SIDE + _NOT_CHECKED_ALWAYS


#: The default (side-unknown) list, kept as a name because the renderer used it.
NOT_CHECKED = not_checked()


@dataclass
class PackFinding:
    """One actionable row. `kind` is stable so callers can filter on it."""

    kind: str
    severity: Severity
    subject: str
    detail: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity.name,
                "subject": self.subject, "detail": self.detail,
                "evidence": self.evidence}


@dataclass
class PackReport:
    root: str
    mods_dir: str
    jars: int = 0
    declared_mods: int = 0
    findings: list[PackFinding] = field(default_factory=list)
    undecided: list[dict] = field(default_factory=list)
    unreadable: list[dict] = field(default_factory=list)
    #: Two jars touch the same target class or the same member. Informational,
    #: not a finding: overlapping is normal and usually harmless, and calling it
    #: a problem would be the false-positive failure mode this project keeps
    #: finding. It becomes useful exactly when a crash names one of the mixins.
    overlaps: list[dict] = field(default_factory=list)
    #: How much of the pack the overlap check actually saw. Printed because
    #: "no overlaps" and "no jar shipped a refmap" must not look the same.
    mixin_coverage: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    loaders: dict = field(default_factory=dict)
    side: str | None = None         # client|server when the caller said so

    @property
    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.INFO)

    def by_kind(self, kind: str) -> list[PackFinding]:
        return [f for f in self.findings if f.kind == kind]

    def not_checked(self) -> tuple[str, ...]:
        """Limitations for *this* scan: `--side` removes two of the three."""
        return not_checked(self.side)

    def summary_line(self) -> str:
        return (f"{self.jars} jars, {self.declared_mods} declared mods, "
                f"{len(self.findings)} findings, "
                f"{len(self.undecided)} undecided, "
                f"{len(self.unreadable)} unreadable")

    def to_dict(self) -> dict:
        return {
            "root": self.root, "mods_dir": self.mods_dir,
            "jars": self.jars, "declared_mods": self.declared_mods,
            "context": self.context, "loaders": self.loaders,
            "side": self.side,
            "findings": [f.to_dict() for f in self.findings],
            "undecided": self.undecided, "unreadable": self.unreadable,
            "overlaps": self.overlaps, "mixin_coverage": self.mixin_coverage,
            "not_checked": list(self.not_checked()),
        }


def _mods_dir(root: Path) -> Path | None:
    """`root/mods` wins; a directory of bare jars is accepted as-is."""
    for candidate in (root / "mods", root):
        if candidate.is_dir() and any(candidate.glob("*.jar")):
            return candidate
    return None


def _pack_context(root: Path) -> dict:
    """What the pack manifest claims, if there is one (CurseForge / Modrinth).

    Informational only: it is nice to print "pack says 1.20.1 / forge-47.2.0"
    next to the findings, but nothing here decides whether the pack is broken.
    """
    out: dict = {}
    cf = root / "manifest.json"
    if cf.is_file():
        try:
            data = json.loads(cf.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return {"manifest": "unreadable"}
        mc = (data.get("minecraft") or {})
        if mc.get("version"):
            out["mc_version"] = str(mc["version"])
        ids = [str(m.get("id", "")) for m in (mc.get("modLoaders") or [])
               if isinstance(m, dict)]
        if ids:
            out["loader"] = ids[0]
        if isinstance(data.get("files"), list):
            out["declared_files"] = len(data["files"])
            out["manifest"] = "manifest.json"
    mr = root / "modrinth.index.json"
    if mr.is_file():
        try:
            data = json.loads(mr.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            out.setdefault("modrinth_index", "unreadable")
            return out
        deps = data.get("dependencies") or {}
        if deps.get("minecraft"):
            out.setdefault("mc_version", str(deps["minecraft"]))
        if isinstance(data.get("files"), list):
            out.setdefault("declared_files", len(data["files"]))
        out.setdefault("manifest", "modrinth.index.json")
    return out


def _requirement_chain(by_id: dict[str, list[tuple[Path, ModManifest]]],
                       missing: str, *, depth: int = 3) -> list[str]:
    """Who pulls *missing* in, nearest first: ['create', 'immersive_aircraft'].

    Only useful for a dependency that is absent: the direct requirer is already
    named in the finding, and the second hop is what turns "install flywheel"
    into "install flywheel, because create needs it and immersive_aircraft needs
    create". Depth is capped so a pack with a deep chain prints a line, not a
    family tree, and a cycle cannot loop: every id enters the chain once.
    """
    chain: list[str] = []
    frontier = {missing}
    seen = {missing}
    for _ in range(depth):
        layer = sorted(
            modid for modid, entries in by_id.items()
            if modid not in seen
            and any(d.modid in frontier for _jar, man in entries
                    for d in man.hard_requirements))
        if not layer:
            break
        chain.extend(layer)
        seen.update(layer)
        frontier = set(layer)
    return chain


def analyse(root: str | Path, *, side: str | None = None) -> PackReport:
    """Check a `mods/` directory.

    `side` is what the caller knows and the directory cannot say: `server` or
    `client`. With it, two questions become answerable -- whether a Fabric/Quilt
    mod declares itself for the other side, and which `side=`-scoped dependency
    requirements actually apply. Without it both stay in `not_checked`.
    """
    if side not in (None, "client", "server"):
        raise ValueError(f"side must be 'client' or 'server', not {side!r}")
    base = Path(root)
    mods = _mods_dir(base)
    if mods is None:
        # The old message named the same condition for three different
        # situations: a path that does not exist, a mods/ folder with no jars,
        # and a folder of unrelated files. The suffix says which one it is.
        if not base.is_dir():
            detail = (f"({base} is a file, not a directory)" if base.is_file()
                      else f"({base} does not exist)")
        elif (base / "mods").is_dir():
            detail = f"({base / 'mods'} holds no .jar files)"
        else:
            detail = f"(no {base / 'mods'}, and no .jar files in {base})"
        raise FileNotFoundError(
            f"no `mods/` directory with .jar files under {base} {detail}")

    rep = PackReport(root=str(base), mods_dir=str(mods),
                     context=_pack_context(base), side=side)

    by_id: dict[str, list[tuple[Path, ModManifest]]] = defaultdict(list)
    mixin_owner: dict[str, list[str]] = {}   # config name -> jars shipping it
    # target class -> jar -> mixin classes; and (target, member) -> jar -> the
    # same. Two levels because a shared class is ordinary (every performance mod
    # mixes into the client class) while a shared member is a real collision
    # candidate -- and even that is informational, not a finding.
    target_owner: dict[str, dict[str, set[str]]] = {}
    member_owner: dict[tuple[str, str], dict[str, set[str]]] = {}
    refmap_jars = 0
    provided: dict[str, str] = {}          # provided id -> who provides it
    loaders: dict[str, int] = defaultdict(int)
    jars = sorted(mods.glob("*.jar"))
    rep.jars = len(jars)

    for jar in jars:
        try:
            manifests = parse_jar(jar)
        except ManifestError as exc:
            reason = str(exc)
            # ManifestError already names the file; printing "broken.jar:
            # broken.jar: not a readable jar" reads like two problems.
            prefix = f"{jar.name}: "
            if reason.startswith(prefix):
                reason = reason[len(prefix):]
            rep.unreadable.append({"jar": jar.name, "reason": reason})
            continue
        # A jar can declare nothing at the top level and still provide mods:
        # JarJar/Fabric bundle them under META-INF/jarjar|jars. Reading only the
        # ids is enough to stop claiming a dependency is missing when it is
        # sitting inside another mod's jar (measured: 4 findings on a pack that
        # boots). The bundle's own dependencies are still not checked.
        for cfg in mixin_config_names(jar):
            mixin_owner.setdefault(cfg, []).append(jar.name)
        refs = mixin_references(jar)
        if not refs.empty:
            refmap_jars += 1
        for target, classes in refs.targets.items():
            target_owner.setdefault(target, {}).setdefault(jar.name, set()).update(classes)
        for key, classes in refs.methods.items():
            member_owner.setdefault(key, {}).setdefault(jar.name, set()).update(classes)
        bundled = nested_modids(jar)
        if not manifests and not bundled:
            rep.unreadable.append({
                "jar": jar.name,
                "reason": "no fabric.mod.json / quilt.mod.json / mods.toml "
                          "(library, resource pack or unknown layout)"})
            continue
        for m in manifests:
            rep.declared_mods += 1
            loaders[m.loader] += 1
            by_id[m.modid].append((jar, m))
            for pid in m.provides:
                provided.setdefault(pid, m.modid)
            # `environment` is a Fabric/Quilt field; Forge-family manifests do
            # not have one, so this can only ever fire for fabric/quilt mods --
            # which is exactly the population a NeoForge server pack gets wrong
            # when somebody drops a Fabric client mod into `mods/`.
            if (side and m.environment in ("client", "server")
                    and m.environment != side):
                other = "client" if side == "server" else "server"
                rep.findings.append(PackFinding(
                    kind="pack.wrong-side-mod",
                    severity=Severity.WARNING,
                    subject=m.modid,
                    detail=(f"{m.modid} declares environment={m.environment}, but "
                            f"this is a {side} directory: the loader skips it, so "
                            f"it is installed and never runs"
                            + (" (that also means the server is missing whatever "
                               "it was installed for)" if other == "server" else "")),
                    evidence=[jar.name]))
        for bid in bundled:
            provided.setdefault(bid, jar.name)

    # --- mixin config collisions -------------------------------------------
    # Two jars declaring the same <name>.mixins.json: the mixin service keeps
    # one and silently drops the other, or fails with mixin.apply-failed. It is
    # a declaration-level fact, so it is checkable without running the game.
    for cfg, owners in sorted(mixin_owner.items()):
        jars_for_cfg = sorted(set(owners))
        if len(jars_for_cfg) > 1:
            rep.findings.append(PackFinding(
                kind="pack.mixin-config-collision",
                severity=Severity.WARNING,
                subject=cfg,
                detail=(f"{len(jars_for_cfg)} jars ship a mixin config with the "
                        f"same name ({cfg}): " + ", ".join(jars_for_cfg)
                        + ". The mixin service applies one and drops or fails "
                          "the other; keep one jar per config."),
                evidence=jars_for_cfg))

    # --- mixin target overlaps (informational) -----------------------------
    # Deeper than a config-name collision: two jars injecting into the same
    # target member is what mixin.apply-failed / InvalidInjectionException look
    # like once the game runs. It is NOT a finding -- overlapping is how the
    # ecosystem works, and a pack with 300 mods overlaps thousands of times.
    # So it goes in its own bucket with the coverage that produced it, and the
    # renderer labels it as a lead to check when a crash names a mixin.
    OVERLAP_CAP = 20
    rows: list[dict] = []
    for (target, member), owners in member_owner.items():
        if len(owners) > 1:
            rows.append({"scope": "member", "target": target, "member": member,
                         "jars": sorted(owners)})
    overlapping_targets = {t for t, owners in target_owner.items() if len(owners) > 1}
    members_by_target = {(r["target"], r["member"]) for r in rows}
    for target in sorted(overlapping_targets):
        owners = target_owner[target]
        if any(t == target for t, _ in members_by_target):
            continue            # already listed at the finer granularity
        rows.append({"scope": "class", "target": target, "member": "",
                     "jars": sorted(owners)})
    rows.sort(key=lambda r: (r["scope"] != "member", -len(r["jars"]), r["target"]))
    rep.overlaps = rows[:OVERLAP_CAP]
    rep.mixin_coverage = {
        "jars_with_refmap": refmap_jars,
        "targets": len(target_owner),
        "members": len(member_owner),
        "overlapping_targets": len(overlapping_targets),
        "overlapping_members": sum(1 for o in member_owner.values() if len(o) > 1),
        "listed": len(rep.overlaps),
    }
    rep.loaders = dict(sorted(loaders.items(), key=lambda kv: -kv[1]))

    # --- duplicate mods: the same id declared by two different jars ---------
    for modid, entries in sorted(by_id.items()):
        files = {jar.name for jar, _ in entries}
        if len(files) > 1:
            versions = sorted({(m.version or "?") for _, m in entries})
            rep.findings.append(PackFinding(
                kind="pack.duplicate-mod",
                severity=Severity.WARNING,
                subject=modid,
                detail=f"declared by {len(files)} jars "
                       f"(versions: {', '.join(versions)}) -- the loader will "
                       f"load one of them and the choice is not obvious",
                evidence=sorted(files)))

    # --- mixed loaders ------------------------------------------------------
    if len(rep.loaders) > 1:
        rep.findings.append(PackFinding(
            kind="pack.mixed-loaders",
            severity=Severity.ERROR,
            subject=", ".join(rep.loaders),
            detail="jars for more than one loader are installed; a loader "
                   "ignores the other family's jars, so those mods are "
                   "installed but never load",
            evidence=[f"{k}: {v} jar(s)" for k, v in rep.loaders.items()]))

    # --- missing dependencies + version ranges ------------------------------
    for modid, entries in sorted(by_id.items()):
        for jar, m in entries:
            for dep in m.hard_requirements:
                if dep.modid in BUILTIN_IDS:
                    continue
                # A CLIENT/SERVER-scoped requirement only applies on that side,
                # and `--pack DIR` cannot tell which side the directory is for.
                # Claiming "missing" would be wrong on half the packs: measured
                # on a server pack, two of the last findings were exactly this
                # (connectedglass -> fusion, fancymenu -> melody, both
                # side="CLIENT"). Listed in NOT_CHECKED, not silently dropped.
                dep_side = (dep.side or "").strip().lower()
                if dep_side in ("client", "server") and dep_side != side:
                    continue
                target = by_id.get(dep.modid)
                if target is None and dep.modid in provided:
                    continue
                if target is None:
                    chain = _requirement_chain(by_id, dep.modid)
                    # Only printed when there is a second hop; a one-link chain
                    # would repeat the "required by" clause above.
                    via = ("; chain: " + " <- ".join([dep.modid] + chain)
                           if len(chain) > 1 else "")
                    rep.findings.append(PackFinding(
                        kind="pack.missing-dependency",
                        severity=Severity.ERROR,
                        subject=dep.modid,
                        detail=f"required by {modid} "
                               f"({m.version or 'no version'}) but no jar in "
                               f"mods/ declares it"
                               + (f"; range {dep.version_range}"
                                  if dep.version_range else "")
                               + via,
                        evidence=[jar.name]))
                    continue
                if not dep.version_range or len({j.name for j, _ in target}) > 1:
                    # duplicate jars already reported; comparing against an
                    # ambiguous version would just add noise
                    continue
                have = target[0][1].version
                ok = satisfies(have, dep.version_range)
                if ok is None:
                    rep.undecided.append({
                        "modid": dep.modid, "required_by": modid,
                        "range": dep.version_range,
                        "installed": have or "", "jar": target[0][0].name})
                elif not ok:
                    rep.findings.append(PackFinding(
                        kind="pack.version-mismatch",
                        severity=Severity.WARNING,
                        subject=dep.modid,
                        detail=f"{modid} requires {dep.version_range} but "
                               f"{have or 'an unversioned build'} is installed",
                        evidence=[jar.name, target[0][0].name]))

    # --- declared negatives, both sides installed --------------------------
    # A `breaks`/`incompatible` edge is version-scoped, and that is most of what
    # makes it useful: ae2wtlib declares extendedae incompatible with
    # `(,1.21-1.1.4-neoforge]`, i.e. only the old builds. Ignoring the range
    # turned every installed copy into a conflict -- 9 of them on a 355-jar pack
    # that boots fine ("Done (4.723s)!" in its own latest.log). So the range is
    # now the condition, exactly like a positive dependency, and an unreadable
    # range becomes `undecided` instead of a finding.
    for modid, entries in sorted(by_id.items()):
        for jar, m in entries:
            for dep in m.negatives:
                if dep.modid == modid or dep.modid not in by_id:
                    continue
                installed = by_id[dep.modid][0]
                have = installed[1].version
                rng = (dep.version_range or "").strip()
                if not rng or rng == "*":
                    hit = True                      # no range: incompatible with all
                else:
                    hit = satisfies(have, rng)
                if hit is None:
                    rep.undecided.append({
                        "modid": dep.modid, "required_by": modid, "range": rng,
                        "installed": have or "", "jar": jar.name,
                        "why": f"{dep.kind}: could not compare the declared range"})
                    continue
                if not hit:
                    continue
                note = ("the loader refuses to start" if dep.hard
                        else "the author reports they misbehave together")
                detail = (f"{modid} declares this pair {dep.kind} "
                          f"({'breaks' if dep.hard else 'conflicts'}): {note}")
                if rng:
                    detail += f"; the incompatibility covers {rng}"
                rep.findings.append(PackFinding(
                    kind="pack.declared-conflict",
                    severity=Severity.ERROR if dep.hard else Severity.WARNING,
                    subject=f"{modid} x {dep.modid}",
                    detail=detail,
                    evidence=[jar.name, installed[0].name]))

    rep.findings.sort(key=lambda f: (-int(f.severity), f.kind, f.subject))
    return rep
