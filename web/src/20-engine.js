/* -------------------------------------------------------------- progress */

function step(name, state) {
  const el = document.querySelector(`#progress li[data-step="${name}"]`);
  if (el) el.dataset.state = state;
}

function resetProgress() {
  $("progress").hidden = false;
  step("runtime", "pending");
  step("engine", "pending");
  step("ready", "pending");
  step("runtime", "active");
}

/* ------------------------------------------------------------------ boot */

// Pyodide is ~10 MB of WASM and cannot be vendored into this repo, so the page
// depends on one CDN being reachable. One is not a plan: a corporate proxy or a
// national network can block jsDelivr while unpkg works. Try them in order and
// report the whole list if none loads -- "engine failed" with no URL is what a
// user cannot act on.
// Measured, not assumed. unpkg serves pyodide.js but its wheels come back
// without `Access-Control-Allow-Origin`, so the runtime loads and then dies
// deeper with a CORS error the page cannot explain; cdn.pyodide.org does not
// resolve here at all. jsDelivr's own mirrors are the same files behind
// different hostnames, which is exactly what a blocked-main-host needs.
const PYODIDE_CDNS = [
  "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/",
  "https://fastly.jsdelivr.net/pyodide/v0.26.4/full/",
  "https://gcore.jsdelivr.net/pyodide/v0.26.4/full/",
];

const SCRIPT_TIMEOUT_MS = 20000;

// `new Error("")` and DOMException-style failures both reach the catch block
// with an empty `.message`, which produced a status line that said the engine
// failed and a panel with nothing in it. Never show an empty reason.
function describeError(e) {
  if (!e) return "unknown error (open the browser console for details)";
  const msg = (e.message || "").trim();
  if (msg) return msg;
  const err = (e.error && (e.error.message || "")).trim();
  if (err) return err;
  if (e.type) return e.type + " (open the browser console for details)";
  const s = String(e);
  return s && s !== "[object Object]"
    ? s
    : "unknown error (open the browser console for details)";
}

function loadScript(src, timeoutMs = SCRIPT_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const el = document.createElement("script");
    let done = false;
    const finish = (err) => {
      if (done) return;
      done = true;
      el.remove();
      err ? reject(err) : resolve();
    };
    el.src = src;
    el.async = true;
    el.onload = () => finish(null);
    el.onerror = () => finish(new Error("could not load " + src));
    setTimeout(() => finish(new Error("timed out after " +
      Math.round(timeoutMs / 1000) + "s: " + src)), timeoutMs);
    document.head.appendChild(el);
  });
}

async function ensureRuntime() {
  if (typeof window.loadPyodide === "function") return;
  if (typeof WebAssembly !== "object") {
    throw new Error("this browser has no WebAssembly support -- " +
                    "the engine cannot run here (try a current Chrome/Edge/Firefox)");
  }
  const tried = [];
  for (const base of PYODIDE_CDNS) {
    const url = base + "pyodide.js";
    tried.push(url);
    try {
      await loadScript(url);
      if (typeof window.loadPyodide === "function") return;
      throw new Error("script loaded but loadPyodide is missing: " + url);
    } catch (e) {
      console.warn("pyodide source failed:", url, e && e.message);
    }
  }
  throw new Error("no Pyodide CDN reachable. Tried:\n" + tried.join("\n"));
}

// sample.js is 78 KB of real report text. Loading it on first paint delays the
// only thing the user is waiting for (the engine); fetch it when it is asked for.
let samplePromise = null;
function ensureSample() {
  if (window.MCD_SAMPLE) return Promise.resolve(window.MCD_SAMPLE);
  if (!samplePromise) {
    samplePromise = loadScript("sample.js")
      .then(() => window.MCD_SAMPLE || SAMPLE)
      .catch(() => SAMPLE);            // the built-in fallback is enough
  }
  return samplePromise;
}

