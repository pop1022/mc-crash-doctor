"""GitHub Action glue (ROADMAP 1C.1): source resolution, idempotent comments,
outputs, and an end-to-end run against a fake GitHub API.

Nothing here touches the network: the API is a local HTTP server, and the
issue body is read from a synthesised event payload.

    pytest tests/test_action.py -v
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd import action  # noqa: E402

GT = ROOT / "tests" / "fixtures" / "ground-truth"
WATCHDOG = GT / "crash-2026-09-08_22.42.32-server.txt"   # 266-mod hang kill


# --------------------------------------------------------------------------
# fake GitHub API
# --------------------------------------------------------------------------
class FakeAPI:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.comments: list[dict] = []
        self.issue_body = ""
        self._next_id = 1000

    def add_comment(self, body: str, user: str = "someone") -> dict:
        c = {"id": self._next_id, "body": body, "user": {"login": user}}
        self._next_id += 1
        self.comments.append(c)
        return c

    def posts(self) -> list[dict]:
        return [p for m, _, p in self.calls if m == "POST"]


class _Handler(BaseHTTPRequestHandler):
    api: FakeAPI = None  # set by the fixture

    def log_message(self, *a):  # keep pytest output clean
        pass

    def _reply(self, code: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n)) if n else None
        url = urllib.parse.urlsplit(self.path)
        self.api.calls.append((self.command, url.path, payload))
        parts = url.path.strip("/").split("/")   # repos/o/r/issues/...
        api = self.api

        if self.command == "GET" and url.path.endswith("/comments"):
            self._reply(200, api.comments)
        elif self.command == "GET" and parts[-2] == "issues":
            self._reply(200, {"number": int(parts[-1]), "body": api.issue_body})
        elif self.command == "POST" and parts[-1] == "comments":
            self._reply(201, api.add_comment(payload["body"], user="github-actions"))
        elif self.command == "PATCH" and "comments" in parts:
            cid = int(parts[-1])
            for c in api.comments:
                if c["id"] == cid:
                    c["body"] = payload["body"]
                    self._reply(200, c)
                    return
            self._reply(404, {"message": "Not Found"})
        else:
            self._reply(404, {"message": "Not Found"})

    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle


@pytest.fixture()
def fake_api(monkeypatch):
    """A live local API server plus a proxy-free environment."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    api = FakeAPI()
    handler = type("H", (_Handler,), {"api": api})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GITHUB_API_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    try:
        yield api
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _issue_event(body: str, number: int = 12) -> dict:
    return {
        "action": "opened",
        "issue": {"number": number, "body": body,
                  "user": {"login": "player", "type": "User"}},
        "repository": {"full_name": "pop1022/mc-crash-doctor"},
    }


