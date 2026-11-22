"""Feedback issues become redacted inbox candidates, never index rows."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from ingest_feedback import extract_report, ingest  # noqa: E402

ISSUE = """### 引擎看到的东西
- 平台：forge 47.4.16

### 我不同意的地方
应该是另一个模组

### 报告
```
---- Minecraft Crash Report ----
At 10.0.0.9 from C:\\Users\\bob\\.minecraft\\mods
java.lang.OutOfMemoryError: Java heap space
```
"""


def test_extract_prefers_the_longest_fence() -> None:
    body = "```\nshort\n```\n```\n" + "x" * 50 + "\n```\n"
    assert "x" * 50 in extract_report(body)


def test_ingest_redacts_and_records_source(tmp_path: Path) -> None:
    path = ingest(ISSUE, issue="https://example.invalid/issues/1", inbox=tmp_path)
    body = path.read_text(encoding="utf-8")
    assert "10.0.0.9" not in body
    assert "bob" not in body
    assert "https://example.invalid/issues/1" in body
    assert "OutOfMemoryError" in body


def test_empty_body_is_a_clean_error(tmp_path: Path) -> None:
    try:
        ingest("no report here", inbox=tmp_path)
    except ValueError as e:
        assert "no report text" in str(e)
    else:                                            # pragma: no cover
        raise AssertionError("expected ValueError")
