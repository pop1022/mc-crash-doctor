"""Rendering backends: terminal (rich), plain text, JSON, Markdown."""

from __future__ import annotations

import json
import unicodedata
from typing import IO

from ..model import CrashReport, Finding, Severity
from ..textfmt import md_cell

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False

SEV_COLOR = {
    Severity.FATAL: "bold red",
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.HINT: "cyan",
    Severity.INFO: "dim",
}
SEV_LABEL = {
    Severity.FATAL: "FATAL",
    Severity.ERROR: "ERROR",
    Severity.WARNING: "WARN",
    Severity.HINT: "HINT",
    Severity.INFO: "INFO",
}


# --------------------------------------------------------------------------
# summary block shared by all formats
# --------------------------------------------------------------------------
_cell = md_cell      # local alias; the implementation lives in mcd.textfmt


def build_summary(rep: CrashReport) -> dict:
    sysd = rep.system
    rc = rep.root_cause
    mem = sysd.memory
    return {
        "kind": rep.kind,
        "time": rep.time,
        "description": rep.description,
        "loader": sysd.loader,
        "loader_version": sysd.loader_version,
        "launcher": sysd.launcher,
        "minecraft_version": sysd.minecraft_version,
        "java_version": sysd.java_version,
        "java_major": sysd.java_major,
        "os": sysd.os_name,
        "cpus": sysd.cpus,
        "heap_used_mib": mem.used_mib,
        "heap_current_mib": mem.current_mib,
        "heap_max_mib": mem.max_mib,
        "xms_mib": sysd.xms_mib,
        "xmx_mib": sysd.xmx_mib,
        "max_metaspace_mib": sysd.max_metaspace_mib,
        "mod_count": sysd.mod_count or len(rep.mods),
        "mods_parsed": len(rep.mods),
        "coremods": len(rep.coremods),
        # headline, not signature: the signature is an 80-character grouping key
        # and printing it cut words in half ("seconds (shoul"). Every consumer
        # of the summary -- terminal, markdown, JSON, the web card -- wanted the
        # readable first line.
        "root_cause": rc.headline if rc else None,
        "exception_chain": [e.signature for e in rep.exceptions],
        "is_server": sysd.is_server,
        "is_client": sysd.is_client,
    }


def _fmt_platform(s: dict, *, via: str = " (via {})") -> str:
    """`loader version`, with the launcher appended in the caller's notation.

    All three renderers print this, and they used to build it by hand -- which
    is how "None" ends up in a report when a log has no loader line.
    """
    out = " ".join(p for p in (s["loader"], s["loader_version"]) if p)
    if s["launcher"]:
        out += via.format(s["launcher"])
    return out


def _fmt_heap(s: dict) -> str:
    if s["heap_max_mib"]:
        pct = ""
        if s["heap_used_mib"] and s["heap_max_mib"]:
            pct = f" ({s['heap_used_mib'] * 100 // s['heap_max_mib']}% used)"
        return f"{s['heap_used_mib']}/{s['heap_max_mib']} MiB{pct}"
    return "unknown"


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------
# Bump when the Incident document shape changes in a way consumers must know
# about. Additive optional fields = minor (no bump needed for the const here
# unless we want to advertise it); removed/renamed/retyped fields = major.
SCHEMA_VERSION = "1.0"


