#!/usr/bin/env python
"""End-to-end verification of the web app in a REAL browser (headless Edge
over CDP). This is the acceptance check for ROADMAP phase 0.1:

  1. open http://127.0.0.1:8765/index.html
  2. wait until the Pyodide engine reports ready (go-button enabled)
  3. click "Try a sample" (loads the redacted real report from sample.js)
  4. read the rendered DOM back: diagnosis card, suspect chips, findings
  5. assert the watchdog diagnosis + lithium attribution actually rendered

Expects:
  - python -m http.server 8765 serving web/
  - headless Edge with --remote-debugging-port=9222

Exit 0 = verified, 1 = failed. Temporary tool, kept out of the pytest suite
(needs a live browser + server).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

import websocket  # websocket-client

CDP_HTTP = "http://127.0.0.1:9222"
PAGE = "http://127.0.0.1:8765/index.html"
READY_TIMEOUT = 120      # pyodide CDN boot + micropip install
DIAGNOSE_TIMEOUT = 120   # 75 KB sample through the WASM engine


def new_tab(url: str) -> str:
    req = urllib.request.Request(f"{CDP_HTTP}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["webSocketDebuggerUrl"]


class CDP:
    def __init__(self, ws_url: str):
        # suppress_origin: newer Edge/Chrome reject CDP websockets that carry
        # an Origin header unless started with --remote-allow-origins.
        self.ws = websocket.create_connection(ws_url, timeout=30,
                                              max_size=None,
                                              suppress_origin=True)
        self.n = 0
        self.console: list[str] = []
        self.errors: list[str] = []
        self.send("Runtime.enable")
        self.send("Log.enable")
        self.send("Page.enable")

    def send(self, method: str, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method,
                                 "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self._event(msg)

    def _event(self, msg: dict) -> None:
        m = msg.get("method", "")
        p = msg.get("params", {})
        if m == "Runtime.consoleAPICalled":
            txt = " ".join(str(a.get("value", a.get("description", "")))
                           for a in p.get("args", []))
            self.console.append(f"[{p.get('type')}] {txt}")
        elif m == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            self.errors.append(d.get("text", "") + " " +
                               str(d.get("exception", {}).get("description", ""))[:200])
        elif m == "Log.entryAdded":
            e = p.get("entry", {})
            if e.get("level") == "error":
                self.errors.append(f"{e.get('source')}: {e.get('text')[:200]}")

    def drain(self, seconds: float = 0.5) -> None:
        self.ws.settimeout(seconds)
        try:
            while True:
                self._event(json.loads(self.ws.recv()))
        except Exception:
            pass
        finally:
            self.ws.settimeout(30)

    def js(self, expr: str):
        r = self.send("Runtime.evaluate", expression=expr,
                      returnByValue=True, awaitPromise=False)
        if "exceptionDetails" in r:
            raise RuntimeError("page JS error: " +
                               str(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main() -> int:
    ws_url = new_tab(PAGE)
    cdp = CDP(ws_url)
    print(f"opened {PAGE}")

    # 1. engine boot
    t0 = time.time()
    status = ""
    while time.time() - t0 < READY_TIMEOUT:
        cdp.drain(1.0)
        status = cdp.js("document.getElementById('status').textContent") or ""
        enabled = cdp.js("!document.getElementById('go').disabled")
        if enabled:
            break
        if "failed" in status.lower():
            break
    boot = time.time() - t0
    print(f"engine status after {boot:.0f}s: {status!r}")
    if "ready" not in status.lower():
        print("FAIL: engine never became ready")
        for e in cdp.errors[:5]:
            print("  page error:", e)
        for c in cdp.console[-5:]:
            print("  console:", c)
        return 1

    # 2. sample must be the redacted real report (not the tiny fallback)
    sample_len = cdp.js("(window.MCD_SAMPLE || '').length")
    print(f"MCD_SAMPLE loaded: {sample_len} chars")
    if not sample_len or sample_len < 10000:
        print("FAIL: sample.js missing or too small (fallback would hide a regression)")
        return 1

    # 3. click "Try a sample"
    cdp.js("document.getElementById('sample').click()")
    t0 = time.time()
    cards = 0
    while time.time() - t0 < DIAGNOSE_TIMEOUT:
        cdp.drain(1.0)
        cards = cdp.js("document.querySelectorAll('#out .card').length") or 0
        st = cdp.js("document.getElementById('status').textContent") or ""
        if cards and ("finding" in st or "no rule" in st):
            break
    print(f"diagnosis rendered after {time.time()-t0:.0f}s: {cards} cards")

    # 4. read the rendered result back
    result = cdp.js("""(() => {
      const out = document.getElementById('out');
      const cards = [...out.querySelectorAll('.card h2')].map(h => h.textContent.trim());
      const suspects = [...out.querySelectorAll('.suspect b')].map(b => b.textContent.trim());
      const sevs = [...out.querySelectorAll('.sev')].map(s => s.textContent.trim());
      const titles = [...out.querySelectorAll('.finding h3')].map(h => h.textContent.trim().replace(/^[A-Z]+\\s*/, ''));
      const fixes = out.querySelectorAll('.finding li').length;
      const evidence = out.querySelectorAll('.evidence').length;
      const status = document.getElementById('status').textContent;
      return {cards, suspects, sevs, titles, fixes, evidence, status};
    })()""")
    print("\nrendered DOM:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 5. acceptance assertions
    checks = [
        ("suspect chip 'lithium' rendered",
         any("lithium" in s.lower() for s in result["suspects"])),
        ("watchdog finding rendered",
         any("watchdog" in t.lower() or "hung" in t.lower() for t in result["titles"])),
        ("a FATAL/ERROR severity badge shown",
         any(s in ("FATAL", "ERROR") for s in result["sevs"])),
        ("fix steps rendered", result["fixes"] >= 1),
        ("evidence lines rendered", result["evidence"] >= 1),
        ("status line reports findings", "finding" in result["status"].lower()),
    ]
    print("\nacceptance:")
    ok = True
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok &= passed

    if cdp.errors:
        print("\npage errors (should be empty):")
        for e in cdp.errors[:5]:
            print("  !", e)
        ok = False

    cdp.close()
    print("\nRESULT:", "VERIFIED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
