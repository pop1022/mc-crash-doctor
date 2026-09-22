"""Parse Minecraft crash reports and server/client logs into ``CrashReport``.

Handles the variants that actually appear in the wild:

* Forge 1.13+ / NeoForge crash reports (``Mod List:`` as a ``|``-delimited table)
* Forge 1.12 and older (``Loaded coremods (and transformers):``)
* Fabric / Quilt reports (``Fabric Mods:`` two-space indented ``modid: Name ver``)
* Vanilla reports (no mod list)
* Plain server logs (no banner, no Mod List) -- best effort

Stack frames keep their provenance: the ``~[foo.jar%2312!/:1.0]`` marker, the
``pl:mixin:APP:bar.mixins.json:Class from mod (modid)`` markers. That is what
makes "which mod caused this" answerable.
"""

from __future__ import annotations

import re
from pathlib import Path

from .platform import (detect_launcher, detect_loader_version, detect_platform,
                       detect_software_version, detect_version)
from ..model import (
    CrashReport,
    ExceptionBlock,
    MemoryInfo,
    Mod,
    Section,
    StackFrame,
    SystemDetails,
)

# --- top-level structure ----------------------------------------------------
BANNER_RE = re.compile(r"^\s*-{2,}\s*Minecraft Crash Report\s*-{2,}\s*$", re.M | re.I)
JOKE_RE = re.compile(r"^\s*//\s*(.+?)\s*$", re.M)
TIME_RE = re.compile(r"^\s*Time:\s*(.+?)\s*$", re.M)
DESC_RE = re.compile(r"^\s*Description:\s*(.+?)\s*$", re.M)
SECTION_RE = re.compile(r"^\s*--\s*(.+?)\s*--\s*$", re.M)
SEP_RE = re.compile(r"^\s*-{15,}\s*$", re.M)

# --- exception chain --------------------------------------------------------
# A qualified name ending in Exception/Error/Throwable. The trailing part is
# optional *before* the keyword so that `java.lang.Error` itself matches: with a
# greedy `(\.\w+)+` prefix the regex backtracks to `.lang` and then cannot match
# `.Error` because the dot is not in the keyword alternation.
EXC_CLASS = r"(?:[\w$]+\.)+[\w$]*(?:Exception|Error|Throwable)"
EXC_RE = re.compile(
    r"^\s*(" + EXC_CLASS + r")\s*:?\s*(.*)$"
)
CAUSED_BY_RE = re.compile(r"^\s*Caused by:\s*(.+?)\s*$")
FRAME_RE = re.compile(r"^\s*at\s+(.+?)\s*$")
MORE_RE = re.compile(r"^\s*\.\.\.\s*(\d+)\s+(?:more|common frames omitted)", re.I)
# Log-file FATAL marker: "[17:43:53] [Render thread/FATAL]: Unreported
# exception thrown!" -- the exception header on the NEXT line is the crash.
LOG_FATAL_RE = re.compile(r"^\[[\d:.]+\]\s*\[[^\]]*/FATAL\]", re.I)

# frame internals
JAR_RE = re.compile(r"~\[([^\]]+?)\]")
JAR_NAME_RE = re.compile(r"([^/%\\]+?)\.jar")
JAR_VER_RE = re.compile(r"!/?:?([\w.\-+]*)\]?$")
MIXIN_APP_RE = re.compile(r"pl:mixin:APP:([\w.\-]+?)\.mixins\.json:([\w.$]+)")
FROM_MOD_RE = re.compile(r"from mod \(([^)]*)\)")
CL_MARKER_RE = re.compile(r"\{([^}]*)\}")
LOC_RE = re.compile(r"([\w.$]+(?:\.[\w$<>]+)*)\.([\w$<>]+)\(([\w.]*(?:java|kt|scala))?:?(\d+)?\)")