def _write_event(tmp_path: Path, body: str, number: int = 12) -> Path:
    p = tmp_path / "event.json"
    p.write_text(json.dumps(_issue_event(body, number)), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# source resolution
# --------------------------------------------------------------------------
def test_source_from_issue_finds_fenced_report():
    report = WATCHDOG.read_text(encoding="utf-8")
    body = ("Server keeps dying after 5 minutes. Config is below.\n\n"
            f"```\n{report}\n```\n\nNothing else to add, thanks!\n")
    src = action.source_from_issue(body, number=7, follow_links=False)
    assert src is not None
    assert "Minecraft Crash Report" in src.text
    assert src.label == "issue #7"
    assert src.origin == "inline:fenced"


def test_source_from_issue_ignores_chatter():
    body = ("Feature request: could you add a `--yaml` output mode?\n\n"
            "It would help my CI. Thanks!\n")
    assert action.source_from_issue(body, number=3, follow_links=False) is None


def test_source_from_issue_reads_inline_log():
    log_lines = "\n".join(
        f"[12:0{i}:00] [Server thread/INFO]: tick {i} took 4200ms" for i in range(6))
    body = f"here is my log\n{log_lines}\n"
    src = action.source_from_issue(body, follow_links=False)
    assert src is not None and "took 4200ms" in src.text


# --------------------------------------------------------------------------
# comment body
# --------------------------------------------------------------------------
def test_comment_is_idempotent_and_reads_well():
    report = WATCHDOG.read_text(encoding="utf-8")
    rep, findings, tri = action.diagnose(None, report, source="issue #1")
    body = action.build_comment("# Minecraft crash diagnosis\n\n## Findings\n",
                                findings=findings, triage=tri)
    assert body.startswith(action.MARKER)
    assert findings, "fixture must produce findings"
    # headings nest under the comment's own heading
    assert "\n### Minecraft crash diagnosis" in body
    assert "\n#### Findings" in body
    top = tri.suspects[0].modid
    assert f"top suspect `{top}`" in body
    assert str(len(findings)) in body


def test_comment_truncates_but_keeps_marker_and_footer():
    body = action.build_comment("# t\n" + ("x" * 10_000 + "\n") * 20,
                                findings=[], triage=None, limit=2_000)
    assert len(body) <= 2_000
    assert body.startswith(action.MARKER)
    assert "truncated" in body
    assert body.rstrip().endswith("</sub>")


def test_demote_headings_leaves_code_fences_alone():
    md = "# Top\n\n## Sub\n\n```\n# not a heading\n```\n"
    out = action._demote_headings(md)
    assert out.startswith("### Top")
    assert "\n#### Sub" in out
    assert "# not a heading" in out


# --------------------------------------------------------------------------
# idempotent comment upsert
# --------------------------------------------------------------------------
def test_upsert_creates_then_updates_same_comment(fake_api):
    gh = action.GitHub("t0ken", "pop1022/mc-crash-doctor")
    assert gh.upsert_comment(12, action.MARKER + "\nfirst")[0] == "created"
    assert len(fake_api.comments) == 1

    kind, cid = gh.upsert_comment(12, action.MARKER + "\nsecond")
    assert kind == "updated"
    assert len(fake_api.comments) == 1, "a re-run must not add a second comment"
    assert fake_api.comments[0]["body"].endswith("second")
    assert fake_api.comments[0]["id"] == cid


def test_upsert_ignores_other_people_comments(fake_api):
    fake_api.add_comment("Thanks for the report! (no marker here)")
    gh = action.GitHub("t0ken", "pop1022/mc-crash-doctor")
    assert gh.upsert_comment(12, action.MARKER + "\ndiag")[0] == "created"
    assert len(fake_api.comments) == 2
    assert fake_api.comments[0]["body"].startswith("Thanks")


def test_api_errors_surface_as_github_error(fake_api, monkeypatch):
    gh = action.GitHub("t0ken", "pop1022/mc-crash-doctor",
                       api_url="http://127.0.0.1:1")   # nothing listening
    with pytest.raises(action.GitHubError):
        gh.issue(12)


# --------------------------------------------------------------------------
# paste-link handling (shared by `--url` and issue-body link following)
# --------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1) -> bytes:
        return self.payload


@pytest.mark.parametrize("url", [
    "https://mclo.gs/6cWndzQ",           # the documented share link (one segment)
    "https://mclo.gs/o/6cWndzQ",         # older two-segment shape
    "https://api.mclo.gs/1/raw/6cWndzQ",  # already the raw API form
    "mclo.gs/6cWndzQ",                   # pasted without a scheme
])
def test_fetch_log_resolves_every_mclogs_link_shape(monkeypatch, url):
    """Regression: the old regex demanded two path segments, so the share link
    form advertised in README (`--url https://mclo.gs/<id>`) fetched the HTML
    page instead of the log."""
    seen = {}

    def fake_urlopen(req, timeout=30):
        seen["url"] = req.full_url
        return _FakeResponse(b"---- Minecraft Crash Report ----\n")

    monkeypatch.setattr("mcd.extract.urllib.request.urlopen", fake_urlopen)
    assert action.fetch_log(url).startswith("---- Minecraft Crash Report ----")
    assert seen["url"] == "https://api.mclo.gs/1/raw/6cWndzQ"


def test_issue_body_link_is_followed(monkeypatch):
    """A bare mclo.gs link in the issue must be dereferenced and preferred."""
    report = WATCHDOG.read_text(encoding="utf-8")
    monkeypatch.setattr("mcd.extract.deref_mclogs",
                        lambda lid: report if lid == "6cWndzQ" else None)
    monkeypatch.setattr("mcd.extract.time.sleep", lambda s: None)

    src = action.source_from_issue(
        "Server crashed, full log here: https://mclo.gs/6cWndzQ\n",
        number=9, follow_links=True)
    assert src is not None
    assert src.origin == "mclo.gs:6cWndzQ"
    assert "ServerHangWatchdog" in src.text


# --------------------------------------------------------------------------
# end-to-end: event in, comment + outputs out
# --------------------------------------------------------------------------
def test_end_to_end_diagnoses_issue_and_writes_outputs(
        fake_api, tmp_path, monkeypatch, capsys):
    body = "My server dies every few hours:\n\n```\n" \
        + WATCHDOG.read_text(encoding="utf-8") + "\n```\n"
    event = _write_event(tmp_path, body, number=12)
    out_file = tmp_path / "out.txt"
    summary = tmp_path / "summary.md"
    for k, v in (("GITHUB_EVENT_PATH", str(event)),
                 ("GITHUB_OUTPUT", str(out_file)),
                 ("GITHUB_STEP_SUMMARY", str(summary)),
                 ("GITHUB_REPOSITORY", "pop1022/mc-crash-doctor"),
                 ("GITHUB_TOKEN", "t0ken")):
        monkeypatch.setenv(k, v)

    rc = action.main(["--comment"])
    assert rc == 0

    printed = capsys.readouterr().out
    assert "Minecraft crash diagnosis" in printed

    outputs = dict(line.split("=", 1)
                   for line in out_file.read_text(encoding="utf-8").splitlines())
    assert outputs["found"] == "true"
    assert int(outputs["findings"]) >= 1
    assert outputs["worst_severity"] == "fatal"
    assert outputs["suspect"] == "lithium"
    assert outputs["commented"] == "true"

    assert len(fake_api.comments) == 1
    comment = fake_api.comments[0]["body"]
    assert comment.startswith(action.MARKER)
    assert "lithium" in comment
    assert summary.read_text(encoding="utf-8").startswith("# Minecraft crash")

    # Re-running (an `edited` trigger) updates the same comment.
    assert action.main(["--comment"]) == 0
    assert len(fake_api.comments) == 1
    assert len(fake_api.posts()) == 1


def test_chatter_issue_exits_clean_without_comment(
        fake_api, tmp_path, monkeypatch, capsys):
    event = _write_event(tmp_path, "Could you support 1.21.5? Thanks.", number=13)
    out_file = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "pop1022/mc-crash-doctor")
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")

    assert action.main(["--comment"]) == 0
    assert fake_api.posts() == []
    outputs = dict(line.split("=", 1)
                   for line in out_file.read_text(encoding="utf-8").splitlines())
    assert outputs["found"] == "false"
    assert outputs["commented"] == "false"
    assert "nothing to do" in capsys.readouterr().err


