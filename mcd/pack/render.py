"""Rendering for Pack Doctor. Three formats, one source of truth.

The terminal form leads with what is *wrong*, then prints the two buckets that
are not findings (`undecided`, `unreadable`) even when they are empty-looking
counts -- because "0 findings, 12 undecided" and "0 findings, 12 jars" are
completely different answers and a bare "no problems found" hides which one you
got.
"""
from __future__ import annotations

import json
from typing import TextIO

from ..model import Severity
from ..textfmt import md_cell
from .doctor import NOT_CHECKED, PackReport

_MARK = {Severity.FATAL: "!!", Severity.ERROR: "x ", Severity.WARNING: "! ",
         Severity.HINT: "- ", Severity.INFO: "  "}

# ANSI rather than rich: Pack Doctor runs with no optional dependencies, and a
# severity colour is the kind of thing that should not need one. Only emitted
# when the caller passes color=True, which the CLI derives from `isatty()` and
# `--no-color`, so captured/piped output is byte-identical to before.
_ANSI = {Severity.FATAL: "\x1b[1;31m", Severity.ERROR: "\x1b[31m",
         Severity.WARNING: "\x1b[33m", Severity.HINT: "\x1b[36m",
         Severity.INFO: "\x1b[2m"}
_RESET = "\x1b[0m"


def _paint(text: str, sev: Severity, color: bool) -> str:
    if not color:
        return text
    return f"{_ANSI.get(sev, '')}{text}{_RESET}"


def render_pack_json(rep: PackReport, out: TextIO) -> None:
    json.dump(rep.to_dict(), out, indent=2, ensure_ascii=False)
    out.write("\n")


def render_pack_markdown(rep: PackReport, out: TextIO) -> None:
    out.write(f"### Pack Doctor — `{rep.mods_dir}`\n\n")
    ctx = ", ".join(f"{k} `{v}`" for k, v in rep.context.items())
    out.write(f"{rep.jars} jars · {rep.declared_mods} declared mods"
              + (f" · pack says {ctx}" if ctx else "") + "\n\n")
    if rep.findings:
        out.write("| severity | kind | subject | detail |\n|---|---|---|---|\n")
        for f in rep.findings:
            out.write(f"| {f.severity.name} | `{md_cell(f.kind)}` | "
                      f"`{md_cell(f.subject)}` | {md_cell(f.detail)} |\n")
        out.write("\n")
    else:
        out.write("No contradictions between the installed jars.\n\n")

    if rep.undecided:
        out.write("**Undecided** — the constraint was read but not understood, "
                  "so nothing is claimed either way:\n\n")
        out.write("| mod | required by | declared range | installed |\n|---|---|---|---|\n")
        for u in rep.undecided:
            out.write(f"| `{md_cell(u['modid'])}` | `{md_cell(u['required_by'])}` | "
                      f"`{md_cell(u['range'])}` | `{md_cell(u['installed'] or '?')}` |\n")
        out.write("\n")
    if rep.unreadable:
        out.write("**Not checked** — jars with no manifest this tool can read:\n\n")
        for u in rep.unreadable:
            out.write(f"- `{u['jar']}` — {u['reason']}\n")
        out.write("\n")
    out.write("<details><summary>What this check does not cover</summary>\n\n")
    for line in NOT_CHECKED:
        out.write(f"- {line}\n")
    out.write("\n</details>\n")


def render_pack_plain(rep: PackReport, out: TextIO, *, color: bool = False) -> None:
    """Terminal form. ``color`` paints only the severity head of each finding;
    every other line is unchanged so the two forms stay diff-able."""
    head = f"Pack Doctor: {rep.mods_dir}"
    out.write(head + "\n" + "=" * len(head) + "\n")
    out.write(f"{rep.jars} jars, {rep.declared_mods} declared mods")
    if rep.loaders:
        out.write("  [" + ", ".join(f"{k} {v}" for k, v in rep.loaders.items()) + "]")
    out.write("\n")
    if rep.context:
        out.write("pack manifest: "
                  + ", ".join(f"{k}={v}" for k, v in rep.context.items()) + "\n")
    out.write("\n")

    if rep.findings:
        for f in rep.findings:
            head = f"{_MARK.get(f.severity, '  ')} {f.subject}"
            out.write(_paint(head, f.severity, color) + "\n")
            out.write(f"    {f.detail}\n")
            if f.evidence:
                out.write(f"    evidence: {', '.join(f.evidence)}\n")
    else:
        out.write("no contradictions between the installed jars\n")

    if rep.undecided:
        out.write(f"\nundecided ({len(rep.undecided)}) -- range not understood, "
                  f"nothing claimed:\n")
        for u in rep.undecided:
            out.write(f"  ? {u['modid']}: {u['required_by']} wants "
                      f"{u['range']}, installed {u['installed'] or 'unknown'}\n")
    if rep.unreadable:
        out.write(f"\nnot checked ({len(rep.unreadable)}) -- no readable "
                  f"manifest:\n")
        for u in rep.unreadable:
            out.write(f"  ? {u['jar']}: {u['reason']}\n")

    out.write("\nnot covered: " + "; ".join(NOT_CHECKED) + "\n")
