#!/usr/bin/env python
"""End-to-end verification of the web app in a REAL browser (headless Edge
over CDP). This is the acceptance check for ROADMAP phase 0.1, extended with
the P0 UX contract and the bilingual UI:

  1. open http://127.0.0.1:8765/index.html
  2. wait until the Pyodide engine reports ready (go-button enabled)
  3. click "用示例试试" / "Try a sample" (loads the redacted real report)
  4. read the rendered DOM back: verdict card, suspect chip, findings
  5. assert the watchdog diagnosis + lithium attribution actually rendered
  6. assert the UX contract: verdict comes first, environment is collapsed,
     copy actions exist, focus lands on the verdict, the status line is live,
     a link is rejected with an explanation, and "busy" disables every control
  7. assert the UI is bilingual: Chinese by default, a toggle that relabels an
     already-rendered result AND a visible notice in place, no missing
     translation keys, and identical key sets in both packs

Expects:
  - python -m http.server 8765 serving web/
  - headless Edge with --remote-debugging-port=9222

Exit 0 = verified, 1 = failed. Temporary tool, kept out of the pytest suite
(needs a live browser + server + a network fetch of the Pyodide CDN).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

import websocket  # websocket-client

CDP_PORT = int(os.environ.get("MCD_CDP_PORT", "9222"))
CDP_HTTP = f"http://127.0.0.1:{CDP_PORT}"
PAGE = "http://127.0.0.1:8765/index.html"
READY_TIMEOUT = 120      # pyodide CDN boot + micropip install
DIAGNOSE_TIMEOUT = 120   # 75 KB sample through the WASM engine

# Severity badges are localized, so accept either script.
SEV_WORDS = ("FATAL", "ERROR", "致命", "错误")


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
        # The server is a plain http.server with no cache headers, so a
        # heuristic-cached app.js would silently verify the PREVIOUS build.
        self.send("Network.enable")
        self.send("Network.setCacheDisabled", cacheDisabled=True)

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
    # Open a blank tab, attach, disable the cache and wipe this origin's
    # storage, THEN navigate: otherwise the page starts loading before we can
    # turn caching off (a stale app.js would make this script verify the
    # previous build) and a language preference left behind by an earlier run
    # would make "Chinese by default" pass or fail depending on history.
    ws_url = new_tab("about:blank")
    cdp = CDP(ws_url)
    cdp.send("Storage.clearDataForOrigin",
             origin="http://127.0.0.1:8765", storageTypes="local_storage")
    cdp.send("Page.navigate", url=PAGE)
    print(f"opened {PAGE}")

    # 1. engine boot -- gated on the button, not on a status string, so the
    # check survives a language change.
    t0 = time.time()
    status = ""
    enabled = False
    while time.time() - t0 < READY_TIMEOUT:
        cdp.drain(1.0)
        status = cdp.js("document.getElementById('status').textContent") or ""
        enabled = bool(cdp.js("!document.getElementById('go').disabled"))
        if enabled:
            break
        if "失败" in status or "failed" in status.lower():
            break
    boot = time.time() - t0
    print(f"engine status after {boot:.0f}s: {status!r}")
    if not enabled:
        print("FAIL: engine never became ready")
        for e in cdp.errors[:5]:
            print("  page error:", e)
        for c in cdp.console[-5:]:
            print("  console:", c)
        return 1

    # A `hidden` PROPERTY is not a hidden ELEMENT: an author display rule wins
    # over the UA's [hidden] rule. Check computed style, not the attribute --
    # this is exactly the bug the screenshot caught (the progress list and a
    # no-op Clear button were still on screen).
    vis = cdp.js("""(() => {
      const d = id => getComputedStyle(document.getElementById(id)).display;
      return {progress: d('progress'), clear: d('clear'), notice: d('notice'),
              logEmpty: !document.getElementById('log').value.length};
    })()""")
    print(f"visibility after boot: {vis}")

    # 2. sample must be the redacted real report (not the tiny fallback)
    sample_len = cdp.js("(window.MCD_SAMPLE || '').length")
    print(f"MCD_SAMPLE loaded: {sample_len} chars")
    if not sample_len or sample_len < 10000:
        print("FAIL: sample.js missing or too small (fallback would hide a regression)")
        return 1

    # 3. click the sample button
    cdp.js("document.getElementById('sample').click()")
    t0 = time.time()
    cards = 0
    while time.time() - t0 < DIAGNOSE_TIMEOUT:
        cdp.drain(1.0)
        cards = cdp.js("document.querySelectorAll('#out .card').length") or 0
        if cards:
            break
    print(f"diagnosis rendered after {time.time()-t0:.0f}s: {cards} cards")

    # 4. read the rendered result back
    result = cdp.js("""(() => {
      const out = document.getElementById('out');
      const cards = [...out.querySelectorAll('.card h2')].map(h => h.textContent.trim());
      const suspects = [...out.querySelectorAll('.suspect b')].map(b => b.textContent.trim());
      const sevs = [...out.querySelectorAll('.sev')].map(s => s.textContent.trim());
      const titles = [...out.querySelectorAll('.finding h3')].map(h => {
        const c = h.cloneNode(true); const s = c.querySelector('.sev');
        if (s) s.remove(); return c.textContent.trim();
      });
      const fixes = out.querySelectorAll('.finding li').length;
      const evidence = out.querySelectorAll('.evidence').length;
      const status = document.getElementById('status').textContent;
      const verdict = out.querySelector('.card.verdict');
      return {
        cards, suspects, sevs, titles, fixes, evidence, status,
        htmlLang: document.documentElement.lang,
        envSummaryLabel: (out.querySelector('details.env summary') || {}).textContent || '',
        copyLabels: [...out.querySelectorAll('[data-copy]')].map(b => b.textContent.trim()),
        firstCardIsVerdict: !!(out.firstElementChild && out.firstElementChild.classList.contains('verdict')),
        verdictTitle: (document.getElementById('verdict-title') || {}).textContent || '',
        hasVerdict: !!verdict,
        envCollapsed: !!out.querySelector('details.env') && !out.querySelector('details.env').open,
        copyButtons: out.querySelectorAll('[data-copy]').length,
        focusOnVerdict: document.activeElement && document.activeElement.id === 'verdict-title',
        liveStatus: document.getElementById('status').getAttribute('aria-live'),
        labelForLog: !!document.querySelector('label[for="log"]'),
        fileInput: (() => { const f = document.getElementById('file'); return f ? f.accept : ''; })(),
        progressHidden: getComputedStyle(document.getElementById('progress')).display === 'none',
      };
    })()""")
    print("\nrendered DOM:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 4b. the in-browser engine must emit the canonical Incident doc.
    # app.js renders the full doc into <details class="raw"><pre>, so read it
    # back from the DOM -- this is exactly what the browser produced (calling
    # the Python global from page scope doesn't work: it lives in Pyodide's
    # namespace, not window). schema_version present proves app.js uses
    # build_incident, not an inline copy that drifts from the CLI.
    raw = cdp.js("(document.querySelector('.raw pre')||{}).textContent")
    sv = None
    if raw:
        try:
            sv = json.loads(raw).get("schema_version")
        except (ValueError, AttributeError):
            sv = None
    print(f"\nin-browser Incident schema_version (from rendered raw JSON): {sv!r}")

    # 5. acceptance assertions (language-agnostic + zh defaults)
    checks = [
        ("suspect chip 'lithium' rendered",
         any("lithium" in s.lower() for s in result["suspects"])),
        ("watchdog finding rendered",
         any("watchdog" in t.lower() or "hung" in t.lower() for t in result["titles"])),
        ("a FATAL/ERROR severity badge shown",
         any(s in SEV_WORDS for s in result["sevs"])),
        ("fix steps rendered", result["fixes"] >= 1),
        ("evidence lines rendered", result["evidence"] >= 1),
        ("in-browser doc carries schema_version", sv == "1.0"),
        # --- P0 UX contract ---
        ("verdict card is the first result block", result["firstCardIsVerdict"]),
        ("verdict headline is the root cause", "watchdog" in result["verdictTitle"].lower()),
        ("environment detail is collapsed", result["envCollapsed"]),
        ("copy actions available (fix + diagnosis)", result["copyButtons"] >= 2),
        ("focus moved to the verdict heading", result["focusOnVerdict"]),
        ("status line is a live region", result["liveStatus"] in ("polite", "assertive")),
        ("textarea has a real label", result["labelForLog"]),
        ("file picker accepts .log", ".log" in (result["fileInput"] or "")),
        ("progress list hidden once ready", result["progressHidden"]),
        ("progress list really is display:none", vis["progress"] == "none"),
        ("empty notice is display:none", vis["notice"] == "none"),
        ("clear button hidden while the box is empty",
         vis["clear"] == "none" and vis["logEmpty"]),
        # --- i18n: Chinese is the default ---
        ("document declares zh-CN by default", result["htmlLang"] == "zh-CN"),
        ("status line is Chinese by default", "条问题" in result["status"]),
        ("environment summary is Chinese", "环境信息" in result["envSummaryLabel"]),
        ("copy buttons are Chinese", any("复制" in s for s in result["copyLabels"])),
    ]

    # 6. interaction checks
    busy = cdp.js("""(() => {
      setBusy(true);
      const on = {go: document.getElementById('go').disabled,
                  sample: document.getElementById('sample').disabled,
                  pick: document.getElementById('pick').disabled};
      setBusy(false);
      const off = {go: document.getElementById('go').disabled,
                   sample: document.getElementById('sample').disabled};
      return {on, off};
    })()""")
    checks.append(("busy state disables every input",
                   all(busy["on"].values()) and not any(busy["off"].values())))

    # 7. a link must be explained, not silently diagnosed (Chinese default)
    guard = cdp.js("""(() => {
      document.getElementById('clear').click();
      const log = document.getElementById('log');
      log.value = 'https://mclo.gs/6cWndzQ';
      log.dispatchEvent(new Event('input'));
      document.getElementById('go').click();
      const n = document.getElementById('notice');
      return {visible: !n.hidden, text: n.textContent,
              cards: document.querySelectorAll('#out .card').length,
              status: document.getElementById('status').textContent};
    })()""")
    checks.append(("a paste link is rejected with guidance (zh)",
                   guard["visible"]
                   and ("链接" in guard["text"] or "link" in guard["text"].lower())
                   and guard["cards"] == 0))

    # 8. the language switch must relabel a VISIBLE notice in place -- this is
    # the check that catches "we translated the template but kept the rendered
    # string" (the exact failure mode a naive i18n pass ships).
    switched = cdp.js("""(() => {
      const before = document.activeElement;
      document.getElementById('lang-en').click();
      const n = document.getElementById('notice');
      return {htmlLang: document.documentElement.lang,
              notice: n.textContent,
              pressed: document.getElementById('lang-en').getAttribute('aria-pressed'),
              status: document.getElementById('status').textContent,
              focusUnchanged: document.activeElement === before,
              saved: localStorage.getItem('mcd.lang')};
    })()""")
    checks.append(("switching to EN relabels the open notice",
                   switched["htmlLang"] == "en"
                   and "link" in (switched["notice"] or "").lower()
                   and "链接" not in (switched["notice"] or "")))
    checks.append(("switching to EN relabels the status line",
                   "nothing diagnosed" in (switched["status"] or "").lower()))
    checks.append(("EN button reports aria-pressed", switched["pressed"] == "true"))
    checks.append(("language switch does not steal focus", switched["focusUnchanged"]))
    checks.append(("language choice is persisted", switched["saved"] == "en"))

    # 9. back to Chinese: the already-rendered diagnosis must return to Chinese
    # without a re-diagnosis (same LAST document, re-rendered chrome).
    cdp.js("document.getElementById('sample').click()")
    t0 = time.time()
    while time.time() - t0 < DIAGNOSE_TIMEOUT:
        cdp.drain(1.0)
        if cdp.js("document.querySelectorAll('#out .card').length") or 0:
            break
    back = cdp.js("""(() => {
      document.getElementById('lang-zh').click();
      const out = document.getElementById('out');
      return {htmlLang: document.documentElement.lang,
              status: document.getElementById('status').textContent,
              verdict: (document.getElementById('verdict-title') || {}).textContent || '',
              envSummary: (out.querySelector('details.env summary') || {}).textContent || '',
              copyLabels: [...out.querySelectorAll('[data-copy]')].map(b => b.textContent.trim()),
              title: document.title};
    })()""")
    checks.append(("switching back to zh relabels the rendered result",
                   back["htmlLang"] == "zh-CN"
                   and "条问题" in (back["status"] or "")
                   and "环境信息" in (back["envSummary"] or "")
                   and any("复制" in s for s in back["copyLabels"])
                   and "诊断" in (back["title"] or "")))
    checks.append(("the diagnosis itself survives a language switch",
                   "watchdog" in (back["verdict"] or "").lower()))

    # 10. translation hygiene: no missing keys, and both packs cover the same set
    hygiene = cdp.js("""(() => {
      const t = [...document.querySelectorAll('[data-i18n]')];
      const missing = t.filter(e => !e.textContent.trim() || e.textContent === e.dataset.i18n)
                         .map(e => e.dataset.i18n);
      const pack = (typeof I18N !== 'undefined') ? I18N : {};
      const zh = Object.keys(pack.zh || {}).sort();
      const en = Object.keys(pack.en || {}).sort();
      return {missing, zh: zh.length, en: en.length,
              parity: zh.length > 0 && JSON.stringify(zh) === JSON.stringify(en)};
    })()""")
    checks.append(("no untranslated data-i18n node", not hygiene["missing"]))
    checks.append(("both language packs carry the same keys",
                   hygiene["parity"] and hygiene["zh"] == hygiene["en"]
                   and hygiene["zh"] >= 70))

    # 11. a paragraph of prose gets a warning but is still allowed through
    prose = cdp.js("""(() => {
      document.getElementById('clear').click();
      const log = document.getElementById('log');
      log.value = 'my server keeps crashing pls help';
      log.dispatchEvent(new Event('input'));
      const v = validate(log.value);
      return {block: !!v.block, warn: !!v.warn};
    })()""")
    checks.append(("prose is warned about, not blocked", prose["warn"] and not prose["block"]))

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
