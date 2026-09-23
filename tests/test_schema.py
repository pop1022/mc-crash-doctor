"""Incident schema conformance (ROADMAP 1A.1).

The Incident document (mcd.report.render.build_incident) is the single source
of truth shared by the CLI, the browser app, and any future API. This test
pins it to data/schemas/incident.v1.json so the contract can't silently
drift -- e.g. the CLI and web app were found building the doc inline and the
web copy was already missing schema_version before this landed.

Validates every ground-truth + synthetic fixture, plus a sample of each real
corpus. Skips (not fails) if the optional `jsonschema` package is absent, so
the core suite stays runnable without it; CI installs it.

    pytest tests/test_schema.py -v
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.cli import diagnose                       # noqa: E402
from mcd.report.render import SCHEMA_VERSION, build_incident  # noqa: E402

try:
    import jsonschema
    from jsonschema import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:            # pragma: no cover
    HAS_JSONSCHEMA = False

SCHEMA_PATH = ROOT / "data" / "schemas" / "incident.v1.json"

pytestmark = pytest.mark.skipif(
    not HAS_JSONSCHEMA, reason="jsonschema not installed (pip install jsonschema)")


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)   # the schema itself is valid
    return Draft202012Validator(schema)


def _incident(path: str) -> dict:
    rep, findings, t = diagnose(path, None)
    return build_incident(rep, findings, t)


def _corpus_files() -> list[str]:
    # every fixture, plus a bounded sample of the big corpora
    files = sorted(glob.glob(str(ROOT / "tests/fixtures/**/*.txt"), recursive=True))
    for pat, limit in [("corpus/aternos/**/*.log", 25),
                       ("corpus/github/**/*.crash.txt", 40)]:
        hits = sorted(glob.glob(str(ROOT / pat), recursive=True))
        files.extend(hits[:limit])
    return files


def test_schema_version_matches_code(validator):
    doc = _incident(str(ROOT / "tests/fixtures/ground-truth/crash-2026-09-08_22.42.32-server.txt"))
    assert doc["schema_version"] == SCHEMA_VERSION == "1.0"


def test_known_incident_conforms(validator):
    """The watchdog ground-truth report must validate and carry its verdict."""
    doc = _incident(str(ROOT / "tests/fixtures/ground-truth/crash-2026-09-08_22.42.32-server.txt"))
    errors = sorted(validator.iter_errors(doc), key=lambda e: e.path)
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
    assert doc["summary"]["loader"] == "forge"
    assert any(f["rule_id"] == "hang.watchdog" for f in doc["findings"])
    assert doc["triage"]["suspects"][0]["modid"] == "lithium"


def test_no_findings_still_conforms(validator):
    """An empty/garbage input produces a valid doc with zero findings."""
    from mcd.parser.report import parse_text
    from mcd.rules.engine import RuleSet, run_rules
    rep = parse_text("this is not a crash report at all")
    findings = run_rules(rep, RuleSet.load())
    doc = build_incident(rep, findings, None)
    assert doc["findings"] == []
    assert doc["triage"] is None
    errors = list(validator.iter_errors(doc))
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("path", _corpus_files(), ids=lambda p: Path(p).name)
def test_corpus_incidents_conform(validator, path):
    doc = _incident(path)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, f"{Path(path).name}:\n" + "\n".join(
        f"  {list(e.path)}: {e.message}" for e in errors[:5])
