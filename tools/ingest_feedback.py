#!/usr/bin/env python
"""Turn a feedback issue into a redacted corpus candidate.

The loop this closes: a user presses "结论不对？" (or runs --feedback), the issue
arrives with the summary pre-filled, a maintainer pastes the report, and this
script moves that report into corpus/inbox/ -- redacted, hashed, and recorded
with where it came from. Nothing enters corpus/index.jsonl automatically: a
human still decides whether it becomes evidence for a rule.

    python tools/ingest_feedback.py issue.md --issue https://github.com/.../issues/123
    pbpaste | python tools/ingest_feedback.py - --issue ...

Why not parse the issue straight into the index: the issue body is free text by
a stranger, and the index is the thing every published number is computed from.
An inbox with a human in the middle is slower and correct.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from harvest_corpus import redact  # noqa: E402
from export_corpus_sample import harden  # noqa: E402

FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)


def extract_report(body: str) -> str:
    """The fenced block if there is one, else everything after '## The report'."""
    blocks = FENCE.findall(body)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    m = re.search(r"^##\s*The report\s*$", body, re.M | re.I)
    if m:
        return body[m.end():].strip() + "\n"
    # No fence and no section: the body is the issue prose, not a report.
    # Ingesting it would put a paragraph of English into the corpus.
    return ""


def ingest(body: str, *, issue: str = "", inbox: Path | None = None) -> Path:
    text = extract_report(body)
    clean = harden(redact(text))
    if not clean.strip():
        raise ValueError("no report text found in the issue body")
    out_dir = inbox or (ROOT / "corpus" / "inbox")
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}-{digest}.txt"
    header = (f"# source: {issue or 'local'}\n"
              f"# sha256: {digest}\n"
              f"# ingested: {stamp}\n")
    path.write_text(header + clean, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("body", help="issue body file, or - for stdin")
    ap.add_argument("--issue", default="", help="issue URL, recorded in the header")
    ap.add_argument("--inbox", default=None)
    args = ap.parse_args()

    raw = sys.stdin.read() if args.body == "-" else Path(args.body).read_text(
        encoding="utf-8", errors="replace")
    try:
        path = ingest(raw, issue=args.issue, inbox=Path(args.inbox) if args.inbox else None)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"wrote {path}")
    print("next: look at it, then either write a rule (tools/suggest_rules.py) "
          "or delete it -- nothing enters corpus/index.jsonl on its own")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
