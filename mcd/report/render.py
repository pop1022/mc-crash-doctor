"""Rendering backends: terminal (rich), plain text, JSON, Markdown."""

from __future__ import annotations

import json
import sys
from typing import IO

from ..model import CrashReport, Finding, Severity

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
        "root_cause": rc.signature if rc else None,
        "exception_chain": [e.signature for e in rep.exceptions],
        "is_server": sysd.is_server,
        "is_client": sysd.is_client,
    }


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
def render_json(rep: CrashReport, findings: list[Finding], triage,
                out: IO[str]) -> None:
    doc = {
        "source": rep.source_path,
        "summary": build_summary(rep),
        "findings": [f.to_dict() for f in findings],
        "triage": triage.to_dict() if triage else None,
    }
    json.dump(doc, out, ensure_ascii=False, indent=2)
    out.write("\n")


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def render_markdown(rep: CrashReport, findings: list[Finding], triage,
                    out: IO[str]) -> None:
    s = build_summary(rep)
    w = out.write
    w("# Minecraft crash diagnosis\n\n")
    w(f"*Source:* `{rep.source_path}`\n\n")

    w("## Environment\n\n")
    w("| | |\n|---|---|\n")
    w(f"| Platform | {s['loader']} {s['loader_version'] or ''}"
      f"{(' (via ' + s['launcher'] + ')') if s['launcher'] else ''} |\n")
    w(f"| Minecraft | {s['minecraft_version'] or '?'} |\n")
    w(f"| Java | {s['java_version'] or '?'} (major {s['java_major']}) |\n")
    w(f"| Heap | {_fmt_heap(s)} |\n")
    w(f"| Mods | {s['mods_parsed'] or s['mod_count'] or '?'} |\n")
    w(f"| OS | {s['os'] or '?'} |\n")
    if s["root_cause"]:
        w(f"| Root cause | `{s['root_cause']}` |\n")
    w("\n")

    if triage and triage.suspects:
        w("## Suspect mods\n\n")
        w("| Mod | Version | Confidence | Why |\n|---|---|---|---|\n")
        for sp in triage.suspects:
            why = (sp.reasons[0] if sp.reasons else "").replace("|", "\\|")
            w(f"| `{sp.modid}` | {sp.version or '-'} | {sp.confidence:.0%} | {why} |\n")
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
                for fx in f.fixes:
                    w(f"1. {fx}\n")
                w("\n")
    else:
        w("## Findings\n\nNo rule matched. "
          "The report parsed cleanly but this failure mode is not covered yet — "
          "please open an issue with the report attached.\n\n")


# --------------------------------------------------------------------------
# plain text
# --------------------------------------------------------------------------
def render_plain(rep: CrashReport, findings: list[Finding], triage,
                 out: IO[str]) -> None:
    s = build_summary(rep)
    line = "=" * 74
    w = out.write
    w(f"\n{line}\n Minecraft crash diagnosis\n{line}\n\n")
    w(f"  source   : {rep.source_path}\n")
    w(f"  platform : {s['loader']} {s['loader_version'] or ''}"
        f"{(' via ' + s['launcher']) if s['launcher'] else ''}\n")
    w(f"  version  : Minecraft {s['minecraft_version'] or '?'} | "
        f"Java {s['java_version'] or '?'}\n")
    w(f"  heap     : {_fmt_heap(s)}"
        f"   mods: {s['mods_parsed'] or s['mod_count'] or '?'}\n")
    if s["description"]:
        w(f"  desc     : {s['description']}\n")
    if s["root_cause"]:
        w(f"  root     : {s['root_cause']}\n")
    w("\n")

    if triage and triage.suspects:
        w(f"{line}\n SUSPECT MODS\n{line}\n")
        for sp in triage.suspects:
            w(f"  ● {sp.modid:<26} {sp.confidence:>5.0%}  "
                f"{sp.name} {sp.version}\n".rstrip() + "\n")
            for r in sp.reasons[:3]:
                w(f"      - {r}\n")
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
            for ln in _wrap(f.explanation, 70):
                w(f"    {ln}\n")
        if f.evidence:
            w("    evidence:\n")
            for e in f.evidence:
                w(f"      | {e}\n")
        if f.fixes:
            w("    fix:\n")
            for n, fx in enumerate(f.fixes, 1):
                for j, ln in enumerate(_wrap(fx, 66)):
                    w(f"      {n}. {ln}\n" if j == 0 else f"         {ln}\n")
    w("\n")


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for wd in words:
        if len(cur) + len(wd) + 1 <= width:
            cur = f"{cur} {wd}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


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
    plat = s["loader"] + (f" {s['loader_version']}" if s["loader_version"] else "")
    if s["launcher"]:
        plat += f" [dim](via {s['launcher']})[/dim]"
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
            con.print()
    else:
        con.print("[yellow]No rule matched this report.[/yellow] It parsed cleanly, "
                  "but this failure mode is not covered yet — please open an issue "
                  "with the report attached.")
    con.print()
