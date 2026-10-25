/* mc-crash-doctor web UI.
 *
 * Loads Pyodide (CPython compiled to WASM), micropip-installs the project
 * wheel from wheel-manifest.json, then runs the SAME parse -> rules -> triage
 * pipeline as the CLI, entirely client-side. The pasted log is never sent
 * anywhere -- that is the whole point of this deployment model.
 *
 * UX contract (kept deliberately explicit, see the P0 audit):
 *  - verdict first: root cause + suspect + the first two fixes, in one screen;
 *  - every input path is validated visibly -- a link or a stray paragraph gets
 *    an explanation instead of a silent "no rule matched";
 *  - boot reports three named stages and can be retried;
 *  - the result is announced (status line) and focus moves to the verdict, so
 *    keyboard and screen-reader users know it landed;
 *  - every diagnosis and every fix can be copied out.
 *
 * i18n: the UI ships bilingual (zh default, en toggle). Every user-facing
 * string lives in I18N below -- nothing is concatenated inline, because a
 * half-translated page reads worse than an untranslated one. Diagnosis CONTENT
 * (finding titles, fixes) comes from the YAML rules and stays as the engine
 * emits it: it is data, pinned by tests/test_e2e.py and the Incident schema,
 * and translating it needs a schema-level change, not a UI one.
 */
"use strict";

const SAMPLE = `---- Minecraft Crash Report ----
// I blame Dinnerbone.

Time: 2026-09-08 18:47:46
Description: Ticking entity

java.lang.OutOfMemoryError: Java heap space
\tat net.minecraft.world.level.Level.tickEntities(Level.java:512) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]
\tat net.minecraft.client.Minecraft.tick(Minecraft.java:1755) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]
\tat mekanism.common.CommonWorldTickHandler.onTick(CommonWorldTickHandler.java:44) ~[Mekanism-1.20.1-10.4.5.19.jar%23155!/:10.4.5.19]

A detailed walkthrough of the error, its code path and all known details is as follows:
---------------------------------------------------------------------------------------

-- Head --
Thread: Render thread
Stacktrace:
\tat net.minecraft.world.level.Level.tickEntities(Level.java:512) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]

-- Entity being ticked --
Details:
\tEntity Type: minecraft:item (net.minecraft.world.entity.item.ItemEntity)
\tEntity ID: 12345

-- System Details --
Details:
\tMinecraft Version: 1.20.1
\tJava Version: 21.0.2, Eclipse Adoptium
\tMemory: 3200 MiB / 4096 MiB
\tJVM Flags: 3 total; -Xmx4G -Xms1G
\tLoader: Forge 1.20.1-47.2.20
\tMod Count: 241
\tMods: 
\t\tMekanism|mekanism|10.4.5.19|DONE|NOSIGNATURE|Mekanism-1.20.1-10.4.5.19.jar
\t\tJust Enough Items|jei|15.2.0.27|DONE|NOSIGNATURE|jei-1.20.1-forge-15.2.0.27.jar
\t\tLithium|lithium|0.11.2|DONE|NOSIGNATURE|lithium-forge-mc1.20.1-0.11.2.jar
\t\tSodium|sodium|0.5.3|DONE|NOSIGNATURE|sodium-forge-mc1.20.1-0.5.3.jar`;

const MAX_BYTES = 8 * 1024 * 1024;
const SEV_RANK = { fatal: 4, error: 3, warning: 2, hint: 1, info: 0 };
const ISSUE_URL = "https://github.com/pop1022/mc-crash-doctor/issues/new?template=crash-not-covered.md";
const STORE_KEY = "mcd.lang";

/* ------------------------------------------------------------------- i18n */

