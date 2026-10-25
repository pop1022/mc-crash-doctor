"""Pack Doctor (ROADMAP 2.2) -- check a `mods/` directory without a crash.

Two modules, two questions:

* `doctor` -- "does this pack contradict itself?" Compares what each jar
  declares (`depends`, `conflicts`, `breaks`, `versionRange`) against what is
  actually installed. No network: this is why it can ship before 2.1/1D.2.
* `version` -- "does this version satisfy that range?" Maven intervals,
  Fabric's `~`/`^`/`x` forms, and the bare form that means *minimum*, not exact.

    from mcd.pack.doctor import analyse
    rep = analyse("/srv/minecraft")
    print(rep.summary_line())

The one invariant worth remembering: `undecided` and `unreadable` are printed,
never swallowed. The tool is allowed to say "I do not know"; it is not allowed
to say "fine" when it does not know.
"""
from .doctor import NOT_CHECKED, BUILTIN_IDS, PackFinding, PackReport, analyse
from .version import compare, parse_spec, satisfies

__all__ = [
    "analyse", "PackReport", "PackFinding", "BUILTIN_IDS", "NOT_CHECKED",
    "satisfies", "parse_spec", "compare",
]
