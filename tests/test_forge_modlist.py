"""Contract + performance guard for the Forge/NeoForge Mod List row splitter.

Background: `_parse_forge_modlist` used to match each row with a six-group
lazy regex. On a *mangled* row -- which is common in harvested reports, because
issue authors paste partially-formatted tables -- the engine had exponentially
many ways to distribute the same whitespace between the lazy groups and the
interleaved `\\s*`, and gave up only after exhausting them. Measured on the real
corpus:

    row length   old regex per row
    121 chars            2 ms
    186 chars           54 ms
    242 chars          321 ms
    306 chars         1326 ms

Two harvested reports (Mekanism#2697, Placebo#8291) contain ~350 such rows each,
i.e. 9.4 s to parse a 276 KB file. A full 454-report corpus pass spent ~95% of
its wall clock in this one call (250.8 s -> 30.7 s after the fix).

The replacement splits on "|", which is linear. These tests pin both halves:
the accept/reject contract (so the rewrite cannot silently change what counts
as a mod row) and the cost (so a regex cannot quietly come back).

    pytest tests/test_forge_modlist.py -v
"""
from __future__ import annotations

import time

import pytest

from mcd.parser.report import _forge_row, _parse_forge_modlist

#: Real Forge 1.21 rows are indented with tabs. `^\s*` in the old regex ate
#: that indentation before the tab-rejecting character class ever saw it; the
#: first version of the split rewrite checked for tabs before stripping and
#: therefore rejected *every real row* (Mekanism#5379: 1047 mods -> 0). This
#: constant exists so that mistake cannot come back unnoticed.
TAB_INDENTED = ("\t\tcreate-1.20.1-0.5.1.jar                      "
                "|Create                        |create          "
                "|0.5.1               |Manifest: NOSIGNATURE|")


def test_tab_indented_row_is_accepted():
    row = _forge_row(TAB_INDENTED)
    assert row is not None, "tab-indented rows are the normal case, not an edge case"
    f, name, modid, ver, status, manifest = row
    assert f == "create-1.20.1-0.5.1.jar"
    assert name == "Create"
    assert modid == "create"
    assert ver == "0.5.1"
    assert status == "Manifest: NOSIGNATURE"
    assert manifest == ""


def test_field_values_survive_padding():
    """Whitespace padding is alignment, not data."""
    row = _forge_row("\t\t  padded.jar   |  Padded Name  |  padded  |  1.0  |  ok  |  ")
    assert row == ("padded.jar", "Padded Name", "padded", "1.0", "ok", "")


@pytest.mark.parametrize("line", [
    "",                                   # blank
    "\t\tjust a jar name.jar",            # no table at all
    "\t\ta|b|c|d|e",                      # 4 pipes -> 5 fields, one short
    "\t\t|\t|b|c|d|e",                   # tab inside a field
    "\t\t |b|c|d|e|f",                    # empty first field
    "   ",                                # whitespace only
])
def test_malformed_rows_are_rejected(line):
    assert _forge_row(line) is None


def test_sixth_field_may_contain_pipes():
    """The old `(.*?)` sixth group was free-form; a status column with a pipe
    in it must not become an extra field."""
    row = _forge_row("\t\tx.jar | X | x | 1.0 | ok | Manifest: a|b")
    assert row is not None
    assert row[5] == "Manifest: a|b"


def test_full_table_row_count():
    text = ("Mod List: \n"
            + "\n".join(TAB_INDENTED.replace("create", f"mod{i}") for i in range(5))
            + "\n")
    mods, _ = _parse_forge_modlist(text, 0)
    assert [m.modid for m in mods] == [f"mod{i}" for i in range(5)]


def _mangled_row(length_bucket: int = 242) -> str:
    """A partial row: one column short (4 pipes) and padded to `length_bucket`.

    This is the exact shape that made the old regex backtrack -- and it is a
    *reject* case, which is why the blowup was invisible in output: the row
    never became a mod, only 300 ms of CPU.
    """
    row = ("\t\t" + "ferritecore-7.0.3-neoforge.jar".ljust(70)
           + "|" + "Ferrite Core".ljust(60)
           + "|" + "ferritecore".ljust(40)
           + "|" + "7.0.3".ljust(66)
           + "|")
    assert len(row) == length_bucket
    return row


def test_mangled_row_is_rejected():
    assert _forge_row(_mangled_row()) is None


def test_pathological_table_stays_fast():
    """Tripwire against reintroducing a backtracking regex.

    Numbers on the old implementation: 242-char mangled rows cost 321 ms each,
    so the 200 rows below took ~64 s. The splitter needs ~1 ms for the same
    work. A 2 s budget is 2000x the current cost and ~30x below the old one,
    so it fires on a regression without being flaky on a slow CI box.
    """
    row = _mangled_row()
    text = "Mod List: \n" + "\n".join([row] * 200) + "\n"
    t0 = time.perf_counter()
    mods, _ = _parse_forge_modlist(text, 0)
    elapsed = time.perf_counter() - t0
    assert mods == [], "mangled rows must not be parsed as mods"
    assert elapsed < 2.0, (
        f"200 malformed rows took {elapsed:.1f}s -- the row matcher is "
        f"backtracking again (see this module's docstring for the numbers)")


def test_splitter_is_linear_not_exponential():
    """Doubling the row length must roughly double the work, not square it.

    Cheap and robust: compare 5k short rows against 5k rows twice as long, and
    insist the ratio stays under 10x. Exponential backtracking shows up here as
    a ratio in the hundreds, which is the whole point.
    """
    short = "\t\t" + "a.jar".ljust(60) + "|" + "N".ljust(30) + \
        "|" + "n".ljust(20) + "|" + "1.0".ljust(20) + "|" + "ok"
    long = "\t\t" + "a.jar".ljust(120) + "|" + "N".ljust(60) + \
        "|" + "n".ljust(40) + "|" + "1.0".ljust(40) + "|" + "ok"
    assert len(long) > 2 * len(short) * 0.95

    def cost(row: str) -> float:
        n = 5000
        t0 = time.perf_counter()
        for _ in range(n):
            _forge_row(row)
        return time.perf_counter() - t0

    ratio = cost(long) / max(cost(short), 1e-9)
    assert ratio < 10, f"cost grew {ratio:.1f}x for a 2x longer row"
