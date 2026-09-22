"""Structured model of a Minecraft crash report / log.

Everything downstream (rules, triage, rendering) consumes these dataclasses,
never raw text. Keep them JSON-serialisable so `--json` output is free.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    """Diagnostic severity, ordered so `max()` works."""

    INFO = 0
    HINT = 1
    WARNING = 2
    ERROR = 3
    FATAL = 4


@dataclass
class Mod:
    """One entry from the report's Mod List / Fabric Mods block."""

    file: str = ""          # jar filename as listed
    name: str = ""          # human display name
    modid: str = ""
    version: str = ""
    status: str = ""        # DONE / ERROR / ... (Forge)
    manifest: str = ""      # NOSIGNATURE / <sha> (Forge)
    parent: str = ""        # Fabric: the mod it is nested under, if any

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StackFrame:
    """A single `at ...` line, with whatever provenance it carries."""

    raw: str
    index: int = 0                  # position in the chain top-down (0 = top)
    cls: str = ""                   # fully qualified class
    method: str = ""
    line_no: int | None = None
    jar: str = ""                   # from ~[foo.jar%2312!/:ver]
    jar_version: str = ""
    mixin_config: str = ""          # from pl:mixin:APP:foo.mixins.json
    mixin_class: str = ""
    mixin_owner_mod: str = ""       # from "from mod (modid)"
    transformers: list[str] = field(default_factory=list)  # re:/pl: markers
    is_native: bool = False
    is_minecraft: bool = False
    is_forge: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExceptionBlock:
    """One link of the exception chain (top-level or a `Caused by:`)."""

    kind: str = ""                  # java.lang.OutOfMemoryError
    message: str = ""               # "Java heap space"
    frames: list[StackFrame] = field(default_factory=list)
    is_caused_by: bool = False
    depth: int = 0                  # 0 = outermost, 1 = first Caused by, ...
    # True when the block was introduced by a FATAL-level log line
    # ("[Render thread/FATAL]: Unreported exception thrown!"). Log files carry
    # a whole timeline of exceptions; the FATAL one is the actual crash, so
    # root_cause prefers it over earlier WARN/INFO noise.
    fatal: bool = False

    @property
    def signature(self) -> str:
        """Stable grouping key: exception class + first message token."""
        msg = (self.message or "").split("\n", 1)[0].strip()
        return f"{self.kind}: {msg[:80]}".strip(": ")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signature"] = self.signature
        return d


@dataclass
class Section:
    """A `-- Name --` block with its key/values and free text."""

    name: str = ""
    body: str = ""
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemoryInfo:
    """The `Memory: used / current up to max` triple, in MiB."""

    used_bytes: int | None = None
    current_bytes: int | None = None
    max_bytes: int | None = None
    used_mib: int | None = None
    current_mib: int | None = None
    max_mib: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.max_mib is not None and self.used_mib is not None

    def utilisation(self) -> float | None:
        """used / max as a 0..1 ratio, or None."""
        if self.used_mib and self.max_mib:
            return self.used_mib / self.max_mib
        return None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SystemDetails:
    """The `-- System Details --` block, normalised."""

    raw: dict[str, str] = field(default_factory=dict)
    minecraft_version: str = ""
    loader: str = ""                # forge | neoforge | fabric | quilt | vanilla | ...
    loader_version: str = ""
    platform_evidence: str = ""     # which fingerprint matched (debuggability)
    launcher: str = ""              # prism-launcher | multimc | ... (orthogonal axis)
    software_version: str = ""      # version of the platform software itself
                                    # (bedrock/pocketmine/geyser use this, not MC's)
    java_version: str = ""
    java_major: int | None = None
    jvm_name: str = ""
    jvm_flags_count: int | None = None
    jvm_flags: list[str] = field(default_factory=list)
    xms_mib: int | None = None
    xmx_mib: int | None = None
    max_metaspace_mib: int | None = None
    os_name: str = ""
    os_arch: str = ""
    cpus: int | None = None
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    mod_count: int | None = None
    player_count: int | None = None
    server_running: bool | None = None
    crash_uuid: str = ""
    # side hints
    is_server: bool | None = None
    is_client: bool | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["memory"] = self.memory.to_dict()
        return d


