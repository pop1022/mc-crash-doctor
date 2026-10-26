"""Small text helpers shared by the renderers.

Kept dependency-free on purpose: both :mod:`mcd.report.render` (which pulls in
the optional `rich` import) and :mod:`mcd.pack.render` need these, and the pack
side must not inherit a rich dependency to escape a pipe.
"""
from __future__ import annotations


def md_cell(value: object) -> str:
    """Escape a value for a GitHub-flavoured markdown table cell.

    A pipe in any cell splits the row, and a newline ends it -- so an exception
    message like ``expected mask a|b`` turns a two-column table into a
    five-column one. `--markdown` exists to be pasted into an issue, so the
    input that breaks it (arbitrary text from the crash report) is the normal
    case, not an edge case.
    """
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return (text.replace("\\", "\\\\")
                .replace("|", "\\|")
                .replace("\n", " "))
