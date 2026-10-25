"""GitHub Action glue (ROADMAP 1C.1): diagnose a crash report posted to an issue.

The diagnosis itself is a pure function (:func:`mcd.cli.diagnose`); this module
is the *application* layer around it and does exactly three things:

1. work out **which** report to diagnose -- a file, a mclo.gs/raw URL, or the
   crash text inside an issue body (fenced block, inline paste, or a link the
   extractor already knows how to follow);
2. render the normal Markdown report;
3. keep **one** comment updated on the issue instead of posting a new one on
   every edit.

Deliberate limits:

- **stdlib only** (urllib), so the action needs nothing beyond the package.
- **Idempotent comments.** The comment carries :data:`MARKER`; a re-run edits
  that comment. Issue threads get noisy fast otherwise -- and an `edited`
  trigger would otherwise append a fresh diagnosis per typo fix.
- **Commenting failures never hide the diagnosis.** A token without
  ``issues: write`` is a workflow-config problem, not a diagnosis failure; the
  markdown is already on stdout and in the step summary, so we warn loudly and
  exit 0 unless ``--fail-on`` says otherwise.
- **No report, no comment.** Chatter that merely triggers the workflow (a
  feature request, a "thanks!") must not get a bot reply; we exit 0 and report
  ``found=false``.

Entry point: ``python -m mcd.action`` (see ``action.yml`` at the repo root).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .cli import VERSION, diagnose
from .extract import extract, fetch_log
from .model import Finding, Severity
from .parser.report import read_report_text
from .report.render import render_json, render_markdown

# Hidden marker that makes the comment idempotent. GitHub renders HTML
# comments as nothing, so it is invisible to the reader.
MARKER = "<!-- mc-crash-doctor:diagnosis -->"

# GitHub's hard limit is 65536 characters. Leave headroom for the marker and
# the footer, which are appended after truncation.
COMMENT_LIMIT = 60_000

# Severity that counts as "this is a real crash" for --fail-on.
FAIL_ON = {
    "never": None,
    "error": Severity.ERROR,
    "fatal": Severity.FATAL,
}


class GitHubError(RuntimeError):
    """A GitHub API call failed (auth, permissions, network, rate limit)."""


# --------------------------------------------------------------------------
# input resolution
# --------------------------------------------------------------------------
@dataclass
class Source:
    """Where the text we are about to diagnose came from."""

    text: str
    label: str          # shown in the report: "issue #12", a path, a URL
    origin: str = ""    # "inline:fenced" | "mclo.gs:abc" | "path" | ...


def source_from_issue(body: str, *, number: int | None = None,
                      follow_links: bool = True,
                      pat: str | None = None) -> Source | None:
    """Pull the best crash text out of an issue body, or None if there is none.

    ``follow_links`` costs network calls (mclo.gs / gist / pastebin); the
    workflow leaves it on, tests turn it off.
    """
    ex = extract(body or "", follow_links=follow_links, pat=pat)
    label = f"issue #{number}" if number else "issue body"

    # Prefer an explicit fenced block: it is the log on its own, whereas the
    # whole-body candidate also carries the reporter's prose (and is longer,
    # so ``best`` would pick it). Longest fenced block wins -- a report is
    # bigger than the config snippet people paste next to it.
    fenced = [(t, s) for t, s in zip(ex.texts, ex.sources)
              if s == "inline:fenced"]
    if fenced:
        text, origin = max(fenced, key=lambda p: len(p[0]))
        return Source(text, label, origin)

    best = ex.best
    if not best:
        return None
    # `best` is the longest candidate; report which channel it came from so
    # the comment can say "diagnosed the mclo.gs link", not just "issue body".
    idx = ex.texts.index(best) if best in ex.texts else 0
    return Source(best, label, ex.sources[idx] if idx < len(ex.sources) else "")


def source_from_path(path: str | Path) -> Source | None:
    p = Path(path)
    if not p.is_file():
        return None
    # Same encoding ladder as parse_file: this used to decode with
    # errors="replace" behind a two-encoding guess, so a cp1252 report reached
    # the rules with U+FFFD sprinkled through it and silently matched nothing.
    return Source(read_report_text(p), str(p), "path")


def source_from_url(url: str) -> Source | None:
    text = fetch_log(url)
    if not text:
        return None
    return Source(text, url, "url")


# --------------------------------------------------------------------------
# comment body
# --------------------------------------------------------------------------
def _demote_headings(markdown: str, by: int = 2) -> str:
    """Drop heading levels so the report nests under the comment heading.

    H1 -> H3 etc. Fenced blocks are skipped so a ``#`` inside pasted code is
    never touched (the renderer emits none today, but rules can quote text).
    """
    out: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            rest = stripped[hashes:]
            if rest.startswith(" "):
                level = min(6, hashes + by)
                out.append("#" * level + rest)
                continue
        out.append(line)
    return "\n".join(out)


def worst_severity(findings: list[Finding]) -> Severity | None:
    return max((f.severity for f in findings), default=None)


def _footer(findings: list[Finding], top_suspect, version: str) -> str:
    bits = [f"mc-crash-doctor {version}"]
    if findings:
        sev = worst_severity(findings)
        bits.append(f"{len(findings)} finding{'s' if len(findings) != 1 else ''}"
                    f" (worst: {sev.name.lower()})")
    else:
        bits.append("no rule matched")
    if top_suspect is not None:
        bits.append(f"top suspect `{top_suspect.modid}` "
                    f"{top_suspect.confidence:.0%}")
    return "<sub>" + " · ".join(bits) + "</sub>"


def build_comment(markdown: str, *, findings: list[Finding], triage,
                  version: str = VERSION,
                  limit: int = COMMENT_LIMIT) -> str:
    """Wrap the rendered report in an idempotent, size-capped comment."""
    top = triage.suspects[0] if (triage and triage.suspects) else None
    footer = _footer(findings, top, version)
    body = _demote_headings(markdown).strip()

    # The marker and footer must survive truncation -- the first keeps re-runs
    # idempotent, the second tells the reader the text is cut.
    budget = limit - len(MARKER) - len(footer) - 200
    if len(body) > budget > 0:
        body = (body[:budget].rstrip()
                + "\n\n_[truncated to fit GitHub's comment size limit]_")
    return f"{MARKER}\n{body}\n\n---\n{footer}\n"


# --------------------------------------------------------------------------
# GitHub API (minimal, stdlib)
# --------------------------------------------------------------------------
class GitHub:
    """Just enough of the REST API: read an issue, list/create/edit comments."""

    def __init__(self, token: str, repo: str, api_url: str | None = None):
        self.token = token
        self.repo = repo
        self.api_url = (api_url or os.environ.get("GITHUB_API_URL")
                        or "https://api.github.com").rstrip("/")

    def _call(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"mc-crash-doctor/{VERSION}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", errors="replace")
            raise GitHubError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GitHubError(f"{method} {path} -> {e}") from None
        return json.loads(raw) if raw.strip() else None

    # -- issues ------------------------------------------------------------
    def issue(self, number: int) -> dict:
        return self._call("GET", f"/repos/{self.repo}/issues/{number}") or {}

    def comments(self, number: int, *, pages: int = 3) -> list[dict]:
        """First few pages of comments -- enough to find our own marker.

        A thread with >300 comments will get a second bot comment rather than
        none; that is a better failure mode than scanning forever.
        """
        out: list[dict] = []
        for page in range(1, pages + 1):
            batch = self._call(
                "GET",
                f"/repos/{self.repo}/issues/{number}/comments"
                f"?per_page=100&page={page}") or []
            out.extend(batch)
            if len(batch) < 100:
                break
        return out

    def create_comment(self, number: int, body: str) -> dict:
        return self._call("POST",
                          f"/repos/{self.repo}/issues/{number}/comments",
                          {"body": body}) or {}

    def update_comment(self, comment_id: int, body: str) -> dict:
        return self._call("PATCH",
                          f"/repos/{self.repo}/issues/comments/{comment_id}",
                          {"body": body}) or {}

    def upsert_comment(self, number: int, body: str) -> tuple[str, int | None]:
        """Create the diagnosis comment, or edit the one we posted before.

        Returns ``("created"|"updated", comment_id)``.
        """
        for c in self.comments(number):
            if MARKER in (c.get("body") or ""):
                cid = c.get("id")
                self.update_comment(cid, body)
                return "updated", cid
        created = self.create_comment(number, body)
        return "created", created.get("id")


# --------------------------------------------------------------------------
# runner plumbing
# --------------------------------------------------------------------------
def load_event(path: str | os.PathLike | None = None) -> dict:
    """Read the workflow event payload (empty when not running in Actions)."""
    p = path or os.environ.get("GITHUB_EVENT_PATH")
    if not p:
        return {}
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_outputs(pairs: dict[str, object]) -> None:
    """Append ``key=value`` pairs to ``$GITHUB_OUTPUT`` (no-op outside CI)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in pairs.items():
            # One line per output: GitHub parses the first '=' only, so values
            # containing '=' are fine, but newlines are not. Callers pass
            # scalars only.
            f.write(f"{k}={'' if v is None else v}\n")