// The engine is ~10 MB of WASM: loading it on first paint spends the user's
// bandwidth before they have shown they want a diagnosis. It boots on the
// first action instead, and every action awaits this same promise.
// The sample's diagnosis is precomputed at build time by the same engine.
// Showing it immediately is the difference between a 9-second blank wait and
// an answer on the first click -- and it still works when the CDN does not.
async function showPrecomputedSample() {
  try {
    const res = await fetch("sample-diagnosis." + LANG + ".json",
                            { cache: "force-cache" });
    if (!res.ok) throw new Error(String(res.status));
    const doc = await res.json();
    LAST = doc;
    LAST_ORIGIN = "sample";
    // Default focus, not focus:false: this render is the result of a click, so
    // the verdict should be scrolled to and focused. focus:false is for the
    // language switch, where stealing focus from the toggle would be hostile.
    // The status line is busy with boot progress, so the card carries the
    // explanation: this result is real, and it did not need the engine.
    render(doc, { note: ready ? "" : t("st.instant") });
    return true;
  } catch (e) {
    return false;
  }
}

function ensureEngine() {
  if (ready) return Promise.resolve(true);
  if (!booting) booting = boot().then(() => ready).catch(() => false);
  return booting;
}

async function boot() {
  resetProgress();
  hideNotice();
  ready = false;
  setBusy(true);
  setStatus("boot.runtime");

  const startedAt = Date.now();
  const ticker = setInterval(() => {
    if (ready) return;
    setStatus("boot.runtimeElapsed",
              undefined, { s: Math.round((Date.now() - startedAt) / 1000) });
  }, 1000);

  try {
    await ensureRuntime();
    pyodide = await loadPyodide();
    step("runtime", "done");
    step("engine", "active");
    setStatus("boot.engine");

    // PyYAML is a dependency of the wheel. Ask Pyodide for its own build of it
    // (served from the same CDN we just proved reachable) instead of letting
    // micropip resolve it at install time -- that path is one more network hop
    // that can fail, and the browser cannot tell the user which hop it was.
    await pyodide.loadPackage(["micropip", "pyyaml"]);
    await pyodide.runPythonAsync("import micropip");

    const manifest = await (await fetch("wheel-manifest.json")).json();
    const wheelUrl = new URL(manifest.file, location.href).href;
    if (manifest.bytes) {
      // A stale wheel in a deployed folder is invisible until the engine
      // imports the wrong code. The CLI already learned this the hard way
      // (test_manifest_source_digest_matches_mcd); a HEAD is cheap.
      const head = await fetch(wheelUrl, { method: "HEAD" });
      const len = Number(head.headers.get("content-length") || 0);
      if (len && len !== manifest.bytes) {
        throw new Error(
          "web/" + manifest.file + " is " + len + " bytes but the manifest " +
          "says " + manifest.bytes + " -- the folder is stale, re-run " +
          "tools/build_web.py");
      }
    }
    try {
      await pyodide.runPythonAsync(
        "import micropip\nawait micropip.install(" +
        JSON.stringify(wheelUrl) + ", deps=False)");
    } catch (e) {
      // Older Pyodide builds may not honour deps=False with a local wheel.
      console.warn("deps=False install failed, retrying with deps:", e);
      await pyodide.runPythonAsync(
        "import micropip\nawait micropip.install(" + JSON.stringify(wheelUrl) + ")");
    }

    // Warm the engine once (loads the rule packs) so the first Diagnose click
    // is instant.
    await pyodide.runPythonAsync(`
import json
from mcd.cli import diagnose as _diagnose

def mcd_diagnose(text, lang="en"):
    rep, findings, t = _diagnose(None, text, source="<browser>", lang=lang)
    # Single source of truth -- same builder the CLI uses, so the browser
    # document carries schema_version and can't drift from render_json.
    from mcd.report.render import build_incident
    doc = build_incident(rep, findings, t)
    return json.dumps(doc, ensure_ascii=False)

def mcd_feedback(text, lang="en"):
    # Same summary the CLI builds, so the two entry points cannot drift.
    from mcd.cli import feedback_url
    rep, findings, _ = _diagnose(None, text, source="<browser>", lang=lang)
    return feedback_url(rep, findings)
`);
    step("engine", "done");
    step("ready", "done");
    $("progress").hidden = true;
    clearInterval(ticker);
    ready = true;
    setBusy(false);
    setStatus("boot.ready", "ok");
  } catch (e) {
    clearInterval(ticker);
    console.error(e);
    BOOT_ERROR = describeError(e);
    step("engine", "failed");
    $("progress").hidden = true;
    setStatus("boot.failed", "err");
    showBootError(BOOT_ERROR);
  }
}