def build_incident(rep: CrashReport, findings: list[Finding], triage) -> dict:
    """The canonical Incident document.

    Single source of truth for the JSON shape: the CLI (`render_json`), the
    browser app (`web/app.js` warm-up), and any future API all emit exactly
    this. Validated by `tests/test_schema.py` against
    `data/schemas/incident.v1.json`. Do not build the doc inline elsewhere --
    that is how the CLI and web app silently drift apart.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": rep.source_path,
        "summary": build_summary(rep),
        "findings": [f.to_dict() for f in findings],
        "triage": triage.to_dict() if triage else None,
    }


def render_json(rep: CrashReport, findings: list[Finding], triage,
                out: IO[str]) -> None:
    json.dump(build_incident(rep, findings, triage), out,
              ensure_ascii=False, indent=2)
    out.write("\n")


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def render_markdown(rep: CrashReport, findings: list[Finding], triage,
                    out: IO[str]) -> None:
    s = build_summary(rep)
    w = out.write
    w("# Minecraft crash diagnosis\n\n")
    w(f"*Source:* `{_basename(rep.source_path)}`\n\n")

    w("## Environment\n\n")
    w("| | |\n|---|---|\n")
    w(f"| Platform | {_cell(_fmt_platform(s))} |\n")
    w(f"| Minecraft | {_cell(s['minecraft_version'] or '?')} |\n")
    w(f"| Java | {_cell(s['java_version'] or '?')} (major {_cell(s['java_major'])}) |\n")
    w(f"| Heap | {_cell(_fmt_heap(s))} |\n")
    w(f"| Mods | {_cell(s['mods_parsed'] or s['mod_count'] or '?')} |\n")
    w(f"| OS | {_cell(s['os'] or '?')} |\n")
    if s["root_cause"]:
        w(f"| Root cause | {_md_code(s['root_cause'])} |\n")
    w("\n")

    if triage and triage.suspects:
        w("## Suspect mods\n\n")
        w("| Mod | Version | Confidence | Why |\n|---|---|---|---|\n")
        for sp in triage.suspects:
            why = sp.reasons[0] if sp.reasons else ""
            w(f"| `{_cell(sp.modid)}` | {_cell(sp.version or '-')} | "
              f"{sp.confidence:.0%} | {_cell(why)} |\n")
        for note in triage.notes:
            w(f"\n> {note}\n")
        w("\n")

    if findings:
        w("## Findings\n\n")
        for i, f in enumerate(findings, 1):
            w(f"### {i}. [{SEV_LABEL[f.severity]}] {f.title}\n\n")
            w(f"*rule `{f.rule_id}` · confidence {f.confidence:.0%}*\n\n")
            if f.explanation:
                w(f"{f.explanation}\n\n")
            if f.evidence:
                w("**Evidence**\n\n")
                for e in f.evidence:
                    w(f"- `{e}`\n")
                w("\n")
            if f.fixes:
                w("**Fixes**\n\n")
                # Numbered, not "1." repeated: GitHub renumbers either way, but
                # the raw source is also read in editors and chat windows.
                for n, fx in enumerate(f.fixes, 1):
                    w(f"{n}. {fx}\n")
                w("\n")
            if f.commands:
                w("**Check** — printed for you to run, never executed by this "
                  "tool\n\n")
                for cmd in f.commands:
                    w(f"- `{md_cell(cmd)}`\n")
                w("\n")
    else:
        w("## Findings\n\nNo rule matched. "
          "The report parsed cleanly but this failure mode is not covered yet — "
          "please open an issue with the report attached.\n\n")


# --------------------------------------------------------------------------
# plain text
# --------------------------------------------------------------------------
def render_plain(rep: CrashReport, findings: list[Finding], triage,
                 out: IO[str], *, hint: bool = True) -> None:
    s = build_summary(rep)
    line = "=" * 74
    w = out.write
    w(f"\n{line}\n Minecraft crash diagnosis\n{line}\n\n")
    # Basename only: the full path is in the JSON and in --explain, and 70
    # columns of C:\Users\... pushes the actual finding off the screen.
    w(f"  source   : {_basename(rep.source_path)}\n")
    w(f"  platform : {_fmt_platform(s, via=' via {}')}\n")
    w(f"  version  : Minecraft {s['minecraft_version'] or '?'} | "
        f"Java {s['java_version'] or '?'}\n")
    w(f"  heap     : {_fmt_heap(s)}"
        f"   mods: {s['mods_parsed'] or s['mod_count'] or '?'}\n")
    for label, value in (("desc", s["description"]),
                         ("root", s["root_cause"])):
        if not value:
            continue
        for i, ln in enumerate(_wrap(value, 60)):
            w((f"  {label:<8} : " if i == 0 else " " * 13) + ln + "\n")
    w("\n")

    if triage and triage.suspects:
        w(f"{line}\n SUSPECT MODS\n{line}\n")
        for sp in triage.suspects:
            w(f"  ● {sp.modid:<26} {sp.confidence:>5.0%}  "
                f"{sp.name} {sp.version}\n".rstrip() + "\n")
            for r in sp.reasons[:3]:
                for i, ln in enumerate(_wrap(r, 62)):
                    w((f"      - {ln}\n" if i == 0 else f"        {ln}\n"))
        for note in triage.notes:
            w(f"  ! {note}\n")
        w("\n")

    w(f"{line}\n FINDINGS ({len(findings)})\n{line}\n")
    if not findings:
        w("  No rule matched this report.\n")
    for i, f in enumerate(findings, 1):
        w(f"\n[{i}] {SEV_LABEL[f.severity]}  {f.title}\n")
        w(f"    rule={f.rule_id}  confidence={f.confidence:.0%}\n")
        if f.explanation:
            # 66 + the 4-space indent + one hanging punctuation stays under the
            # 74-column banner; 70 used to spill past it on Chinese text.
            for ln in _wrap(f.explanation, 66):
                w(f"    {ln}\n")
        if f.evidence:
            w("    evidence:\n")
            for e in f.evidence:
                w(f"      | {e}\n")
        if f.fixes:
            w("    fix:\n")
            for n, fx in enumerate(f.fixes, 1):
                for j, ln in enumerate(_wrap(fx, 60)):
                    w(f"      {n}. {ln}\n" if j == 0 else f"         {ln}\n")
        if f.commands:
            w("    check (printed, never executed):\n")
            for cmd in f.commands:
                w(f"      $ {cmd}\n")
    # The two things a user can do next that the output itself does not say.
    # Kept to one line: a footer that grows into a paragraph stops being read.
    # The --explain half is dropped when it is already running, because telling
    # someone to add a flag they just passed is the classic bad footer.
    if hint:
        w("  next: --explain  shows how the score was built\n"
          "        --feedback opens a pre-filled issue if this is wrong\n\n")


def _split_long(word: str, width: int) -> list[str]:
    """Break one over-long token at dot/slash/dollar boundaries, not mid-name."""
    if _display_width(word) <= width:
        return [word]
    chunks: list[str] = []
    rest = word
    while _display_width(rest) > width:
        best = 0
        for i, ch in enumerate(rest):
            if ch in "./$" and _display_width(rest[:i + 1]) <= width:
                best = i + 1
        if not best:
            # No boundary fits (a 90-char class with no dots left): cut, because
            # overflowing the terminal is worse than a hard break here.
            head = ""
            for ch in rest:
                if _display_width(head + ch) > width:
                    break
                head += ch
            best = len(head) or len(rest)
        chunks.append(rest[:best])
        rest = rest[best:]
    if rest:
        chunks.append(rest)
    return chunks


def _wrap_words(text: str, width: int) -> list[str]:
    """Space-delimited wrap that never splits a token mid-name.

    Used for stack frames and jar names: breaking "ReflectionUtil" from
    ".hasMethodOverride" makes the line unusable for a search or a copy. An
    over-long token breaks at its own dots ("...reflection." / "ReflectionUtil
    .hasMethodOverride"), which keeps every segment whole.
    """
    lines: list[str] = []
    cur = ""
    for word in text.split():
        for piece in _split_long(word, width):
            if not cur:
                cur = piece
            elif _display_width(cur) + 1 + _display_width(piece) <= width:
                cur += " " + piece
            else:
                lines.append(cur)
                cur = piece
    if cur:
        lines.append(cur)
    return lines or [""]


def _md_code(text: str) -> str:
    """Inline code that survives a backtick inside the text.

    A crash message can contain a backtick (a command, a class name in a quote),
    which would close the span early and leave the row half-formatted.
    """
    # Deliberately not md_cell(): that doubles backslashes, which is right in a
    # cell of prose and wrong inside a code span, where a Windows path would
    # come out as C:\\Users\\....
    body = str(text).replace("\r\n", "\n").replace("\r", "\n")
    body = body.replace("\n", " ").replace("|", "\\|")
    if "`" in body:
        return f"`` {body} ``"
    return f"`{body}`"


def _basename(path: str) -> str:
    """Last path component, whichever separator the report arrived with."""
    return (path or "").replace("\\", "/").rsplit("/", 1)[-1]


#: CJK characters that must not start a line (kinsoku). ASCII punctuation is
#: deliberately absent: latin text wraps at spaces, and treating "." as hanging
#: punctuation split "120.00" across two lines.
_NO_LINE_START = set("、。，；：！？）〕】」』》〉")


def _display_width(text: str) -> int:
    """Columns, not characters: a CJK glyph occupies two.

    This is the whole reason the wrapper was rewritten. The old one split on
    spaces, which Chinese does not have, so a 117-character explanation became a
    single 117-character line -- twice the width of the banner above it -- and
    an ASCII word boundary was the only place it could ever break.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in text)


