"""Make the corpus gate visible instead of silent.

See tests/_corpus_gate.py for why. MCD_REQUIRE_CORPUS=1 turns "the data is not
here" into a failure, which is what a private CI job should set.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _corpus_gate import (GATE, MARKER, has_corpus, is_corpus_skip,  # noqa: E402
                          summary_line)

SKIPPED: list[str] = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "private_corpus: needs corpus/github/**/*.crash.txt, which is not shipped")


def pytest_collection_modifyitems(config, items):
    if has_corpus():
        return
    skip = pytest.mark.skip(
        reason=f"{MARKER}: extended gate NOT RUN (see tests/_corpus_gate.py)")
    for item in items:
        if "private_corpus" in item.keywords:
            item.add_marker(skip)


def pytest_runtest_logreport(report):
    if report.skipped:
        reason = ""
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2])
        elif hasattr(report.longrepr, "reprcrash"):
            reason = report.longrepr.reprcrash.message
        if is_corpus_skip(reason):
            SKIPPED.append(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    # A private job that claims to run the extended gate must not pass while
    # every corpus case was skipped.
    if os.environ.get("MCD_REQUIRE_CORPUS") and SKIPPED:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_sep("-", GATE)
    terminalreporter.write_line(summary_line(len(SKIPPED)))