function showBootError(msg) {
  // Actionable, not just the raw exception: retry, copy the error, or fall
  // back to the CLI. A dead page with "ReferenceError" loses the user.
  showNotice("bootErr", { msg: esc(msg) });
}

/* -------------------------------------------------------------- validate */

const LINK_RE = /(mclo\.gs|pastebin\.com|gist\.github\.com|paste\.ee|hastebin)/i;

function looksLikeLink(text) {
  const t = text.trim();
  return t.length < 2000 && LINK_RE.test(t);
}

function looksLikeLog(text) {
  if (/----\s*Minecraft Crash Report/i.test(text)) return true;
  if (/^\s*Description:/m.test(text)) return true;
  if ((text.match(/^\s*(?:at|\tat)\s+[\w.$]+\s*\(/gm) || []).length >= 2) return true;
  // Two timestamped lines are a log excerpt, which is what people paste when
  // they grab "the last few lines". Requiring five called a real 3-line log
  // "not a log" and then showed it a not-a-report card.
  if ((text.match(/^\s*\[\d{2}:\d{2}:\d{2}\]/gm) || []).length >= 2) return true;
  if (/Starting minecraft server version|Done \(\d+(\.\d+)?s\)!/i.test(text)) return true;
  return false;
}

function looksLikeHsErr(text) {
  // HotSpot's fatal-error log, not a Minecraft report: native crash, no rule
  // in this tool can say anything about it.
  return /^#\s*A fatal error has been detected by the Java Runtime Environment/m.test(text);
}

function looksLikeExitCodeOnly(text) {
  const body = text.trim();
  if (!body || body.length > 200 || body.split(/\r?\n/).length > 2) return false;
  return /exit\s*(?:code|status)\s*[:=]?\s*-?\d+|process\s+(?:exited|finished)\s+with\s+(?:exit\s+)?(?:code|status)\s*-?\d+/i.test(body);
}

function validate(text) {
  if (!text.trim()) {
    return { block: true, key: "val.empty" };
  }
  if (looksLikeHsErr(text)) {
    return { block: true, key: "val.hsErr" };
  }
  if (looksLikeExitCodeOnly(text)) {
    return { block: true, key: "val.exitCode" };
  }
  if (looksLikeLink(text)) {
    // Never silently diagnose a URL: the engine would see one line, find no
    // rule, and the user would conclude the tool does not cover their crash.
    return { block: true, key: "val.link" };
  }
  if (!looksLikeLog(text)) {
    return { warn: true, key: "val.prose" };
  }
  return {};
}

/* -------------------------------------------------------------- diagnose */

function diagnose() {
  if (!ready || busy) return;
  const text = $("log").value;
  // MAX_BYTES used to guard file drops only. A 9 MB paste went straight into
  // Pyodide and froze the tab for 12 seconds, then said "no rule matched" --
  // true, useless, and indistinguishable from a real answer.
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > MAX_BYTES) {
    showNotice("file.tooBig", { size: fmtSize(bytes) });
    setStatus("st.blocked", "err");
    return;
  }
  const check = validate(text);
  if (check.block) {
    showNotice(check.key);
    setStatus("st.blocked", "err");
    $("log").focus();
    return;
  }
  if (check.warn) showNotice(check.key);
  else hideNotice();

  setBusy(true);
  setStatus("st.diagnosing");
  // run on the next tick so the status paints before the WASM call blocks
  setTimeout(() => {
    try {
      const json = pyodide.globals.get("mcd_diagnose")(text, LANG);
      const doc = JSON.parse(json);
      LAST_TEXT = text;
      LAST_ORIGIN = "engine";
      render(doc, { weakInput: !!check.warn });
      if (check.warn) hideNotice();   // the card says it better than a toast
      const n = (doc.findings || []).length;
      if (check.warn && !n) setStatus("st.notReport");
      else if (n) setStatus("st.findings", "ok", { n });
      else setStatus("st.none");
    } catch (e) {
      console.error(e);
      const msg = (e && e.message) ? e.message : String(e);
      setStatus("st.failed", "err", { msg });
      showNotice("diagErr", { msg: esc(msg) });
    } finally {
      setBusy(false);
    }
  }, 30);
}