# --- system details ---------------------------------------------------------
DETAIL_RE = re.compile(r"^\s*([\w \-/().]+?):\s*(.*)$")
MEMORY_RE = re.compile(
    r"([\d,]+)\s*bytes\s*\(([\d,]+)\s*([KMG]i?B)\)\s*/\s*"
    r"([\d,]+)\s*bytes\s*\(([\d,]+)\s*([KMG]i?B)\)\s*up to\s*"
    r"([\d,]+)\s*bytes\s*\(([\d,]+)\s*([KMG]i?B)\)",
    re.I,
)
MEM_SHORT_RE = re.compile(
    r"([\d,]+)\s*(?:MiB|MB)\s*/\s*([\d,]+)\s*(?:MiB|MB)\s*up to\s*([\d,]+)\s*(?:MiB|MB)",
    re.I,
)
JVM_FLAGS_RE = re.compile(r"^\s*JVM Flags:\s*(\d+)\s*total;\s*(.*)$")
JVM_FLAGS_BARE_RE = re.compile(r"^\s*JVM Flags:\s*(.*)$")
XMX_RE = re.compile(r"-Xmx\s*(\d+)([KMGkmg])\b")
XMS_RE = re.compile(r"-Xms\s*(\d+)([KMGkmg])\b")
METASPACE_RE = re.compile(r"-XX:MaxMetaspaceSize\s*=\s*(\d+)([KMGkmg])\b")
MC_VER_RE = re.compile(r"^\s*(?:Minecraft Version|Modpack Version):\s*(.+?)\s*$", re.M)
JAVA_VER_RE = re.compile(r"^\s*Java Version:\s*(.+?)\s*$", re.M)
JVM_NAME_RE = re.compile(r"^\s*Java VM Version:\s*(.+?)\s*$", re.M)
OS_RE = re.compile(r"^\s*Operating System:\s*(.+?)\s*$", re.M)
CPU_RE = re.compile(r"^\s*CPUs:\s*(\d+)", re.M)
MODLAUNCHER_RE = re.compile(r"^\s*Mod Launcher:\s*(.+?)\s*$", re.M)
CRASH_UUID_RE = re.compile(r"^\s*Crash Report UUID:\s*(.+?)\s*$", re.M)
SERVER_RUNNING_RE = re.compile(r"^\s*Server Running:\s*(\w+)", re.M)
PLAYER_COUNT_RE = re.compile(r"^\s*Player Count:\s*(\d+)", re.M)
MODS_COUNT_RE = re.compile(r"^\s*Mods?:\s*(\d+)", re.M)

_UNIT = {"b": 1, "kib": 1024, "kb": 1000, "mib": 1024**2, "mb": 1000**2,
         "gib": 1024**3, "gb": 1000**3}


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def _unit_to_bytes(n: int, unit: str) -> int:
    return n * _UNIT.get(unit.lower(), 1)


def _mib_from_flag(num: int, suffix: str) -> int:
    s = suffix.lower()
    if s == "k":
        return num // 1024
    if s == "g":
        return num * 1024
    return num  # already MiB


# --- mod lists --------------------------------------------------------------
FORGE_MODLIST_HEADER_RE = re.compile(r"^\s*Mods?\s*:\s*\d+\s*$|^\s*Mod List:\s*$", re.M)
# Forge 1.13+: jar | name | modid | version | status | manifest
FORGE_ROW_RE = re.compile(
    r"^\s*([^\t|]+?)\s*\|\s*([^\t|]*?)\s*\|\s*([^\t|]*?)\s*\|\s*"
    r"([^\t|]*?)\s*\|\s*([^\t|]*?)\s*\|\s*(.*?)\s*$"
)
FABRIC_MODLIST_HEADER_RE = re.compile(r"^\s*(Fabric|Quilt) Mods:\s*$", re.M)
# Fabric: two-space indent, "modid: Display Name 1.2.3"
FABRIC_ROW_RE = re.compile(r"^\s{2}([\w.\-]+):\s*(.+?)\s*$")
COREMOD_HEADER_RE = re.compile(
    r"^\s*Loaded coremods \(and transformers\):\s*$|^\s*coremods are present:\s*$", re.M
)