const I18N = {
  zh: {
    title: "mc-crash-doctor — 在浏览器里诊断 Minecraft 崩溃",
    metaDesc: "粘贴 Minecraft 崩溃报告或服务器日志，由 mc-crash-doctor 规则引擎在浏览器本地完成诊断；日志不会离开你的电脑。",
    sub: "粘贴 Minecraft 崩溃报告或服务器日志 → 直接给出根因、修复步骤，以及该找哪个模组算账。",
    privacy: "🔒 <b>纯本地运行。</b> 日志不会离开你的浏览器。",
    privacyTitle: "诊断在标签页内的 WebAssembly 里完成，不上传、无服务器、无统计。",
    fieldLabel: "崩溃报告或日志",
    placeholder: "把 crash-report.txt / latest.log 粘到这里，或者把文件拖进这个框…",
    hint: "贴完整报告效果最好——Mod List 和 System Details 能让定责准确很多。也可以把 <code>.txt</code>/<code>.log</code> 文件拖进这个框，或点「选择文件…」。",
    diagnose: "开始诊断",
    sample: "用示例试试",
    pick: "选择文件…",
    clear: "清空",
    stepRuntime: "Python 运行时",
    stepEngine: "规则引擎",
    stepReady: "就绪",
    footerTail: "· 与 CLI 同一套引擎 · 规则是 YAML，欢迎 PR",

    "boot.runtime": "正在启动 Python 运行时…",
    "boot.engine": "正在安装诊断引擎…",
    "boot.ready": "引擎就绪 — 粘贴崩溃报告后点「开始诊断」",
    "boot.failed": "引擎加载失败",

    "bootErr": (v) => "<p><b>诊断引擎没能加载。</b>它从 CDN（jsDelivr）下载后装在这个" +
      "标签页里，网络被拦或浏览器太旧是最常见的原因。</p>" +
      `<pre>${v.msg}</pre>` +
      '<div class="row" style="margin-top:0">' +
      '<button id="retry">重试</button>' +
      '<button class="ghost" id="copyerr">复制错误</button></div>' +
      '<p class="hint">还是不行？同一套引擎也可以本地跑：' +
      "<code>pip install mc-crash-doctor</code>，然后 " +
      "<code>mc-crash-doctor crash-report.txt</code>。</p>",

    "val.empty": "先粘一份崩溃报告 — 或者点「用示例试试」。",
    "val.link": () => "<b>这是一条链接，不是日志。</b> 打开它、把报告内容复制过来贴在这里——" +
      "浏览器没法替你去抓别的站点的粘贴页（跨域限制）。",
    "val.prose": () => "<b>这看起来不像崩溃报告或日志。</b> 还是继续诊断，但大概率匹配不上——" +
      "正常报告里通常有堆栈帧（<code>at …</code>）或「Minecraft Crash Report」抬头。",

    "st.blocked": "没有诊断 — 看上面的提示",
    "st.diagnosing": "正在诊断…",
    "st.findings": (v) => `找到 ${v.n} 条问题 — 结论在下方`,
    "st.none": "完成 — 这份报告没有命中任何规则",
    "st.failed": (v) => `诊断失败：${v.msg}`,

    "diagErr": (v) => "<p><b>引擎在诊断过程中抛了异常。</b>文本已经解析，但某条规则崩了" +
      `——请带上这份日志提个 issue。</p><pre>${v.msg}</pre>`,

    "verdict.rootCause": "根因",
    "verdict.suspect": "最可能的原因",
    "verdict.confidence": "置信度",
    "verdict.startHere": "先做这两步",
    "verdict.noRule": "没有规则命中这份报告。解析是干净的，只是这个故障模式还没覆盖——带上报告开个 issue，它就会变成下一条规则 + 测试。",
    "verdict.parsed": "崩溃报告已解析",
    "verdict.failedBadge": "未命中",

    "act.copyFix": "复制修复步骤",
    "act.copyMd": "复制诊断",
    "act.issue": "去开 issue",

    "ov.findings": (v) => `${v.n} 条问题`,
    "findings.title": "全部发现",
    "findings.blame": "归责：",
    "findings.fixes": "修复步骤",
    "findings.copyFixes": "复制这些步骤",
    "findings.evidence": "证据",

    "env.summary": "环境信息",
    "raw.summary": "原始 JSON",

    "copy.ok": "已复制到剪贴板",
    "copy.fail": "复制失败",
    "copy.btnOk": "已复制",
    "copy.btnFail": "复制失败",

    "file.tooBig": (v) => `这个文件有 <b>${v.size}</b> — 上限 8 MB。请贴崩溃报告本身，而不是整个日志压缩包。`,
    "file.notLog": "这个文件看起来不像崩溃报告或日志。还是继续诊断，但请确认选对了文件。",
    "file.loaded": (v) => `已载入 <b>${v.name}</b>（${v.size}）。点「开始诊断」。`,
    "file.readFail": (v) => `读不了这个文件。${v.msg}`,

    "md.title": "## Minecraft 崩溃诊断",
    "md.env": "**环境**",
    "md.rootCause": "**根因**",
    "md.suspect": "**嫌疑模组**",
    "md.fixes": "**修复步骤**",
    "md.footer": "_由 mc-crash-doctor 在本地诊断 — 日志从未被上传。_",

    "env.root": "根因",
    "env.loader": "加载器",
    "env.minecraft": "游戏版本",
    "env.java": "Java",
    "env.mods": "模组数",
    "env.heap": "堆内存",
    "env.side": "运行侧",
    "env.server": "服务端",
    "env.client": "客户端",
    "env.modsCount": (v) => `${v.n} 个模组`,
    "env.heapLine": (v) => `堆 ${v.used}/${v.max} MiB`,
    "env.mcVersion": (v) => `MC ${v.v}`,
    "env.javaMajor": (v) => `Java ${v.v}`,

    "sev.fatal": "致命",
    "sev.error": "错误",
    "sev.warning": "警告",
    "sev.hint": "提示",
    "sev.info": "信息",
  },

  en: {
    title: "mc-crash-doctor — diagnose Minecraft crashes in your browser",
    metaDesc: "Paste a Minecraft crash report or server log. Diagnosed entirely in your browser by the mc-crash-doctor rule engine — the log never leaves your machine.",
    sub: "Paste a Minecraft crash report or server log → root cause, fix steps, and the mod to blame.",
    privacy: "🔒 <b>Local only.</b> The log never leaves your browser.",
    privacyTitle: "Diagnosis runs in WebAssembly inside this tab. Nothing is uploaded, there is no server and no analytics.",
    fieldLabel: "Crash report or log",
    placeholder: "Paste crash-report.txt / latest.log here, or drop the file into this box…",
    hint: "The full report works best — the Mod List and System Details make attribution much stronger. Drop a <code>.txt</code>/<code>.log</code> file anywhere in this box, or use “Choose a file…”.",
    diagnose: "Diagnose",
    sample: "Try a sample",
    pick: "Choose a file…",
    clear: "Clear",
    stepRuntime: "Python runtime",
    stepEngine: "Rule engine",
    stepReady: "Ready",
    footerTail: "· same engine as the CLI · rules are YAML, PRs welcome",

    "boot.runtime": "starting the Python runtime…",
    "boot.engine": "installing the diagnosis engine…",
    "boot.ready": "engine ready — paste a crash report and hit Diagnose",
    "boot.failed": "engine failed to load",

    "bootErr": (v) => "<p><b>The diagnosis engine could not load.</b> It is fetched from " +
      "a CDN (jsDelivr) and installed in this tab; a blocked network or an old browser is " +
      `the usual reason.</p><pre>${v.msg}</pre>` +
      '<div class="row" style="margin-top:0">' +
      '<button id="retry">Retry</button>' +
      '<button class="ghost" id="copyerr">Copy error</button></div>' +
      '<p class="hint">Still stuck? The same engine runs locally: ' +
      "<code>pip install mc-crash-doctor</code> then " +
      "<code>mc-crash-doctor crash-report.txt</code>.</p>",

    "val.empty": "Paste a crash report first — or press “Try a sample”.",
    "val.link": () => "<b>That is a link, not the log.</b> Open it, copy the report and " +
      "paste it here — the browser cannot fetch another site's paste for you (cross-origin).",
    "val.prose": () => "<b>This does not look like a crash report or a log.</b> " +
      "Diagnosing anyway, but expect no useful match — a report usually contains stack " +
      "frames (<code>at …</code>) or a “Minecraft Crash Report” banner.",

    "st.blocked": "nothing diagnosed — see the note above",
    "st.diagnosing": "diagnosing…",
    "st.findings": (v) => `${v.n} finding${v.n > 1 ? "s" : ""} — the verdict is below`,
    "st.none": "done — no rule matched this report",
    "st.failed": (v) => `diagnosis failed: ${v.msg}`,

    "diagErr": (v) => "<p><b>The engine threw while diagnosing.</b> The text was parsed, " +
      `but a rule crashed — please report this with the log attached.</p><pre>${v.msg}</pre>`,

    "verdict.rootCause": "root cause",
    "verdict.suspect": "most likely cause",
    "verdict.confidence": "confidence",
    "verdict.startHere": "start here",
    "verdict.noRule": "No rule matched this report. It parsed cleanly, but this failure mode is not covered yet — opening an issue with the report turns it into the next rule + test.",
    "verdict.parsed": "Crash report parsed",
    "verdict.failedBadge": "no match",

    "act.copyFix": "Copy fix",
    "act.copyMd": "Copy diagnosis",
    "act.issue": "Open an issue",

    "ov.findings": (v) => `${v.n} finding${v.n > 1 ? "s" : ""}`,
    "findings.title": "All findings",
    "findings.blame": "blame:",
    "findings.fixes": "fixes",
    "findings.copyFixes": "Copy these fixes",
    "findings.evidence": "evidence",

    "env.summary": "Environment",
    "raw.summary": "raw JSON",

    "copy.ok": "Copied to clipboard",
    "copy.fail": "Could not copy",
    "copy.btnOk": "Copied",
    "copy.btnFail": "Copy failed",

    "file.tooBig": (v) => `That file is <b>${v.size}</b> — the box accepts up to 8 MB. Paste the crash report itself instead of the whole log archive.`,
    "file.notLog": "That file does not look like a crash report or log. Diagnosing anyway, but check you picked the right file.",
    "file.loaded": (v) => `Loaded <b>${v.name}</b> (${v.size}). Press Diagnose.`,
    "file.readFail": (v) => `Could not read that file. ${v.msg}`,

    "md.title": "## Minecraft crash diagnosis",
    "md.env": "**Environment**",
    "md.rootCause": "**Root cause**",
    "md.suspect": "**Suspect**",
    "md.fixes": "**Fixes**",
    "md.footer": "_Diagnosed locally by mc-crash-doctor — the log was never uploaded._",

    "env.root": "root cause",
    "env.loader": "loader",
    "env.minecraft": "minecraft",
    "env.java": "java",
    "env.mods": "mods",
    "env.heap": "heap",
    "env.side": "side",
    "env.server": "server",
    "env.client": "client",
    "env.modsCount": (v) => `${v.n} mods`,
    "env.heapLine": (v) => `heap ${v.used}/${v.max} MiB`,
    "env.mcVersion": (v) => `MC ${v.v}`,
    "env.javaMajor": (v) => `Java ${v.v}`,

    "sev.fatal": "FATAL",
    "sev.error": "ERROR",
    "sev.warning": "WARNING",
    "sev.hint": "HINT",
    "sev.info": "INFO",
  },
};

