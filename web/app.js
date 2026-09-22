/* mc-crash-doctor web UI.
 *
 * Loads Pyodide (CPython compiled to WASM), micropip-installs the project
 * wheel from wheel-manifest.json, then runs the SAME parse -> rules -> triage
 * pipeline as the CLI, entirely client-side. The pasted log is never sent
 * anywhere -- that is the whole point of this deployment model.
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

let pyodide = null;
let ready = false;

const $ = (id) => document.getElementById(id);

function setStatus(msg, isErr = false) {
  const el = $("status");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
}

async function boot() {
  try {
    pyodide = await loadPyodide();
    setStatus("installing packages…");
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
    from mcd.report.render import build_summary
    doc = {
        "summary": build_summary(rep),
        "findings": [f.to_dict() for f in findings],
        "triage": t.to_dict() if t else None,
    }
    return json.dumps(doc, ensure_ascii=False)
`);
    ready = true;
    $("go").disabled = false;
    $("sample").disabled = false;
    setStatus("engine ready — paste a crash report and hit Diagnose");
  } catch (e) {
    console.error(e);
    setStatus("engine failed to load: " + (e && e.message ? e.message : e), true);
  }
}

const SEV_RANK = { fatal: 4, error: 3, warning: 2, hint: 1, info: 0 };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function render(doc) {
  const s = doc.summary || {};
  const f = doc.findings || [];
  const t = doc.triage || null;
  let html = "";

  // summary card
  const meta = [
    ["root cause", s.root_cause],
    ["loader", [s.loader, s.loader_version].filter(Boolean).join(" ") || null],
    ["minecraft", s.minecraft_version],
    ["java", s.java_version],
    ["mods", s.mod_count],
    ["heap", s.heap_max_mib ? `${s.heap_used_mib ?? "?"}/${s.heap_max_mib} MiB` : null],
    ["side", s.is_server ? "server" : s.is_client ? "client" : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (meta.length || s.description) {
    html += `<div class="card"><h2>${s.description ? esc(s.description) : "Report summary"}</h2><div class="meta">`;
    for (const [k, v] of meta) html += `<div><span>${esc(k)}:</span> <b>${esc(v)}</b></div>`;
    html += `</div></div>`;
  }

  // suspects card
  const suspects = (t && t.suspects) || [];
  if (suspects.length) {
    html += `<div class="card"><h2>🎯 Suspect mod${suspects.length > 1 ? "s" : ""}</h2><div class="suspects">`;
    for (const sp of suspects.slice(0, 4)) {
      const name = sp.name || sp.modid;
      const conf = Math.round((sp.confidence || 0) * 100);
      html += `<div class="suspect"><b>${esc(name)}</b> <span class="conf">${conf}%</span>${sp.version ? ` <span class="conf">v${esc(sp.version)}</span>` : ""}</div>`;
    }
    html += `</div>`;
    const top = suspects[0];
    if (top && top.reasons && top.reasons.length) {
      html += `<div class="label">why</div><ul>`;
      for (const r of top.reasons.slice(0, 4)) html += `<li>${esc(r)}</li>`;
      html += `</ul>`;
    }
    html += `</div>`;
  }

  // findings
  if (!f.length) {
    html += `<div class="card"><p class="none">No rule matched this report. It may be a vanilla crash we don't cover yet — ` +
      `<a href="https://github.com/pop1022/mc-crash-doctor/issues/new?template=crash-not-covered.md">open a “crash not covered” issue</a> ` +
      `with the report (redact private paths first) and it becomes the next rule + test.</p></div>`;
  } else {
    const ordered = [...f].sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0));
    html += `<div class="card"><h2>🩺 Diagnosis (${f.length})</h2>`;
    for (const fd of ordered) {
      html += `<div class="finding">`;
      html += `<h3><span class="sev ${esc(fd.severity)}">${esc((fd.severity || "").toUpperCase())}</span>${esc(fd.title)}</h3>`;
      if (fd.explanation) html += `<p>${esc(fd.explanation)}</p>`;
      if (fd.suspects && fd.suspects.length)
        html += `<p><span class="label" style="margin:0">blame:</span> ${fd.suspects.map(esc).join(", ")}</p>`;
      if (fd.fixes && fd.fixes.length) {
        html += `<div class="label">fixes</div><ul>`;
        for (const x of fd.fixes) html += `<li>${esc(x)}</li>`;
        html += `</ul>`;
      }
      if (fd.evidence && fd.evidence.length) {
        html += `<div class="label">evidence</div>`;
        for (const ev of fd.evidence.slice(0, 3)) html += `<div class="evidence">${esc(ev)}</div>`;
      }
      if (fd.refs && fd.refs.length)
        html += `<p>${fd.refs.map((r) => `<a href="${esc(r)}" rel="noopener">${esc(r)}</a>`).join(" · ")}</p>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  html += `<details class="raw"><summary>raw JSON</summary><pre>${esc(JSON.stringify(doc, null, 2))}</pre></details>`;
  $("out").innerHTML = html;
}

function diagnose() {
  if (!ready) return;
  const text = $("log").value;
  if (!text.trim()) {
    setStatus("nothing to diagnose — paste a crash report first", true);
    return;
  }
  $("go").disabled = true;
  setStatus("diagnosing…");
  // run on the next tick so the status paints before the WASM call blocks
  setTimeout(() => {
    try {
      const json = pyodide.globals.get("mcd_diagnose")(text);
      render(JSON.parse(json));
      const n = (JSON.parse(json).findings || []).length;
      setStatus(n ? `${n} finding${n > 1 ? "s" : ""} — see below` : "done — no rule matched");
    } catch (e) {
      console.error(e);
      setStatus("diagnosis failed: " + (e && e.message ? e.message : e), true);
    } finally {
      $("go").disabled = false;
    }
  }, 30);
}

$("go").addEventListener("click", diagnose);
$("sample").addEventListener("click", () => {
  $("log").value = SAMPLE;
  diagnose();
});
// Ctrl/Cmd+Enter in the textarea also diagnoses
$("log").addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") diagnose();
});

boot();