def _parse_forge_modlist(text: str, start: int) -> tuple[list[Mod], int]:
    """Parse ``|``-delimited Forge/NeoForge rows from ``start``."""
    mods: list[Mod] = []
    lines = text[start:].splitlines()
    for off, ln in enumerate(lines[1:], start=1):
        if not ln.strip():
            continue
        # stop at the next section header or a non-table line
        if SECTION_RE.match(ln) or SEP_RE.match(ln):
            return mods, start + off
        m = FORGE_ROW_RE.match(ln)
        if not m:
            # tolerate a trailing non-table line
            if mods and not ln.lstrip().startswith("|"):
                # some reports end the table abruptly
                if not any(c in ln for c in "|"):
                    return mods, start + off
            continue
        f, name, modid, ver, status, manifest = (x.strip() for x in m.groups())
        mods.append(Mod(file=f, name=name, modid=modid, version=ver,
                        status=status, manifest=manifest))
    return mods, len(text)


def _parse_fabric_modlist(text: str, start: int) -> tuple[list[Mod], int]:
    mods: list[Mod] = []
    lines = text[start:].splitlines()
    parent = ""
    for off, ln in enumerate(lines[1:], start=1):
        if not ln.strip():
            continue
        if SECTION_RE.match(ln) or SEP_RE.match(ln):
            return mods, start + off
        indent = len(ln) - len(ln.lstrip(" "))
        m = FABRIC_ROW_RE.match(ln)
        if not m:
            if mods and indent < 2:
                return mods, start + off
            continue
        modid, rest = m.group(1).strip(), m.group(2).strip()
        # Fabric nests children under a deeper indent
        if indent >= 4 and mods:
            parent = mods[-1].modid
        else:
            parent = ""
        # split trailing version: "Fabric API 0.92.0+1.20.1"
        vm = re.match(r"^(.*?)\s+([\w.\-+]+)$", rest)
        name, ver = (vm.group(1), vm.group(2)) if vm else (rest, "")
        mods.append(Mod(file="", name=name, modid=modid, version=ver,
                        status="", manifest="", parent=parent))
    return mods, len(text)


def _parse_coremods(text: str, start: int) -> tuple[list[str], int]:
    out: list[str] = []
    lines = text[start:].splitlines()
    for off, ln in enumerate(lines[1:], start=1):
        s = ln.strip()
        if not s:
            continue
        if SECTION_RE.match(ln) or SEP_RE.match(ln):
            return out, start + off
        if s.startswith("at ") or ":" in s[:12]:
            continue
        out.append(s)
        if len(out) > 200:
            break
    return out, len(text)


# --- frames -----------------------------------------------------------------
def _parse_frame(raw: str, index: int) -> StackFrame:
    f = StackFrame(raw=raw, index=index)
    if "(Native Method)" in raw:
        f.is_native = True

    jars = JAR_RE.findall(raw)
    if jars:
        f.jar = jars[0]
        nm = JAR_NAME_RE.search(jars[0])
        if nm:
            f.jar = nm.group(0)
        vm = JAR_VER_RE.search(jars[0])
        if vm and vm.group(1):
            f.jar_version = vm.group(1)

    mx = MIXIN_APP_RE.search(raw)
    if mx:
        f.mixin_config, f.mixin_class = mx.group(1), mx.group(2)
    fm = FROM_MOD_RE.search(raw)
    if fm and fm.group(1) != "unknown":
        f.mixin_owner_mod = fm.group(1)
    cl = CL_MARKER_RE.search(raw)
    if cl:
        f.transformers = [t.strip() for t in cl.group(1).split(",") if t.strip()]

    # class / method / line
    head = raw.split("~[", 1)[0].strip()
    head = re.sub(r"\s*\{.*\}\s*$", "", head).strip()
    m = re.match(r"^(.*?)(?:\.([\w$<>]+))?\(([^)]*)\)\s*$", head)
    if m:
        cls, meth, arg = m.group(1), m.group(2), m.group(3)
        f.cls = cls or ""
        f.method = meth or ""
        lm = re.search(r":(\d+)\s*$", arg or "")
        if lm:
            f.line_no = int(lm.group(1))
    else:
        f.cls = head

    fq = f.cls or f.method
    if fq.startswith("net.minecraft"):
        f.is_minecraft = True
    elif fq.startswith(("net.minecraftforge", "net.neoforged", "cpw.mods")):
        f.is_forge = True
    return f