let LANG = "zh";

function t(key, vars) {
  const pack = I18N[LANG] || I18N.zh;
  let v = pack[key];
  if (v === undefined) v = I18N.zh[key];      // a missing translation must
  if (v === undefined) return key;            // never blank the UI
  if (typeof v === "function") return v(vars || {});
  if (!vars) return v;
  return String(v).replace(/\{(\w+)\}/g, (m, k) =>
    (vars[k] === undefined ? m : String(vars[k])));
}

let pyodide = null;
let ready = false;
let busy = false;
let LAST = null;            // the Incident document currently rendered
let NOTICE = null;          // { key, vars, tone } so it survives a language switch
let BOOT_ERROR = "";        // last boot exception, for the "copy error" button
let STATUS = { key: "boot.runtime", vars: {}, kind: "" };

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- helpers */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setStatus(key, kind, vars) {
  STATUS = { key: key || "", vars: vars || {}, kind: kind || "" };
  paintStatus();
}

function paintStatus() {
  const el = $("status");
  el.textContent = STATUS.key ? t(STATUS.key, STATUS.vars) : "";
  el.className = STATUS.kind;
}

function setBusy(b) {
  busy = b;
  if ($("go")) $("go").disabled = b || !ready;
  if ($("sample")) $("sample").disabled = b || !ready;
  if ($("pick")) $("pick").disabled = b;
  if ($("clear")) $("clear").disabled = b;
}

