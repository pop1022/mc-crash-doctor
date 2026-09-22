# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
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
- `tests/test_gaps.py`: 11 harvested reports pinned to the rules that must
  fire (and the suspects that must be attributed); blind-spot bound (≤3);
  catch-all honesty check on the full vendored corpus.

### Changed
- Harvested-corpus coverage: diagnosed 14/34 → 31/34; attributed 15/34 →
  19/34 (56%). The 3 remaining blind spots are generic exceptions with pure
  vanilla stacks — deliberately not guessed at.
- `run_tests.sh` / CI now run the whole `tests/` directory (corpus + gaps).
- Rule count 25 → 32.

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
