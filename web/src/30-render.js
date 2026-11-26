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

function verdictCard(s, top, topSus, note, suspects) {
  const sev = top ? esc(sevLabel(top.severity)) : "";
  // The engine cuts a raw exception at ~85 characters, which reads as broken
  // text in a 28px head. The finding's own sentence is the human version of the
  // same fact; the exception string stays, verbatim, one line below in mono.
  const head = (top && top.title) || s.root_cause || s.description || t("verdict.parsed");
  const meta = [s.root_cause ? s.description : null,
                s.is_server ? t("env.server") : s.is_client ? t("env.client") : null]
    .filter(Boolean).join(", ");

  let html = `<div class="card verdict">`;
  if (top) {
    html += `<div class="statusline"><span class="sev ${esc(top.severity)}">${sev}</span>` +
            `<span class="where">${t("verdict.rootCause")}</span></div>`;
  }
  html += `<h2 id="verdict-title" tabindex="-1">${esc(head)}</h2>`;
  if (meta) html += `<p class="cause-meta">${esc(meta)}</p>`;
  if (top && s.root_cause && s.root_cause !== head) {
    // The summary carries the full first line now; the clamp is CSS (two
    // lines, ellipsis). Appending "…" in JS was a lie about the data: it
    // marked complete strings as truncated.
    html += `<p class="cause-raw">${esc(s.root_cause)}</p>`;
  }

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
    // The number is a weighted score, not a calibrated probability of being
    // right. Saying "97%" alone invites reading it as "97% chance this is it".
    html += `<p class="card-note">${t("verdict.strengthNote")}</p>`;
  }

  // Two suspects within 20 points: the evidence does not pick one, and saying
  // "lithium" anyway is how a user deletes the wrong mod. Say so, and give the
  // one-at-a-time bisect instead of a batch removal.
  const tie = (suspects && suspects.length > 1)
    ? ((suspects[0].confidence || 0) - (suspects[1].confidence || 0)) < 0.2
    : false;
  if (tie) {
    const a = suspects[0], b = suspects[1];
    html += `<div class="tie"><span class="k">${t("tie.title")}</span>` +
      `<p>${t("tie.body", {
        a: esc(a.name || a.modid), pa: Math.round((a.confidence || 0) * 100),
        b: esc(b.name || b.modid), pb: Math.round((b.confidence || 0) * 100),
      })}</p></div>`;
  } else if (!topSus && top) {
    html += `<p class="card-note">${t("noSuspect.note")}</p>`;
  }

  // Order is the reader's order: what -> which line -> what to do -> how to
  // check and undo. The reasons used to be an unlabelled bullet list under the
  // suspect, which read as more opinion; labelled, they are the evidence.
  const evidence = (topSus && topSus.reasons && topSus.reasons.length)
    ? topSus.reasons.slice(0, 2)
    : ((top && top.evidence) || []).slice(0, 2);
  if (evidence.length) {
    html += `<div class="anchor"><span class="k">${t("verdict.anchor")}</span><ul class="why">` +
      evidence.map((r) => `<li>${esc(r)}</li>`).join("") + `</ul></div>`;
  }

  if (top && top.fixes && top.fixes.length) {
    html += `<div class="starthere"><span class="k">${t("verdict.startHere")}</span><ol>`;
    for (const fx of top.fixes.slice(0, 2)) html += `<li>${esc(fx)}</li>`;
    html += `</ol></div>`;
  } else if (!top) {
    html += `<p class="none" style="margin:0 0 12px">${t("verdict.noRule")}</p>`;
  }

  if (top) {
    // The last evidence entry is the specific one ("single server tick took
    // 120.00 seconds"), the first is usually the exception class, which every
    // Java crash contains and is useless as a "is it fixed" search string.
    const ev = (top.evidence || []);
    const line = (ev.length ? ev[ev.length - 1] : "") || t("verify.anchorFallback");
    html += `<div class="verify">
      <p><span class="k">${t("verify.title")}</span> ${t("verify.body", { line: "<code>" + esc(line) + "</code>" })}</p>
      <p><span class="k">${t("verify.undoTitle")}</span> ${t("verify.undo")}</p>
    </div>`;
  }

    html += `<div class="actions">
    <button class="ghost" data-feedback>${t("act.feedback")}</button>
    ${top && top.fixes && top.fixes.length
      ? `<button class="ghost" data-copy="fix" data-finding="0">${t("act.copyFix")}</button>` : ""}
    <button class="ghost" data-copy="md">${t("act.copyMd")}</button>
    <a class="linkbtn ghost" href="${ISSUE_URL}" target="_blank" rel="noopener">${t("act.issue")}</a>
  </div>${note ? `<p class="card-note">${esc(note)}</p>` : ""}</div>`;
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
      {
        const names = fd.suspects.slice(0, 3).map(esc).join(", ");
        const rest = fd.suspects.length - 3;
        html += `<p><span class="label" style="margin:0">${t("findings.blame")}</span> ${names}` +
                (rest > 0 ? ` <span class="more">+${rest}</span>` : "") + `</p>`;
      }
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

// Prose is not a report. Before this card existed, pasting a sentence produced
// "the report parsed cleanly, no rule matched" -- a false statement about the
// input, and the opposite of the honesty the tool sells.
function notAReportCard() {
  return `<div class="card verdict verdict--weak">
    <h2 id="verdict-title" tabindex="-1">${t("weak.title")}</h2>
    <p class="cause-meta">${t("weak.body")}</p>
    <ul class="why">
      <li>${t("weak.li1")}</li>
      <li>${t("weak.li2")}</li>
      <li>${t("weak.li3")}</li>
    </ul>
  </div>`;
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
  const weak = !!(opts && opts.weakInput) && !findings.length;

  // Weak input gets one card and nothing else: environment details and the raw
  // JSON of a sentence would invent facts (a "vanilla 1.20.1 server") that were
  // never in the text.
  const html = weak
    ? notAReportCard()
    : [
        verdictCard(s, top, suspects[0] || null, opts && opts.note, suspects),
        overview(findings),
        findings.length ? findingsCard(findings) : "",
        envDetails(s),
        `<details class="raw"><summary>${t("raw.summary")}</summary>` +
          `<pre>${esc(JSON.stringify(doc, null, 2))}</pre></details>`,
      ].join("");

  $("out").innerHTML = html;
  const empty = $("out-empty");
  if (empty) empty.hidden = true;
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
  document.querySelectorAll("#out [data-feedback]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!LAST_TEXT) return;
      try {
        const url = pyodide.globals.get("mcd_feedback")(LAST_TEXT, LANG);
        window.open(url, "_blank", "noopener");
      } catch (e) {
        console.error(e);
        $("copystatus").textContent = t("act.feedbackFail");
      }
    });
  });
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