function showNotice(key, vars, tone) {
  NOTICE = { key, vars: vars || {}, tone: tone || "" };
  paintNotice();
}

function hideNotice() {
  NOTICE = null;
  paintNotice();
}

function paintNotice() {
  const el = $("notice");
  if (!NOTICE) { el.hidden = true; el.innerHTML = ""; return; }
  // NOTICE stores the KEY, never the rendered string: a language switch has to
  // be able to repaint a visible warning in the new language.
  el.innerHTML = t(NOTICE.key, NOTICE.vars);
  el.className = "notice" + (NOTICE.tone === "ok" ? " ok" : "");
  el.hidden = false;
  // Re-attached on every paint: a language switch replaces this subtree.
  const retry = $("retry");
  if (retry) retry.addEventListener("click", () => { hideNotice(); boot(); });
  const cerr = $("copyerr");
  if (cerr) cerr.addEventListener("click", (ev) => copyText(BOOT_ERROR, ev.currentTarget));
}

function syncClear() {
  $("clear").hidden = !$("log").value.length;
}

function fmtSize(bytes) {
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  return Math.max(1, Math.round(bytes / 1024)) + " KB";
}

function sevLabel(sev) {
  const k = String(sev || "").toLowerCase();
  return t("sev." + k);
}

/* --------------------------------------------------------------- i18n glue */

