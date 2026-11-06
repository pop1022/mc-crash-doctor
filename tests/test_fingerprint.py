"""Fingerprint contract: same crash, same id; different crash, different id.

`corpus/CRASH-FINGERPRINTS.md` reports 454 -> 377 groups (mean 1.20) with 7
mixed-description groups. That last number is why the tool prints the
differences inside every group: a grouping this fine is safe for counting
reports, but R11 says it must never silently become "one conclusion".

    pytest tests/test_fingerprint.py -v
"""
from __future__ import annotations

import dataclasses

import pytest

from mcd.fingerprint import cluster, fingerprint, normalise, signature
from mcd.model import CrashReport, ExceptionBlock, StackFrame, SystemDetails


def _rep(kind="java.lang.NullPointerException", message="Cannot invoke X",
         loader="forge", cls="a.b.C", method="go", suspect=""):
    block = ExceptionBlock(kind=kind, message=message,
                           frames=[StackFrame(raw="at a.b.C.go(C.java:1)",
                                             cls=cls, method=method)])
    return dataclasses.replace(
        CrashReport(exceptions=[block]),
        system=SystemDetails(loader=loader)), block


def test_normalise_drops_values_but_keeps_words():
    a = normalise('Cannot invoke "a.b.C.go()" because "x" is null at 12:34')
    b = normalise('Cannot invoke "d.e.F.go()" because "y" is null at 99:99')
    assert a == b
    assert "<q>" in a or "<fqcn>" in a


@pytest.mark.parametrize("change", [
    {"kind": "java.lang.IllegalStateException"},
    {"loader": "fabric"},
    {"cls": "z.y.X", "method": "other"},
])
def test_a_different_crash_gets_a_different_fingerprint(change):
    rep, _ = _rep()
    other, _ = _rep(**change)
    assert fingerprint(rep) != fingerprint(other)


def test_per_report_values_do_not_change_the_fingerprint():
    a, _ = _rep(message='Cannot invoke "a.b.C.go()" because "x" is null')
    b, _ = _rep(message='Cannot invoke "a.b.C.go()" because "totally different" is null')
    assert fingerprint(a) == fingerprint(b)


def test_top_suspect_is_part_of_the_key():
    rep, _ = _rep()
    assert fingerprint(rep) != fingerprint(rep, top_suspect="sodium")
    assert signature(rep, top_suspect="sodium")[2] == "sodium"


def test_a_report_without_frames_still_has_a_stable_id():
    rep = dataclasses.replace(CrashReport(), exceptions=[
        ExceptionBlock(kind="java.lang.Error", message="boom")])
    assert fingerprint(rep) == fingerprint(rep)
    assert signature(rep)[3] == "(no frames)"


def test_cluster_orders_by_size_and_is_deterministic():
    rows = [("a", "r1"), ("b", "r2"), ("a", "r3"), ("a", "r4")]
    assert cluster(rows) == {"a": ["r1", "r3", "r4"], "b": ["r2"]}
    assert list(cluster(rows))[0] == "a"
