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
from .doctor import NOT_CHECKED, PackReport

_MARK = {Severity.FATAL: "!!", Severity.ERROR: "x ", Severity.WARNING: "! ",
         Severity.HINT: "- ", Severity.INFO: "  "}


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
            detail = f.detail.replace("|", "\\|")
            out.write(f"| {f.severity.name} | `{f.kind}` | `{f.subject}` | "
                      f"{detail} |\n")
        out.write("\n")
    else:
        out.write("No contradictions between the installed jars.\n\n")

    if rep.undecided:
        out.write("**Undecided** — the constraint was read but not understood, "
                  "so nothing is claimed either way:\n\n")
        out.write("| mod | required by | declared range | installed |\n|---|---|---|---|\n")
        for u in rep.undecided:
            out.write(f"| `{u['modid']}` | `{u['required_by']}` | "
                      f"`{u['range']}` | `{u['installed'] or '?'}` |\n")
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
            out.write(f"{_MARK.get(f.severity, '  ')} {f.subject}\n")
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
