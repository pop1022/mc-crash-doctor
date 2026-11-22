"""The precomputed sample must describe exactly what the engine would say.

It is shown before Pyodide finishes loading (and kept if the CDN never answers),
which is only honest while it is generated from the same engine and the same
input. Recomputing here is what keeps that true: edit a rule or the sample text
and this fails until tools/make_web_sample.py is re-run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mcd.cli import diagnose
from mcd.report.render import build_incident

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def sample_text() -> str:
    js = (WEB / "sample.js").read_text(encoding="utf-8")
    m = re.search(r"window\.MCD_SAMPLE = (\"(?:[^\"\\]|\\.)*\");", js, re.S)
    assert m, "sample.js does not define window.MCD_SAMPLE"
    return json.loads(m.group(1))


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_committed_diagnosis_matches_a_fresh_run(lang: str) -> None:
    path = WEB / f"sample-diagnosis.{lang}.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    rep, findings, triage = diagnose(None, sample_text(), source="sample", lang=lang)
    fresh = build_incident(rep, findings, triage)
    assert committed == fresh, (
        f"sample-diagnosis.{lang}.json is stale: run tools/make_web_sample.py")


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_sample_still_proves_the_attribution(lang: str) -> None:
    doc = json.loads((WEB / f"sample-diagnosis.{lang}.json").read_text(encoding="utf-8"))
    assert doc["findings"], "a sample with no findings is not a demo"
    assert doc["triage"] and doc["triage"]["suspects"]
    top = doc["triage"]["suspects"][0]
    assert top["modid"] == "lithium"
    assert top["confidence"] >= 0.9


def test_the_sample_carries_no_local_paths() -> None:
    for lang in ("zh", "en"):
        raw = (WEB / f"sample-diagnosis.{lang}.json").read_text(encoding="utf-8")
        assert "sample" == json.loads(raw)["source"]
        assert "C:\\" not in raw and "Users/" not in raw


def test_both_languages_describe_the_same_findings() -> None:
    zh = json.loads((WEB / "sample-diagnosis.zh.json").read_text(encoding="utf-8"))
    en = json.loads((WEB / "sample-diagnosis.en.json").read_text(encoding="utf-8"))
    assert [f["rule_id"] for f in zh["findings"]] == [f["rule_id"] for f in en["findings"]]
    assert ([s["modid"] for s in zh["triage"]["suspects"]]
            == [s["modid"] for s in en["triage"]["suspects"]])