function setLang(lang, opts) {
  LANG = I18N[lang] ? lang : "zh";
  try { localStorage.setItem(STORE_KEY, LANG); } catch (e) { /* private mode */ }

  const html = document.documentElement;
  html.lang = LANG === "zh" ? "zh-CN" : "en";
  document.title = t("title");
  const meta = $("meta-desc");
  if (meta) meta.setAttribute("content", t("metaDesc"));

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  const privacy = $("privacy");
  if (privacy) privacy.title = t("privacyTitle");

  document.querySelectorAll(".lang button").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.lang === LANG ? "true" : "false");
  });

  paintStatus();
  paintNotice();
  // Re-render the existing result so its chrome (labels, buttons, environment
  // keys) switches too. Focus is deliberately NOT moved: the user is on the
  // toggle, and stealing focus from it would be hostile.
  if (LAST) render(LAST, { focus: false });
  if (opts && opts.announce) {
    $("copystatus").textContent = LANG === "zh" ? "界面语言：中文" : "Interface language: English";
  }
  setupProgressLabel();
}

function setupProgressLabel() {
  const p = $("progress");
  if (p) p.setAttribute("aria-label", LANG === "zh" ? "引擎加载进度" : "Engine loading progress");
  const out = $("out");
  if (out) out.setAttribute("aria-label", LANG === "zh" ? "诊断结果" : "Diagnosis result");
}

function preferredLang() {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved && I18N[saved]) return saved;
  } catch (e) { /* ignore */ }
  // Default to Chinese: this deployment targets the zh-speaking Minecraft
  // server community. The toggle is right there for everyone else.
  return "zh";
}

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