@dataclass
class CrashReport:
    """Fully parsed report/log."""

    source_path: str = ""
    kind: str = ""                  # crash-report | server-log | client-log | unknown
    banner: str = ""
    joke: str = ""                  # "// I blame Dinnerbone."
    time: str = ""
    description: str = ""
    exceptions: list[ExceptionBlock] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    system: SystemDetails = field(default_factory=SystemDetails)
    mods: list[Mod] = field(default_factory=list)
    coremods: list[str] = field(default_factory=list)
    # Vanilla/Fabric's OWN diagnosis: the `Suspected Mods:` line in the report
    # header (System Details on Forge, a bare log line on Fabric). The game
    # computes this from the crash-time classloader context, so it is stronger
    # evidence than anything we can infer. Empty when the line is absent or
    # reads `NONE`.
    suspected_mods: list[str] = field(default_factory=list)
    full_text: str = ""

    # --- convenience views -------------------------------------------------
    @property
    def root_cause(self) -> ExceptionBlock | None:
        """The exception that actually killed the process.

        Preference order:
        1. the last FATAL-marked chain (log files contain a timeline of
           exceptions; `Unreported exception thrown!` / `/FATAL]` marks the
           crash -- anything before it is noise, e.g. a WARN-level
           NumberFormatException from a config read);
        2. else the deepest `Caused by:` of the parsed chain;
        3. else the outermost exception.
        """
        fatal_idx = [i for i, b in enumerate(self.exceptions) if b.fatal]
        if fatal_idx:
            i = fatal_idx[-1]
            chain = [self.exceptions[i]]
            j = i + 1
            while j < len(self.exceptions) and self.exceptions[j].is_caused_by:
                chain.append(self.exceptions[j])
                j += 1
            return max(chain, key=lambda b: b.depth)
        caused = [e for e in self.exceptions if e.is_caused_by]
        if caused:
            return max(caused, key=lambda e: e.depth)
        return self.exceptions[0] if self.exceptions else None

    @property
    def all_frames(self) -> list[StackFrame]:
        out: list[StackFrame] = []
        for e in self.exceptions:
            out.extend(e.frames)
        return out

    def section(self, name: str) -> Section | None:
        name_l = name.strip().lower()
        for s in self.sections:
            if s.name.strip().lower() == name_l:
                return s
        return None

    def find_section(self, *names: str) -> Section | None:
        for n in names:
            s = self.section(n)
            if s:
                return s
        return None

    def mod_by_id(self, modid: str) -> Mod | None:
        modid_l = modid.strip().lower()
        for m in self.mods:
            if m.modid.lower() == modid_l:
                return m
        return None

    def to_dict(self, *, include_text: bool = False) -> dict:
        d = {
            "source_path": self.source_path,
            "kind": self.kind,
            "banner": self.banner,
            "time": self.time,
            "description": self.description,
            "exceptions": [e.to_dict() for e in self.exceptions],
            "sections": [s.to_dict() for s in self.sections],
            "system": self.system.to_dict(),
            "mods": [m.to_dict() for m in self.mods],
            "coremods": self.coremods,
            "suspected_mods": self.suspected_mods,
            "mod_count_parsed": len(self.mods),
            "root_cause": (self.root_cause or ExceptionBlock()).to_dict(),
        }
        if include_text:
            d["full_text"] = self.full_text
        return d

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(**kw), ensure_ascii=False, indent=2)


@dataclass
class Finding:
    """One diagnostic produced by a rule."""

    rule_id: str
    title: str
    severity: Severity = Severity.ERROR
    summary: str = ""
    explanation: str = ""
    evidence: list[str] = field(default_factory=list)   # quoted lines / refs
    fixes: list[str] = field(default_factory=list)      # actionable steps
    suspects: list[str] = field(default_factory=list)   # mod ids or jar names
    confidence: float = 0.0                             # 0..1
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)       # doc/issue links

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.name.lower()
        return d