def test_comment_failure_does_not_fail_the_run(
        fake_api, tmp_path, monkeypatch, capsys):
    body = "```\n" + WATCHDOG.read_text(encoding="utf-8") + "\n```\n"
    event = _write_event(tmp_path, body, number=14)
    out_file = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "pop1022/mc-crash-doctor")
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    # A 403 is what a token without `issues: write` actually returns.
    monkeypatch.setattr(action.GitHub, "comments",
                        lambda self, n, **kw: (_ for _ in ()).throw(
                            action.GitHubError("POST ... -> HTTP 403: Forbidden")))

    assert action.main(["--comment"]) == 0
    assert "could not comment" in capsys.readouterr().err
    outputs = dict(line.split("=", 1)
                   for line in out_file.read_text(encoding="utf-8").splitlines())
    assert outputs["commented"] == "false"
    assert outputs["found"] == "true"   # the diagnosis still ran


def test_fail_on_threshold(fake_api, tmp_path, monkeypatch):
    body = "```\n" + WATCHDOG.read_text(encoding="utf-8") + "\n```\n"
    event = _write_event(tmp_path, body, number=15)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "pop1022/mc-crash-doctor")

    assert action.main(["--fail-on", "never"]) == 0
    assert action.main(["--fail-on", "fatal"]) == 1


def test_issue_flag_fetches_body_from_api(fake_api, monkeypatch, capsys):
    """Manual dogfood (`workflow_dispatch`, or `mcd-action --issue 12`) has no
    event payload to read the body from, so it must fetch the issue."""
    fake_api.issue_body = "```\n" + WATCHDOG.read_text(encoding="utf-8") + "\n```\n"
    monkeypatch.setenv("GITHUB_REPOSITORY", "pop1022/mc-crash-doctor")
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    monkeypatch.setenv("GITHUB_EVENT_PATH", "/nonexistent/event.json")

    assert action.main(["--issue", "12"]) == 0
    assert any(m == "GET" and p.endswith("/issues/12")
               for m, p, _ in fake_api.calls)
    assert "lithium" in capsys.readouterr().out


def test_path_input_wins_over_event(fake_api, tmp_path, monkeypatch):
    """An explicit --path is a CI gate use case: no issue involved at all."""
    event = _write_event(tmp_path, "unrelated", number=16)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    out_file = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    assert action.main(["--path", str(WATCHDOG)]) == 0
    outputs = dict(line.split("=", 1)
                   for line in out_file.read_text(encoding="utf-8").splitlines())
    assert outputs["found"] == "true"
    assert outputs["suspect"] == "lithium"
    assert fake_api.posts() == []
