/* ------------------------------------------------------------------ wire */

$("go").addEventListener("click", async () => {
  if (!ready) { await ensureEngine(); if (!ready) return; }
  diagnose();
});

$("sample").addEventListener("click", async () => {
  // Fetched on first use (see ensureSample): 78 KB of real report text is not
  // worth delaying anything else for.
  $("log").value = await ensureSample();
  syncClear();
  hideNotice();
  if (!ready) {
    // Answer now with the build-time diagnosis, then let the engine replace it
    // with the identical result once Pyodide is up. If the engine never comes
    // up the sample still works, which is the only state where that matters.
    const shown = await showPrecomputedSample();
    await ensureEngine();
    if (!ready) {
      if (shown) showNotice("sample.offline", undefined, "info");
      return;
    }
  }
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
  const empty = $("out-empty");
  if (empty) empty.hidden = false;
  LAST = null;
  LAST_TEXT = "";
  LAST_ORIGIN = "";
  syncClear();
  hideNotice();
  setStatus(ready ? "boot.ready" : "boot.idle", ready ? "ok" : "");
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
setStatus("boot.idle");