# --- exceptions -------------------------------------------------------------
def _split_exception_header(line: str) -> tuple[str, str]:
    m = EXC_RE.match(line.strip())
    if m:
        return m.group(1).strip(), (m.group(2) or "").strip()
    # "Caused by: something weird" -- fall back to splitting on ': '
    if ":" in line:
        kind, _, msg = line.strip().partition(":")
        return kind.strip(), msg.strip()
    return line.strip(), ""


def _parse_exceptions(text: str) -> list[ExceptionBlock]:
    """Extract exception chains from the report/log body.

    Crash reports carry ONE chain (before `-- System Details --`). Log files
    carry a whole TIMELINE of exceptions at different levels; the one that
    matters is introduced by a `/FATAL]` line ("Unreported exception
    thrown!"). Both shapes are parsed here: every top-level exception header
    starts a new depth-0 block, `Caused by:` nests under it, and FATAL-
    introduced blocks are flagged so `root_cause` can prefer them.
    """
    blocks: list[ExceptionBlock] = []
    current: ExceptionBlock | None = None
    depth = 0
    frame_idx = 0
    fatal_pending = False

    # For crash reports only scan the region before "-- System Details --" /
    # "-- Crash Report --" (later sections repeat the same trace). Log files
    # have no such markers, so cut stays len(text).
    cut = len(text)
    for marker in ("-- System Details --", "-- Crash Report --"):
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    region = text[:cut]

    for raw_line in region.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # log-level FATAL marker -> the NEXT exception header is the crash
        if LOG_FATAL_RE.match(line):
            fatal_pending = True
            continue
        cb = CAUSED_BY_RE.match(line)
        if cb:
            if current:
                blocks.append(current)
            kind, msg = _split_exception_header(cb.group(1))
            depth += 1
            frame_idx = 0
            current = ExceptionBlock(kind=kind, message=msg,
                                     is_caused_by=True, depth=depth)
            continue
        em = EXC_RE.match(line.strip())
        if em and (current is None or current.frames):
            # start of a (new) top-level exception: close the previous block
            if current is not None:
                blocks.append(current)
            kind, msg = em.group(1).strip(), (em.group(2) or "").strip()
            current = ExceptionBlock(kind=kind, message=msg,
                                     is_caused_by=False, depth=0,
                                     fatal=fatal_pending)
            fatal_pending = False
            depth = 0
            frame_idx = 0
            continue
        fm = FRAME_RE.match(line)
        if fm and current is not None:
            inner = fm.group(1)
            if MORE_RE.match(inner):
                continue
            current.frames.append(_parse_frame(inner, frame_idx))
            frame_idx += 1
            continue
        if current is not None and current.frames:
            # end of the trace region
            if SECTION_RE.match(line) or SEP_RE.match(line):
                break

    if current:
        blocks.append(current)
    # de-duplicate identical consecutive blocks (reports repeat the head trace)
    out: list[ExceptionBlock] = []
    for b in blocks:
        if out and out[-1].signature == b.signature and out[-1].is_caused_by == b.is_caused_by \
                and len(out[-1].frames) and len(b.frames) and \
                out[-1].frames[0].raw == b.frames[0].raw:
            if len(b.frames) > len(out[-1].frames):
                out[-1] = b
            continue
        out.append(b)
    return out


# --- sections ---------------------------------------------------------------
def _parse_sections(text: str) -> list[Section]:
    marks = [(m.start(), m.group(1).strip()) for m in SECTION_RE.finditer(text)]
    out: list[Section] = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        chunk = text[pos:end]
        # drop the header line and the dotted separator
        lines = chunk.splitlines()[1:]
        if lines and SEP_RE.match(lines[0]):
            lines = lines[1:]
        details: dict[str, str] = {}
        for ln in lines:
            if SECTION_RE.match(ln) or SEP_RE.match(ln) or ln.startswith("\t\t"):
                continue
            m = DETAIL_RE.match(ln)
            if m:
                k = m.group(1).strip()
                if len(k) <= 40 and k not in details:
                    details[k] = m.group(2).strip()
        out.append(Section(name=name, body="\n".join(lines).strip(),
                           details=details))
    return out