async function boot() {
  resetProgress();
  hideNotice();
  ready = false;
  setBusy(true);
  setStatus("boot.runtime");

  try {
    pyodide = await loadPyodide();
    step("runtime", "done");
    step("engine", "active");
    setStatus("boot.engine");

    await pyodide.loadPackage(["micropip"]);
    await pyodide.runPythonAsync("import micropip");

    const manifest = await (await fetch("wheel-manifest.json")).json();
    // micropip accepts a URL; serve the wheel from the same origin.
    const wheelUrl = new URL(manifest.file, location.href).href;
    await pyodide.runPythonAsync(
      `import micropip\nawait micropip.install(${JSON.stringify(wheelUrl)})`
    );

    // Warm the engine once (loads PyYAML + all rule packs) so the first
    // Diagnose click is instant.
    await pyodide.runPythonAsync(`
import json
from mcd.cli import diagnose as _diagnose

def mcd_diagnose(text):
    rep, findings, t = _diagnose(None, text, source="<browser>")
    # Single source of truth -- same builder the CLI uses, so the browser
    # document carries schema_version and can't drift from render_json.
    from mcd.report.render import build_incident
    doc = build_incident(rep, findings, t)
    return json.dumps(doc, ensure_ascii=False)
`);
    step("engine", "done");
    step("ready", "done");
    $("progress").hidden = true;
    ready = true;
    setBusy(false);
    setStatus("boot.ready", "ok");
  } catch (e) {
    console.error(e);
    BOOT_ERROR = (e && e.message) ? e.message : String(e);
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
  if ((text.match(/^\s*\[\d{2}:\d{2}:\d{2}\]/gm) || []).length >= 5) return true;
  return false;
}

function validate(text) {
  if (!text.trim()) {
    return { block: true, key: "val.empty" };
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
      const json = pyodide.globals.get("mcd_diagnose")(text);
      const doc = JSON.parse(json);
      render(doc);
      const n = (doc.findings || []).length;
      if (n) setStatus("st.findings", "ok", { n });
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

/* ---------------------------------------------------------------- render */

function bySeverity(a, b) {
  return (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0);
}

// [id, value] -- the label is looked up at render time, so switching language
// relabels the environment block without re-diagnosing.
function summaryBits(s) {
  return [
    ["root", s.root_cause],
    ["loader", [s.loader, s.loader_version].filter(Boolean).join(" ") || null],
    ["minecraft", s.minecraft_version],
    ["java", s.java_version],
    ["mods", s.mod_count],
    ["heap", s.heap_max_mib ? t("env.heapLine", {
      used: s.heap_used_mib ?? "?", max: s.heap_max_mib }) : null],
    ["side", s.is_server ? t("env.server") : s.is_client ? t("env.client") : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");
}

function envLine(s) {
  return [
    [s.loader, s.loader_version].filter(Boolean).join(" "),
    s.minecraft_version && t("env.mcVersion", { v: s.minecraft_version }),
    s.java_major && t("env.javaMajor", { v: s.java_major }),
    s.mod_count && t("env.modsCount", { n: s.mod_count }),
    s.heap_max_mib && t("env.heapLine", {
      used: s.heap_used_mib ?? "?", max: s.heap_max_mib }),
  ].filter(Boolean).join(" · ");
}

function verdictCard(s, top, topSus) {
  const sev = top ? esc(sevLabel(top.severity)) : "";
  const head = s.root_cause || s.description || t("verdict.parsed");
  const meta = [s.root_cause ? s.description : null,
                s.is_server ? t("env.server") : s.is_client ? t("env.client") : null]
    .filter(Boolean).join(" · ");

  let html = `<div class="card verdict">`;
  if (top) {
    html += `<div class="eyebrow"><span class="sev ${esc(top.severity)}">${sev}</span>` +
            `<span class="where">${t("verdict.rootCause")}</span></div>`;
  }
  html += `<h2 id="verdict-title" tabindex="-1">${esc(head)}</h2>`;
  if (meta) html += `<p class="cause-meta">${esc(meta)}</p>`;

  if (topSus) {
    const name = topSus.name || topSus.modid;
    const conf = Math.round((topSus.confidence || 0) * 100);
    html += `<div class="suspect-row">
      <div class="who"><span class="k">${t("verdict.suspect")}</span>
        <span class="v suspect"><b>${esc(name)}</b>${
          topSus.version ? ` <span class="conf">v${esc(topSus.version)}</span>` : ""
        }</span></div>
      <div class="conf"><span class="k">${t("verdict.confidence")}</span>
        <span class="v">${conf}%</span></div>
    </div>`;
    if (topSus.reasons && topSus.reasons.length) {
      html += `<ul class="why">` +
        topSus.reasons.slice(0, 2).map((r) => `<li>${esc(r)}</li>`).join("") +
        `</ul>`;
    }
  }

  if (top && top.fixes && top.fixes.length) {
    html += `<div class="starthere"><span class="k">${t("verdict.startHere")}</span><ol>`;
    for (const fx of top.fixes.slice(0, 2)) html += `<li>${esc(fx)}</li>`;
    html += `</ol></div>`;
  } else if (!top) {
    html += `<p class="none" style="margin:0 0 12px">${t("verdict.noRule")}</p>`;
  }

  html += `<div class="actions">
    ${top && top.fixes && top.fixes.length
      ? `<button class="ghost" data-copy="fix" data-finding="0">${t("act.copyFix")}</button>` : ""}
    <button class="ghost" data-copy="md">${t("act.copyMd")}</button>
    <a class="linkbtn ghost" href="${ISSUE_URL}" target="_blank" rel="noopener">${t("act.issue")}</a>
  </div></div>`;
  return html;
}

function overview(findings) {
  if (!findings.length) return "";
  const counts = {};
  for (const f of findings) counts[f.severity] = (counts[f.severity] || 0) + 1;
  const detail = Object.entries(counts)
    .sort((a, b) => (SEV_RANK[b[0]] || 0) - (SEV_RANK[a[0]] || 0))
    .map(([k, v]) => `${v} ${sevLabel(k)}`)
    .join(" · ");
  return `<div class="overview"><b>${t("ov.findings", { n: findings.length })}</b>` +
         `<span class="counts">${esc(detail)}</span></div>`;
}

function findingsCard(findings) {
  let html = `<div class="card"><h2>${t("findings.title")}</h2>`;
  findings.forEach((fd, i) => {
    html += `<div class="finding">`;
    html += `<h3><span class="sev ${esc(fd.severity)}">${esc(sevLabel(fd.severity))}</span> ${esc(fd.title)}</h3>`;
    if (fd.explanation) html += `<p>${esc(fd.explanation)}</p>`;
    if (fd.suspects && fd.suspects.length)
      html += `<p><span class="label" style="margin:0">${t("findings.blame")}</span> ${fd.suspects.map(esc).join(", ")}</p>`;
    if (fd.fixes && fd.fixes.length) {
      html += `<div class="label">${t("findings.fixes")}</div><ul>`;
      for (const x of fd.fixes) html += `<li>${esc(x)}</li>`;
      html += `</ul><button class="ghost" data-copy="fix" data-finding="${i}">${t("findings.copyFixes")}</button>`;
    }
    if (fd.evidence && fd.evidence.length) {
      html += `<div class="label">${t("findings.evidence")}</div>`;
      for (const ev of fd.evidence.slice(0, 3))
        html += `<div class="evidence">${esc(ev)}</div>`;
    }
    if (fd.refs && fd.refs.length)
      html += `<p>${fd.refs.map((r) => `<a href="${esc(r)}" rel="noopener">${esc(r)}</a>`).join(" · ")}</p>`;
    html += `</div>`;
  });
  return html + `</div>`;
}

function envDetails(s) {
  const line = envLine(s);
  const meta = summaryBits(s).filter(([id]) => id !== "root");
  return `<details class="env"><summary>${t("env.summary")}${line ? " · " + esc(line) : ""}</summary>
    <div class="meta">${meta.map(([id, v]) =>
      `<div><span>${t("env." + id)}:</span> <b>${esc(v)}</b></div>`).join("")}</div>
  </details>`;
}

function render(doc, opts) {
  LAST = doc;
  const focus = !opts || opts.focus !== false;
  const s = doc.summary || {};
  const findings = (doc.findings || []).slice().sort(bySeverity);
  const tri = doc.triage || null;
  const suspects = (tri && tri.suspects) || [];
  const top = findings[0] || null;

  const html = [
    verdictCard(s, top, suspects[0] || null),
    overview(findings),
    findings.length ? findingsCard(findings) : "",
    envDetails(s),
    `<details class="raw"><summary>${t("raw.summary")}</summary>` +
      `<pre>${esc(JSON.stringify(doc, null, 2))}</pre></details>`,
  ].join("");

  $("out").innerHTML = html;
  wireCopy();
  if (focus) focusVerdict();
}

function focusVerdict() {
  const h = $("verdict-title");
  if (!h) return;
  // Focus management, not aria-live, for the result: a screen reader reads the
  // verdict heading from the top instead of announcing a whole DOM subtree.
  h.focus({ preventScroll: true });
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  h.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
}

/* ------------------------------------------------------------------ copy */

function fixesText(doc, index) {
  const fd = (doc.findings || [])[Number(index)];
  if (!fd) return "";
  const head = `[${sevLabel(fd.severity)}] ${fd.title}`;
  const steps = (fd.fixes || []).map((x, i) => `${i + 1}. ${x}`).join("\n");
  return steps ? `${head}\n${steps}` : head;
}

function toMarkdown(doc) {
  const s = doc.summary || {};
  const f = doc.findings || [];
  const tri = doc.triage || null;
  const out = [t("md.title"), ""];
  const env = [s.loader, s.loader_version].filter(Boolean).join(" ")
    + (s.minecraft_version ? " · " + t("env.mcVersion", { v: s.minecraft_version }) : "")
    + (s.java_major ? " · " + t("env.javaMajor", { v: s.java_major }) : "")
    + (s.mod_count ? " · " + t("env.modsCount", { n: s.mod_count }) : "");
  if (env.trim()) out.push(`${t("md.env")} ${env}`);
  if (s.root_cause) out.push(`${t("md.rootCause")} \`${s.root_cause}\``);
  if (tri && tri.suspects && tri.suspects.length) {
    const top = tri.suspects[0];
    out.push(`${t("md.suspect")} \`${top.modid}\` ${Math.round((top.confidence || 0) * 100)}%`);
  }
  out.push("");
  f.forEach((fd, i) => {
    out.push(`### ${i + 1}. [${sevLabel(fd.severity)}] ${fd.title}`);
    if (fd.explanation) out.push("", fd.explanation);
    if (fd.fixes && fd.fixes.length) {
      out.push("", t("md.fixes"));
      fd.fixes.forEach((x, j) => out.push(`${j + 1}. ${x}`));
    }
    out.push("");
  });
  out.push(t("md.footer"));
  return out.join("\n");
}

async function copyText(text, btn) {
  let ok = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      ok = true;
    }
  } catch (e) { ok = false; }
  if (!ok) {
    // Fallback for file:// or older browsers.
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    ta.remove();
  }
  $("copystatus").textContent = ok ? t("copy.ok") : t("copy.fail");
  if (btn) {
    const label = btn.textContent;
    btn.textContent = ok ? t("copy.btnOk") : t("copy.btnFail");
    setTimeout(() => { btn.textContent = label; }, 1400);
  }
}

function wireCopy() {
  document.querySelectorAll("#out [data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.copy;
      const text = kind === "md" ? toMarkdown(LAST) : fixesText(LAST, btn.dataset.finding);
      copyText(text, btn);
    });
  });
}