def _split_mixed(word: str, width: int) -> list[str]:
    """Split one whitespace-delimited token without breaking a latin name.

    Chinese has no internal word boundaries and can break anywhere; a Java class
    name can only break at its dots. The old character-by-character wrapper
    produced "ReflectionUtil.ha" / "sMethodOverride", which is unsearchable and
    uncopyable even though it fit the column budget.
    """
    if _display_width(word) <= width:
        return [word]
    if any(unicodedata.east_asian_width(ch) in ("W", "F") for ch in word):
        out: list[str] = []
        cur = ""
        cur_w = 0
        for ch in word:
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if cur and cur_w + cw > width:
                if ch in _NO_LINE_START:
                    out.append(cur + ch)
                    cur, cur_w = "", 0
                    continue
                out.append(cur)
                cur, cur_w = "", 0
            cur += ch
            cur_w += cw
        if cur:
            out.append(cur)
        return out
    return _split_long(word, width)


def _wrap(text: str, width: int) -> list[str]:
    """Wrap to *display columns*: CJK breaks anywhere, latin names only at dots."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            for piece in _split_mixed(word, width):
                if not cur:
                    cur = piece
                elif _display_width(cur) + 1 + _display_width(piece) <= width:
                    cur += " " + piece
                else:
                    lines.append(cur.rstrip())
                    cur = piece
        if cur.strip():
            lines.append(cur.rstrip())
    return lines or [""]


# --------------------------------------------------------------------------
# terminal (rich)
# --------------------------------------------------------------------------
def render_terminal(rep: CrashReport, findings: list[Finding], triage,
                    out: IO[str], *, color: bool = True) -> None:
    if not HAS_RICH or not color:
        render_plain(rep, findings, triage, out)
        return
    con = Console(file=out, width=100)
    s = build_summary(rep)

    env = Table.grid(padding=(0, 2))
    env.add_column(style="dim", no_wrap=True)
    env.add_column()
    plat = _fmt_platform(s, via=" [dim](via {})[/dim]")
    env.add_row("platform", plat)
    env.add_row("version", f"Minecraft [bold]{s['minecraft_version'] or '?'}[/bold]"
                           f"  ·  Java {s['java_major'] or '?'}")
    heap = _fmt_heap(s)
    if s["heap_max_mib"] and s["heap_max_mib"] <= 2048 and (s["mod_count"] or 0) > 100:
        heap += " [red]← small for this mod count[/red]"
    env.add_row("heap", heap)
    env.add_row("mods", str(s["mods_parsed"] or s["mod_count"] or "?"))
    if s["os"]:
        env.add_row("os", s["os"])
    if s["root_cause"]:
        env.add_row("root cause", Text(s["root_cause"], style="bold red"))
    con.print()
    con.print(Panel(env, title="[bold]Minecraft crash diagnosis[/bold]",
                    subtitle=rep.source_path.split("\\")[-1].split("/")[-1],
                    border_style="blue", expand=False))

    if triage and triage.suspects:
        t = Table(title="Suspect mods", expand=False, title_style="bold")
        t.add_column("mod", style="bold yellow", no_wrap=True)
        t.add_column("conf", justify="right")
        t.add_column("version", style="dim", no_wrap=True)
        t.add_column("why", overflow="fold")
        for sp in triage.suspects:
            conf = sp.confidence
            style = "bold red" if conf >= 0.8 else ("yellow" if conf >= 0.4 else "dim")
            t.add_row(sp.modid, f"[{style}]{conf:.0%}[/{style}]",
                      sp.version or "-",
                      (sp.reasons[0] if sp.reasons else ""))
        con.print(t)
        for note in triage.notes:
            con.print(f"  [cyan]![/cyan] {note}")
        con.print()

    if findings:
        con.print(f"[bold]Findings[/bold] ({len(findings)})")
        for i, f in enumerate(findings, 1):
            color_ = SEV_COLOR[f.severity]
            head = Text()
            head.append(f"{i}. ", style="dim")
            head.append(f"[{SEV_LABEL[f.severity]}] ", style=color_)
            head.append(f.title, style="bold")
            head.append(f"   ({f.rule_id}, {f.confidence:.0%})", style="dim")
            con.print(head)
            if f.explanation:
                for ln in _wrap(f.explanation, 92):
                    con.print(f"    {ln}")
            if f.evidence:
                con.print("    [dim]evidence[/dim]")
                for e in f.evidence:
                    con.print(f"      [dim]| {e}[/dim]")
            if f.fixes:
                con.print("    [green]fix[/green]")
                for n, fx in enumerate(f.fixes, 1):
                    for j, ln in enumerate(_wrap(fx, 88)):
                        con.print(f"      {n}. {ln}" if j == 0 else f"         {ln}")
            if f.commands:
                con.print("    [cyan]check[/cyan] [dim](printed, never "
                          "executed)[/dim]")
                for cmd in f.commands:
                    con.print(f"      [dim]$ {cmd}[/dim]")
            con.print()
    else:
        con.print("[yellow]No rule matched this report.[/yellow] It parsed cleanly, "
                  "but this failure mode is not covered yet — please open an issue "
                  "with the report attached.")
    con.print()

# --- --explain ---------------------------------------------------------------
def _by_reason(rows) -> list[tuple[float, int, str]]:
    """Sum the weights of identical reasons, keeping the biggest first.

    The engine records one entry per hit, so "jar on the failing path" appears
    once per frame. Ten identical rows would be accurate and unreadable; the
    count keeps the information and drops the repetition.
    """
    totals: dict[str, tuple[float, int]] = {}
    for weight, reason in rows:
        total, count = totals.get(reason, (0.0, 0))
        totals[reason] = (total + weight, count + 1)
    out = [(w, n, r) for r, (w, n) in totals.items()]
    out.sort(key=lambda item: (-item[0], item[2]))
    return out


def render_explain(triage, trace: dict[str, list[tuple[float, str]]],
                   out: IO[str], *, markdown: bool = False,
                   top_suspects: int = 3, top_signals: int = 8) -> None:
    """Show how the suspicion score was assembled: `--explain`'s payload.

    The point is auditability. A tool that says "create, 62%" and cannot show
    the arithmetic is asking to be believed; this prints the weights so the user
    can disagree with a specific line instead of with the whole answer.
    """
    suspects = list(getattr(triage, "suspects", ()) or ())
    if not suspects:
        out.write("\nno mod was implicated: no attribution signal fired.\n")
        return
    total_evidence = sum(w for rows in trace.values() for w, _ in rows) or 1.0

    if markdown:
        out.write("\n## Why these suspects\n\n")
        out.write("Each suspect's score is the sum of the weighted signals below; "
                  "confidence is its share of all recorded evidence, damped when "
                  "the leader is barely ahead. Negative evidence is not a thing "
                  "here: every row adds.\n")
    else:
        out.write("\n" + "=" * 74 + "\n suspicion breakdown\n" + "=" * 74 + "\n")
        out.write("score = sum of weighted signals; confidence = share of "
                  "evidence\n")

    for s in suspects[:top_suspects]:
        rows = _by_reason(trace.get(s.modid, ()))[:top_signals]
        head = (f"{s.modid}  score {s.score:.1f}  confidence {s.confidence:.0%}  "
                f"(of {total_evidence:.1f} total evidence)")
        if markdown:
            out.write(f"\n**{md_cell(head)}**\n\n")
            out.write("| weight | n | signal |\n|---:|---:|---|\n")
            for weight, count, reason in rows:
                out.write(f"| {weight:.2f} | {count} | {md_cell(reason)} |\n")
        else:
            out.write(f"\n{head}\n")
            for weight, count, reason in rows:
                times = f" x{count}" if count > 1 else ""
                prefix = f"  {weight:6.2f}{times:5s}  "
                for i, ln in enumerate(_wrap_words(reason,
                                                   74 - _display_width(prefix))):
                    out.write((prefix if i == 0 else " " * _display_width(prefix))
                              + ln + "\n")

    # A near-tie is not a footnote: it says the answer is "one of these two",
    # which changes what the user should do next.
    notes = list(getattr(triage, "notes", ()) or ())
    unresolved = list(getattr(triage, "unresolved_modids", ()) or ())
    if notes or unresolved:
        if markdown:
            out.write("\n### Caveats\n\n")
        else:
            out.write("\ncaveats:\n")
        for note in notes:
            out.write(f"- {md_cell(note)}\n" if markdown else f"  * {note}\n")
        if unresolved:
            shown = unresolved[:8]
            if markdown:
                out.write(f"- {md_cell('could not resolve: ' + ', '.join(shown))}\n")
            else:
                # One per line: a dozen jar names in one sentence ran to 200
                # columns and hid the two entries that mattered.
                out.write("  * could not resolve:\n")
                for name in shown:
                    for ln in _wrap_words(name, 66):
                        out.write(f"      {ln}\n")
            if len(unresolved) > len(shown):
                more = f"... and {len(unresolved) - len(shown)} more"
                out.write(f"      {more}\n" if not markdown else f"      {more}\n")
