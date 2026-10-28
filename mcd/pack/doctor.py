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

WHAT IS NOT CHECKED (deliberate, listed so callers do not over-trust)
  * client-only mod on a server -- the manifest reader does not capture Fabric's
    `environment` field yet, so the tool cannot see it. ROADMAP 2.2 lists it as
    a required finding; it is reported as NOT CHECKED rather than guessed.
  * nested jars (`META-INF/jars/*.jar`, Fabric's bundled libraries).
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
        raise FileNotFoundError(
            f"no `mods/` directory with .jar files under {base}")

    rep = PackReport(root=str(base), mods_dir=str(mods),
                     context=_pack_context(base), side=side)

    by_id: dict[str, list[tuple[Path, ModManifest]]] = defaultdict(list)
    provided: dict[str, str] = {}          # provided id -> who provides it
    loaders: dict[str, int] = defaultdict(int)
    jars = sorted(mods.glob("*.jar"))
    rep.jars = len(jars)

    for jar in jars:
        try:
            manifests = parse_jar(jar)
        except ManifestError as exc:
            rep.unreadable.append({"jar": jar.name, "reason": str(exc)})
            continue
        # A jar can declare nothing at the top level and still provide mods:
        # JarJar/Fabric bundle them under META-INF/jarjar|jars. Reading only the
        # ids is enough to stop claiming a dependency is missing when it is
        # sitting inside another mod's jar (measured: 4 findings on a pack that
        # boots). The bundle's own dependencies are still not checked.
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
                    rep.findings.append(PackFinding(
                        kind="pack.missing-dependency",
                        severity=Severity.ERROR,
                        subject=dep.modid,
                        detail=f"required by {modid} "
                               f"({m.version or 'no version'}) but no jar in "
                               f"mods/ declares it"
                               + (f"; range {dep.version_range}"
                                  if dep.version_range else ""),
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