/* ----------------------------------------------------------------- input */

async function loadFile(file) {
  if (!file) return;
  if (file.size > MAX_BYTES) {
    showNotice("file.tooBig", { size: esc(fmtSize(file.size)) });
    return;
  }
  try {
    const text = await file.text();
    $("log").value = text;
    syncClear();
    if (looksLikeLink(text) || !looksLikeLog(text)) {
      showNotice("file.notLog");
    } else {
      showNotice("file.loaded", { name: esc(file.name), size: fmtSize(file.size) }, "ok");
    }
    $("go").focus();
  } catch (e) {
    showNotice("file.readFail", { msg: esc(e && e.message ? e.message : e) });
  }
}

/* ------------------------------------------------------------------ wire */

$("go").addEventListener("click", diagnose);

$("sample").addEventListener("click", () => {
  // sample.js (generated from a redacted real report by
  // tools/make_web_sample.py) when present; tiny built-in fallback otherwise.
  $("log").value = window.MCD_SAMPLE || SAMPLE;
  syncClear();
  hideNotice();
  diagnose();
});

$("pick").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => {
  loadFile(e.target.files && e.target.files[0]);
  e.target.value = "";          // allow picking the same file again
});

$("clear").addEventListener("click", () => {
  $("log").value = "";
  $("out").innerHTML = "";
  LAST = null;
  syncClear();
  hideNotice();
  setStatus(ready ? "boot.ready" : "", ready ? "ok" : "");
  $("log").focus();
});

$("log").addEventListener("input", syncClear);

// Ctrl/Cmd+Enter in the textarea also diagnoses
$("log").addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") diagnose();
});

// Language toggle. aria-pressed on the pair is the state; the announcement
// goes through the existing live region so screen readers hear the switch.
document.querySelectorAll(".lang button").forEach((b) => {
  b.addEventListener("click", () => {
    if (b.dataset.lang === LANG) return;
    setLang(b.dataset.lang, { announce: true });
  });
});

// Drag and drop: a crash report is a file, not something you retype.
const drop = $("drop");
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => {
    e.preventDefault();
    drop.classList.add("over");
  }));
["dragleave", "dragend"].forEach((ev) =>
  drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) loadFile(f);
});
// A file dropped outside the box must not navigate away from the app, but a
// drag *inside* the box still has to reach the textarea.
window.addEventListener("dragover", (e) => {
  if (!drop.contains(e.target)) e.preventDefault();
});
window.addEventListener("drop", (e) => {
  if (!drop.contains(e.target)) e.preventDefault();
});

setLang(preferredLang());
boot();
