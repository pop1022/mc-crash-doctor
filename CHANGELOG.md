# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Web app** (`web/`, work in progress): a Pyodide (WASM Python) static site
  that runs the *same* `diagnose()` pipeline as the CLI, entirely client-side
  — the pasted log never leaves the browser. Built by `tools/build_web.py`
  (wheel + manifest); deployable to GitHub Pages. **Status: assets written and
  the wheel verified to contain the rule YAMLs, but the in-browser end-to-end
  check did NOT run** — the local browser harness failed to start
  (`daemon didn't come up`), so boot + sample-diagnosis is still unverified.
  Do not advertise the web app until that passes.
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

### Fixed
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

[Unreleased]: https://github.com/YOURNAME/mc-crash-doctor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YOURNAME/mc-crash-doctor/releases/tag/v0.1.0
