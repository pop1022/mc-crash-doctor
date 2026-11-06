"""Minimum regression for the four modules that had no test file of their own.

The suite has ~950 tests, but they concentrated on the engine, triage, rules and
the pack *doctor*. These four modules were reached only indirectly, which meant
a change to their contracts (a renderer losing a section, `root_cause` drifting,
a paste-ID regex widening) could pass everything with no dedicated signal.

This file is deliberately small: one behaviour per module that would be painful
to lose, not a mirror of the modules' internals.

    pytest tests/test_modules_smoke.py -v
"""
from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path

from mcd.extract import Extracted, _looks_like_report, mclogs_id
from mcd.model import CrashReport, ExceptionBlock
from mcd.pack.doctor import PackReport
from mcd.pack.render import (render_pack_json, render_pack_markdown,
                             render_pack_plain)
from mcd.parser.report import parse_file
from mcd.report.render import (SCHEMA_VERSION, build_incident, render_json,
                               render_markdown, render_plain)
from mcd.rules.engine import RuleSet, run_rules
from mcd.triage.attribution import triage

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures/synthetic/disk-space.txt"


# --- mcd/extract.py ---------------------------------------------------------
def test_mclogs_id_accepts_share_and_raw_urls_only():
    assert mclogs_id("https://mclo.gs/6cWndzQ") == "6cWndzQ"
    assert mclogs_id("https://api.mclo.gs/1/raw/AbCdEf9") == "AbCdEf9"
    assert mclogs_id("https://pastebin.com/AbCdEf9") is None
    assert mclogs_id("not a url at all") is None


def test_looks_like_report_does_not_accept_prose():
    assert not _looks_like_report("hello, I have a problem with my server")
    assert _looks_like_report(
        "---- Minecraft Crash Report ----\n\nDescription: Ticking entity\n")


def test_extracted_best_is_the_longest_candidate():
    e = Extracted(body="", texts=["short", "a much longer log blob"],
                  sources=["inline", "mclo.gs:x"])
    assert e.best == "a much longer log blob"
    assert Extracted(body="").best is None


# --- mcd/model.py -----------------------------------------------------------
def test_root_cause_prefers_the_last_fatal_block_over_earlier_noise():
    """Log files carry a timeline: an earlier WARN-level exception is noise,
    the FATAL one is what killed the process. Pinned so a future "simplify"
    cannot silently go back to taking the first exception."""
    warn = ExceptionBlock(kind="java.lang.NumberFormatException",
                          message="bad config", fatal=False)
    fatal = ExceptionBlock(kind="java.lang.OutOfMemoryError",
                           message="Java heap space", fatal=True)
    rep = replace(CrashReport(), exceptions=[warn, fatal])
    assert rep.root_cause is fatal

    rep2 = replace(CrashReport(), exceptions=[fatal, warn])
    assert rep2.root_cause is fatal

    assert replace(CrashReport(), exceptions=[]).root_cause is None


def test_root_cause_falls_back_to_the_deepest_caused_by():
    outer = ExceptionBlock(kind="java.lang.RuntimeException", message="outer")
    inner = ExceptionBlock(kind="java.lang.NullPointerException",
                           message="inner", is_caused_by=True, depth=1)
    assert replace(CrashReport(), exceptions=[outer, inner]).root_cause is inner


# --- mcd/pack/render.py -----------------------------------------------------
def test_pack_renderers_keep_all_four_buckets_visible():
    """`undecided` and `unreadable` are not findings; losing them would make a
    report say "1 finding" and hide what it could not check."""
    rep = PackReport(root=".", mods_dir="mods", jars=2, declared_mods=1,
                     context={"mc_version": "1.21.1"})
    rep.findings.append(_finding())
    rep.undecided.append({"modid": "x", "required_by": "y", "range": "*",
                          "installed": "1.0"})
    rep.unreadable.append({"jar": "lib.jar", "reason": "no manifest"})

    md, plain, js = io.StringIO(), io.StringIO(), io.StringIO()
    render_pack_markdown(rep, md)
    render_pack_plain(rep, plain)
    render_pack_json(rep, js)

    assert "Undecided" in md.getvalue() and "no manifest" in md.getvalue()
    assert "undecided" in plain.getvalue() and "no manifest" in plain.getvalue()
    assert "\x1b[" not in plain.getvalue(), "plain output must be ANSI-free"
    doc = json.loads(js.getvalue())
    assert doc["jars"] == 2 and doc["not_checked"], doc
    assert len(doc["undecided"]) == 1 and len(doc["unreadable"]) == 1


def _finding():
    from mcd.model import Severity

    from mcd.pack.doctor import PackFinding
    return PackFinding(kind="pack.missing-dependency",
                       severity=Severity.WARNING, subject="x",
                       detail="a dependency is missing", evidence=["y.jar"])


# --- mcd/report/render.py ---------------------------------------------------
def _diagnosis():
    rep = parse_file(FIX)
    rs = RuleSet.load()
    findings = run_rules(rep, rs)
    return rep, findings, triage(rep)


def test_incident_json_is_a_valid_document_with_a_version():
    rep, findings, t = _diagnosis()
    doc = build_incident(rep, findings, t)
    assert doc["schema_version"] == SCHEMA_VERSION == "1.0"
    assert isinstance(doc["findings"], list) and doc["findings"], doc
    assert json.loads(json.dumps(doc, ensure_ascii=False))["schema_version"] == "1.0"


def test_all_three_report_renderers_agree_on_the_findings():
    rep, findings, t = _diagnosis()
    for renderer, kwargs in ((render_json, {}), (render_markdown, {}),
                             (render_plain, {})):
        buf = io.StringIO()
        renderer(rep, findings, t, buf, **kwargs)
        text = buf.getvalue()
        assert text.strip(), f"{renderer.__name__} produced nothing"
        assert "\x1b[" not in text, f"{renderer.__name__} leaked ANSI codes"
        assert "disk" in text.lower(), f"{renderer.__name__} lost the finding"
    if render_json is not None:            # JSON must parse, not just look pretty
        buf = io.StringIO()
        render_json(rep, findings, t, buf)
        assert json.loads(buf.getvalue())["schema_version"] == SCHEMA_VERSION