# --- system details ---------------------------------------------------------
def _parse_system(text: str, sections: list[Section], mods: list[Mod]) -> SystemDetails:
    sys_sec = next((s for s in sections
                    if s.name.lower().startswith("system details")), None)
    src = sys_sec.body if sys_sec else text
    d = SystemDetails()
    if sys_sec:
        d.raw = dict(sys_sec.details)

    def _g(pattern: re.Pattern[str], default: str = "") -> str:
        m = pattern.search(src) or pattern.search(text)
        return m.group(1).strip() if m else default

    # Platform detection runs FIRST: detect_version needs the loader to pick
    # loader-specific patterns (and to reverse-derive the MC version from a
    # NeoForge build number).
    d.loader, d.platform_evidence = detect_platform(text)
    d.loader_version = detect_loader_version(text, d.loader)
    d.launcher, _ = detect_launcher(text)

    d.minecraft_version = _g(MC_VER_RE)
    if not d.minecraft_version:
        # logs (no System Details block) need the fingerprint-driven detector
        d.minecraft_version = detect_version(text, d.loader)
    jv = _g(JAVA_VER_RE)
    d.java_version = jv
    m = re.search(r'\b(\d+)(?:\.(\d+))?', jv)
    if m:
        major = int(m.group(1))
        d.java_major = (int(m.group(2)) if major == 1 and m.group(2) else major)
    d.jvm_name = _g(JVM_NAME_RE)
    d.os_name = _g(OS_RE)
    am = re.search(r"\((\w+)\)", d.os_name)
    if am:
        d.os_arch = am.group(1)
    cm = CPU_RE.search(src) or CPU_RE.search(text)
    if cm:
        d.cpus = int(cm.group(1))
    um = CRASH_UUID_RE.search(src) or CRASH_UUID_RE.search(text)
    if um:
        d.crash_uuid = um.group(1).strip()
    sm = SERVER_RUNNING_RE.search(src) or SERVER_RUNNING_RE.search(text)
    if sm:
        d.server_running = sm.group(1).lower() == "true"
    pm = PLAYER_COUNT_RE.search(src) or PLAYER_COUNT_RE.search(text)
    if pm:
        d.player_count = int(pm.group(1))
    mm = MODS_COUNT_RE.search(src) or MODS_COUNT_RE.search(text)
    if mm:
        d.mod_count = int(mm.group(1))
    elif mods:
        d.mod_count = len(mods)

    # memory triple
    mem = MEMORY_RE.search(src) or MEMORY_RE.search(text)
    if mem:
        g = mem.groups()
        d.memory = MemoryInfo(
            used_bytes=_to_int(g[0]), current_bytes=_to_int(g[3]),
            max_bytes=_to_int(g[6]),
            used_mib=_to_int(g[1]) * _UNIT.get(g[2].lower(), 1) // (1024**2),
            current_mib=_to_int(g[4]) * _UNIT.get(g[5].lower(), 1) // (1024**2),
            max_mib=_to_int(g[7]) * _UNIT.get(g[8].lower(), 1) // (1024**2),
        )
    else:
        ms = MEM_SHORT_RE.search(src) or MEM_SHORT_RE.search(text)
        if ms:
            u, c, mx = (_to_int(x) for x in ms.groups())
            d.memory = MemoryInfo(used_mib=u, current_mib=c, max_mib=mx)

    # jvm flags
    jf = JVM_FLAGS_RE.search(src) or JVM_FLAGS_RE.search(text)
    if jf:
        d.jvm_flags_count = int(jf.group(1))
        flags = jf.group(2)
    else:
        jb = JVM_FLAGS_BARE_RE.search(src) or JVM_FLAGS_BARE_RE.search(text)
        flags = jb.group(1) if jb else ""
    if flags:
        d.jvm_flags = [f for f in re.split(r"\s{2,}|(?=-)", flags.strip()) if f.strip()]
    else:
        d.jvm_flags = []
    mx = XMX_RE.search(flags) or XMX_RE.search(src)
    if mx:
        d.xmx_mib = _mib_from_flag(int(mx.group(1)), mx.group(2))
    xm = XMS_RE.search(flags) or XMS_RE.search(src)
    if xm:
        d.xms_mib = _mib_from_flag(int(xm.group(1)), xm.group(2))
    msz = METASPACE_RE.search(flags) or METASPACE_RE.search(src)
    if msz:
        d.max_metaspace_mib = _mib_from_flag(int(msz.group(1)), msz.group(2))
    if d.xmx_mib is None and d.memory.max_mib:
        d.xmx_mib = d.memory.max_mib

    # loader / platform detection happened above (version detection needs it)
    d.software_version = detect_software_version(text, d.loader, d.launcher)

    return d