def write_summary(markdown: str, *, limit: int = 900_000) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(markdown[:limit])


def _event_issue(ev: dict) -> dict:
    issue = ev.get("issue") or {}
    return issue if isinstance(issue, dict) else {}


def _resolve_source(args, gh: GitHub | None, ev: dict) -> Source | None:
    """Input precedence: explicit path > explicit URL > issue (event or --issue)."""
    if args.path:
        return source_from_path(args.path)
    if args.url:
        return source_from_url(args.url)

    issue = _event_issue(ev)
    number = args.issue or issue.get("number")
    if not number:
        return None

    body = issue.get("body")
    if body is None and gh is not None:
        body = gh.issue(int(number)).get("body")
    if not body:
        return None
    return source_from_issue(body, number=int(number),
                             follow_links=args.follow_links, pat=args.token)


def _report_payload(args, ev: dict):
    """Diagnose whatever the flags point at; None when there is nothing to do."""
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or ""
    token = args.token or os.environ.get("GITHUB_TOKEN") or ""
    gh = GitHub(token, repo) if (token and repo) else None

    src = _resolve_source(args, gh, ev)
    if src is None:
        return None

    return diagnose(None, src.text, source=src.label)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mcd-action",
        description="Diagnose a Minecraft crash report from a file, URL or "
                    "GitHub issue and (optionally) comment the result.",
    )
    ap.add_argument("--path", help="crash report / log file")
    ap.add_argument("--url", help="mclo.gs share link or raw log URL")
    ap.add_argument("--issue", type=int, help="issue number to read the report from")
    ap.add_argument("--event", help="event payload path (default $GITHUB_EVENT_PATH)")
    ap.add_argument("--repo", default=None, help="owner/name (default $GITHUB_REPOSITORY)")
    ap.add_argument("--token", default=None, help="API token (default $GITHUB_TOKEN)")
    ap.add_argument("--comment", action="store_true",
                    help="post or update the diagnosis comment on the issue")
    ap.add_argument("--no-follow-links", dest="follow_links", action="store_false",
                    help="do not dereference mclo.gs / gist / pastebin links")
    ap.add_argument("--fail-on", choices=sorted(FAIL_ON), default="never",
                    help="exit 1 when a finding reaches this severity")
    ap.add_argument("--json", action="store_true", help="emit the Incident JSON")
    ap.add_argument("--out", help="also write the rendered report to this file")
    args = ap.parse_args(argv)

    ev = load_event(args.event)
    payload = _report_payload(args, ev)
    issue_no = args.issue or _event_issue(ev).get("number")

    if payload is None:
        # Nothing that looks like a report. Quietly succeed: a workflow that
        # triggers on every issue must not answer chatter.
        print("mc-crash-doctor: no crash report found in the input -- nothing to do",
              file=sys.stderr)
        write_outputs({"found": "false", "findings": "0",
                       "worst_severity": "none", "suspect": "",
                       "commented": "false"})
        return 0

    rep, findings, tri = payload
    buf = io.StringIO()
    if args.json:
        render_json(rep, findings, tri, buf)
    else:
        render_markdown(rep, findings, tri, buf)
    rendered = buf.getvalue()

    print(rendered)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    write_summary(rendered)

    worst = worst_severity(findings)
    top = tri.suspects[0] if (tri and tri.suspects) else None
    outputs = {
        "found": "true",
        "findings": len(findings),
        "worst_severity": worst.name.lower() if worst else "none",
        "suspect": top.modid if top else "",
        "suspect_confidence": f"{top.confidence:.0%}" if top else "",
        "commented": "false",
    }

    if args.comment and issue_no:
        body = build_comment(rendered, findings=findings, triage=tri)
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or ""
        token = args.token or os.environ.get("GITHUB_TOKEN") or ""
        if not (repo and token):
            print("mc-crash-doctor: --comment needs a token and a repo "
                  "($GITHUB_TOKEN / $GITHUB_REPOSITORY) -- skipped",
                  file=sys.stderr)
        else:
            gh = GitHub(token, repo)
            try:
                action, cid = gh.upsert_comment(int(issue_no), body)
                outputs["commented"] = "true"
                print(f"mc-crash-doctor: comment {action} on issue #{issue_no}"
                      f"{f' (id {cid})' if cid else ''}", file=sys.stderr)
            except GitHubError as e:
                # Do not fail the run: the report is already in the log and the
                # step summary. A missing `issues: write` permission is a
                # workflow bug, and it must be visible, not silent.
                print(f"mc-crash-doctor: could not comment: {e}", file=sys.stderr)

    write_outputs(outputs)

    threshold = FAIL_ON[args.fail_on]
    if threshold is not None and worst is not None and worst >= threshold:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
