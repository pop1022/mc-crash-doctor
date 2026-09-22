"""mc-crash-doctor -- diagnose Minecraft crash reports and logs.

Public API (also available as the ``mc-crash-doctor`` / ``mcd`` CLI):

    from mcd import diagnose
    rep, findings, triage = diagnose("crash-report.txt")

Imports are lazy so that ``python -m mcd.cli`` does not emit a RuntimeWarning
about the module already being in sys.modules, and so importing ``mcd`` stays
cheap when only one piece is needed.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "diagnose",
    "CrashReport",
    "Finding",
    "Severity",
    "parse_file",
    "parse_text",
    "RuleSet",
    "run_rules",
    "triage",
]

_LAZY = {
    "diagnose": (".cli", "diagnose"),
    "CrashReport": (".model", "CrashReport"),
    "Finding": (".model", "Finding"),
    "Severity": (".model", "Severity"),
    "parse_file": (".parser.report", "parse_file"),
    "parse_text": (".parser.report", "parse_text"),
    "RuleSet": (".rules.engine", "RuleSet"),
    "run_rules": (".rules.engine", "run_rules"),
    "triage": (".triage.attribution", "triage"),
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib

        mod, attr = _LAZY[name]
        value = getattr(importlib.import_module(mod, __name__), attr)
        globals()[name] = value      # cache for subsequent accesses
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY.keys()))