# --- entry point ------------------------------------------------------------
# `Suspected Mods:` -- the game's own attribution line. Two shapes seen in the
# wild (harvested 2026-09):
#   Forge/Fabric crash reports, System Details section:
#     "\tSuspected Mods: Fabric Registry Sync (v0) (fabric-registry-sync-v0), ..."
#   bare server logs:
#     "[12:34:56] [Server thread/ERROR]: Suspected Mods: NONE"
# The mod id is the last parenthesised token of each comma-separated entry.
SUSPECTED_MODS_RE = re.compile(r"Suspected Mods:\s*(.+)")


def _parse_suspected_mods(text: str) -> list[str]:
    """Extract mod ids from the game's `Suspected Mods:` line."""
    m = SUSPECTED_MODS_RE.search(text)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw or raw.upper() == "NONE":
        return []
    out: list[str] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # "Fabric Registry Sync (v0) (fabric-registry-sync-v0)" -> id in the
        # LAST parens; a plain "mekanism" entry has no parens at all.
        pm = re.findall(r"\(([^()]+)\)", entry)
        mid = pm[-1].strip() if pm else entry
        mid = mid.strip().lower()
        # skip display-name leftovers that are not mod ids
        if mid and mid not in out and re.fullmatch(r"[\w\-]+", mid):
            out.append(mid)
    return out


def parse_text(text: str, *, source_path: str = "") -> CrashReport:
    """Parse crash-report or log text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    rep = CrashReport(source_path=source_path, full_text=text)

    banner = BANNER_RE.search(text)
    if banner:
        rep.kind = "crash-report"
        rep.banner = banner.group(0).strip()
        head = text[banner.end():banner.end() + 400]
        j = JOKE_RE.search(head)
        if j:
            rep.joke = j.group(1).strip()
    elif re.search(r"^\[\d{2}:\d{2}:\d{2}\]", text, re.M):
        rep.kind = "log"
    else:
        rep.kind = "unknown"

    tm = TIME_RE.search(text)
    if tm:
        rep.time = tm.group(1).strip()
    dm = DESC_RE.search(text)
    if dm:
        rep.description = dm.group(1).strip()

    rep.sections = _parse_sections(text)
    rep.exceptions = _parse_exceptions(text)

    # coremods
    cm = COREMOD_HEADER_RE.search(text)
    if cm:
        rep.coremods, _ = _parse_coremods(text, cm.start())

    # mod list -- try Forge table first, then Fabric
    mods: list[Mod] = []
    fm = FORGE_MODLIST_HEADER_RE.search(text)
    if fm:
        mods, _ = _parse_forge_modlist(text, fm.start())
    if not mods:
        fb = FABRIC_MODLIST_HEADER_RE.search(text)
        if fb:
            mods, _ = _parse_fabric_modlist(text, fb.start())
    rep.mods = mods
    rep.suspected_mods = _parse_suspected_mods(text)

    rep.system = _parse_system(text, rep.sections, mods)

    # side
    if rep.system.loader in ("forge", "neoforge"):
        head = text[:6000].lower()
        rep.system.is_server = ("server thread" in head or "dedicatedserver" in head
                                or rep.kind == "log" and "for help" in head)
        rep.system.is_client = ("client thread" in head or "render thread" in head
                                or "--username" in head)
    if rep.description and not rep.system.is_server:
        rep.system.is_server = rep.description in (
            "Watching Server", "Exception in server tick loop")

    return rep


def parse_file(path: str | Path) -> CrashReport:
    p = Path(path)
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return parse_text(raw.decode(enc), source_path=str(p))
        except UnicodeDecodeError:
            continue
    return parse_text(raw.decode("utf-8", errors="replace"), source_path=str(p))
