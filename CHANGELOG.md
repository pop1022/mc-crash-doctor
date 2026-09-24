# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Blind evaluation + misattribution rate** (ROADMAP 1B.1/1B.2):
  `tools/blind_eval.py` splits the harvested corpus into dev/blind sets
  deterministically (rule-provenance pins forced to dev -- a rule is never
  blind-tested on its motivating report; the rest hash-split). On the 218
  blind reports: 65% diagnosed, 100% root-cause extraction, 0 parse errors;
  dev 69% -- no meaningful overfitting. Attribution scored DIRECTION-AWARE
  against maintainer verdicts (bug_in_this_mod -> top-1 must be the repo's
  mod; root_cause_elsewhere -> top-1 must be external; ambiguous verdicts
  reported not scored): blame-error rate 1/7 (14%). The single error
  (Mekanism/8455, Sinytra Connector interaction invisible to stack-frame
  attribution) is investigated, documented in corpus/BLIND_EVAL.md as a
  known method limit, and pinned by
  tests/test_blind_eval.py::test_direction_aware_scoring_on_known_samples.
  Machine-readable result: corpus/blind-eval.json (redaction-checked).
- **Rule provenance + lifecycle metadata** (ROADMAP 1A.3): every rule's YAML
  now carries `provenance.fixtures` (the real reports and/or synthetic
  fixtures that prove it, plus optional `expect_suspects`) and
  `lifecycle_status` (`draft → experimental → verified → stable →
  deprecated → retired`; `Rule.from_dict` rejects invalid values at load).
  `tools/stamp_provenance.py` scans all corpora and stamps evidence into the
  YAMLs (text-level insert preserving every comment; idempotent). Result:
  41/41 rules have fixtures — **37 verified** (real-corpus evidence),
  **4 experimental** (synthetic-only; auto-upgradable when a real report
  fires them). `tests/test_gaps.py` now reads its 24 pins from rule metadata
  instead of a hardcoded dict (single source of truth, with an empty-pins
  false-green guard); `tests/test_rule_metadata.py` (9 tests) enforces the
  contract. CONTRIBUTING's rule-authoring flow updated to match.
- **Compatibility edges** (ROADMAP 1A.2): `tools/build_compat_edges.py`
  mines the 454-fragment harvested corpus into 9,895 aggregated
  CompatibilityClaims (`corpus/compat-edges.jsonl`, format documented in
  `corpus/COMPAT_EDGES.md`) — deduped by (subject, object, relation, loader,
  mc_version), joined to maintainer verdicts from the redacted index
  (3,531 claims carry weak supervision). Relations: `caused` (82) /
  `suspected` (92) / `co_occurred` (9,721, explicitly presence-not-guilt).
  This is the seed pipeline for the Compatibility Graph (VISION line 5),
  built years early because graphs eat structured data. Record-only —
  nothing queries it yet. Diagnosis stays a pure function; edges are built
  offline and reproducibly.
- **Incident schema v1.0** (ROADMAP 1A.1): `data/schemas/incident.v1.json`
  (JSON Schema draft 2020-12) pins the diagnosis document contract.
  `build_incident()` in `mcd/report/render.py` is now the single source of
  truth — the CLI `--json`, the browser app, and any future API all emit
  exactly this shape, stamped with `schema_version`. The web app had already
  drifted (inline doc, missing the version field); fixed by sharing the
  builder and re-verifying end-to-end in the browser (7/7 acceptance).
  `tests/test_schema.py`: 78 conformance tests (fixtures + corpus samples +
  empty-input edge case); `jsonschema` added to the `[test]` extra and CI.
- **Web app** (`web/`): a Pyodide (WASM Python) static site that runs the
  *same* `diagnose()` pipeline as the CLI, entirely client-side — the pasted
  log never leaves the browser. Built by `tools/build_web.py` (wheel +
  manifest + demo sample). **Verified end-to-end in a real browser**
  (headless Edge over CDP, `tools/verify_web_e2e.py`): engine boots, the
  75 KB redacted demo report diagnoses to `hang.watchdog` with **lithium**
  attributed, and the suspect chip / severity badge / fix steps / evidence
  lines all render. 6/6 acceptance checks pass.
- `web/sample.js` + `tools/make_web_sample.py`: the demo report is a real
  ground-truth fixture (the 22.42.32 watchdog hang), reduced to
  header+stacktrace+System Details and passed through the corpus `redact()`
  plus a path scrub, with a leak guard that refuses to write if any username /
  IPv4 / drive path survives. Regenerated on every `build_web.py` run so it
  can't drift from the engine.
- **`Suspected Mods:` attribution** — vanilla/Fabric print their own verdict
  into the crash report; we now parse it (`rep.suspected_mods`) and feed it as
  the highest-weight triage signal (`W_GAME_SUSPECTED=12`, above mixin's 10).
  On the 42 harvested reports that carry the line, our top-1 suspect matches
  the game's first-listed mod 90% of the time.
- 8 rules from the 12-repo corpus expansion (33 → 41), every one pinned to
  the real report that motivated it: `mod.binary-incompat` (NoSuchField/
  MethodError), `mod.linkage-duplicate` (LinkageError / loader constraint),
  `quilt.config-broken` (JSON5 strict-mode), `loader.namespace-missing`
  (mappings not loaded), `mixin.injection-failed` (@WrapOperation / LVT),
  `crash.registry-load-failed`, `net.connectivity` (UnknownHost / cert),
  `env.headless-jvm` (libawt missing).
- `tests/verify_new_rules.py`: corpus hit-check + evidence-backed firing
  guard (a rule may only fire where its own evidence line is present).
- Synthetic fixtures for the 4 rules that never fire on the real corpora
  (`oom.save-time`, `oom.gc-overhead`, `disk.space`, `native.gl`) — each
  proves its rule on a clearly-marked SYNTHETIC report shaped like a real
  one, plus `tests/test_rule_fixtures.py` (7 tests) with negative guards
  (save-time must not fire without a chunk-save path; native.gl must not
  fire on mixin errors).
- `.github/workflows/pages.yml`: build + deploy the web app to GitHub Pages
  with a PII guard on `sample.js` before upload. First-run deployment needs
  a one-time manual enable (Settings → Pages → Source: GitHub Actions) —
  GITHUB_TOKEN cannot create the Pages site even with `pages: write`
  (GitHub limitation); tracked in ROADMAP 0.2.

### Fixed
- **`native.gl` misdiagnosed mixin failures as graphics problems** — its
  `exception` alternation wrongly included
  `org.spongepowered.asm.mixin.InjectionError` (copy-paste), so any mixin
  injection failure with an "OpenGL"-ish word nearby could render as a
  driver issue. Now LWJGL/OpenGL/GLFW exceptions only; pinned by
  `test_native_gl_does_not_fire_on_mixin_injection`.
- **Log-file FATAL root-cause selection** — `_parse_exceptions` only captured
  the FIRST top-level exception, so on log files it latched onto early
  WARN/INFO noise (e.g. fabric-loader#611: a config-read
  `NumberFormatException`) and missed the real `/FATAL] Unreported
  exception thrown!` crash below it. Now every top-level header starts a new
  block, FATAL-introduced blocks are flagged (`ExceptionBlock.fatal`), and
  `root_cause` prefers the last FATAL chain. This was silently misdiagnosing
  every multi-exception log.

### Added (earlier this cycle)
- `runtime-crashes.yaml` rule pack (7 rules), derived from 20 real harvested
  reports that the first two packs left undiagnosed: NeoForge/Fabric
  load-failure wordings, client-only class on dedicated server, threading
  violations, block-entity rendering, datapack/book failures, and an
  attributed runtime catch-all gated on `has_suspect` (never fires without
  a named mod).
- Rule engine: `has_suspect` condition and `{{suspect_top}}` /
  `{{suspect_top_id}}` / `{{suspect_top_conf}}` placeholders — rules can now
  build on attribution results.
- Attribution: exception-message class mining (`message_modids`). Java 14+
  NPE/CCE messages quote fully-qualified class names, which resolves the
  owning mod even for issue-tracker fragments with no Mod List. Added
  `mekanism.api` package override.
- `tests/test_gaps.py`: 15 harvested reports pinned to the rules that must
  fire (and the suspects that must be attributed); corpus-wide diagnosis
  rate floor (≥50%) with a tight absolute bound on the original Mekanism
  subset; catch-all honesty check on the full vendored corpus.

### Changed
- Corpus expansion: 34 → 454 crash fragments from 12 mod repositories
  (fabric-loader, fabric-api, Mekanism, Jade, RFTools, Curios,
  twilightforest, sodium, quilt-loader, ModernFix, Placebo,
  TinkersConstruct), 125 with weak-supervision maintainer labels.
- `mod.incompatible-set` rewritten against real Fabric resolver wordings
  ("Some of your mods are incompatible with the game or each other",
  "mod 'X' requires any 0.8.x version ... but only the wrong version is
  present"): blind FormattedException fragments 11 → 0.
- Harvested-corpus diagnosis rate: 55.7% overall (Mekanism subset 91%,
  RFTools 88%, Curios 81%); the old 34-fragment numbers (31/34) predate
  the expansion and are not comparable.
- `test_blind_spots_stay_bounded` is now scale-free: an absolute `blind ≤ 3`
  assertion was written for the 34-fragment corpus and became meaningless at
  454 fragments (more issues ⇒ more blind spots even with better rules).
  Replaced with a rate floor + per-subset bound.
- `run_tests.sh` / CI now run the whole `tests/` directory (corpus + gaps).
- Rule count 25 → 33.

## [0.1.0] - 2026-09-22

Initial release.

### Added
- **Parser** (`mcd/parser/`): crash reports and server/client logs for
  Forge, NeoForge, Fabric, Quilt, the Bukkit family (Paper/Purpur/Folia/
  Spigot/CraftBukkit/Glowstone), Forge-Bukkit hybrids (Magma/Mohist/
  Arclight/CatServer), proxies (Velocity/Waterfall/BungeeCord), Bedrock-side
  (Bedrock/PocketMine/Geyser) and launchers (Prism/MultiMC/vanilla) on a
  separate axis. Extracts exception chains, `Caused by` roots, full Mod List
  (tested at 266 mods), stack-frame provenance (`~[jar]`, mixin configs,
  `from mod (id)`), System Details, memory triple, JVM flags, Java/MC/loader
  versions (NeoForge MC version reverse-derived from its build number).
- **Rule engine** (`mcd/rules/`): declarative YAML rules, 25 across two
  builtin packs; user rule dirs via `MCD_RULES_PATH`; malformed rule files
  warn instead of crashing diagnosis.
- **Attribution** (`mcd/triage/`): suspect-mod ranking from mixin ownership,
  mod-owned stack frames and jar names, cross-indexed against the report's
  Mod List; flags likely two-mod interactions instead of forcing one culprit.
- **Renderers**: rich terminal, plain text, JSON, Markdown.
- **CLI**: file / `--dir` / `--stdin` / `--url` (mclo.gs aware) /
  `--json` / `--markdown` / `--exit-code`; `mc-crash-doctor` and `mcd`
  entry points; lazy-import package root.
- **Corpus tooling**: `tools/harvest_corpus.py` (mod-repo issue harvester
  with mclo.gs/gist/pastebin dereferencing, PII redaction, maintainer-label
  weak supervision), `tools/verify_seed_repos.py`, `tools/fetch_aternos_corpus.py`,
  `tools/seed_repos.txt` (15 verified targets).
- **Tests**: four gates in `run_tests.sh` — redaction (25 cases), parser
  accuracy vs upstream expectations, end-to-end + ground truth (6 real
  reports incl. negative assertions), CLI smoke. CI on Python 3.9/3.11/3.13
  with a wheel-packaging check.

### Measured
- Platform detection: **201/201 (100%)** on the vendored codex-minecraft
  corpus.
- Version detection: **176/177 (99.4%)**; the single miss is a corpus file
  containing two contradictory versions (we take the software's own banner).
- Ground truth: **6/6** on real 266-mod Forge 1.20.1 server reports
  (4 heap OOM, 2 ServerHangWatchdog), with attribution resolving lithium
  and harium at 0.97 confidence.
- Zero parse/run errors across 235 corpus files (201 vendored + 34 harvested).

### Fixed (during pre-release development)
- IPv4 redaction blanked Mod List version columns (`|jei |15.20.0.129|` →
  `<IP>`) — now context-gated to real network addresses only.
- Platform probe precedence: hybrids (Magma/Mohist/Arclight) outrank the
  Forge/Bukkit families they embed; Quilt outranks Fabric (shared Knot
  loader); launcher and loader detected on separate axes; platform banners
  deep inside large reports (>40 KB) are found.
- `java.lang.Error` exception-header regex (ServerHangWatchdog reports).

[Unreleased]: https://github.com/pop1022/mc-crash-doctor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pop1022/mc-crash-doctor/releases/tag/v0.1.0
