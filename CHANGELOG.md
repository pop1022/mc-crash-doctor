# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **`tools/suggest_rules.py` — candidate rule *review*, not rule generation**
  (ROADMAP 1E.3). Two halves, and the split is the point:

  `--report` is deterministic and offline. It clusters the reports no rule fires
  on and prints, for each cluster, the two numbers that decide whether a rule is
  worth writing: how many reports it holds, and whether its message is reusable
  or specific to one report. `--ingest` is the only door into
  `corpus/rule-drafts/`, and it refuses a candidate that is not `draft`, whose id
  does not start with `candidate.`, whose fixtures do not resolve, that lacks
  `generated_by: {model, date}`, or that **fires on no report in the corpus**.

  Nothing in it calls a network. "LLM-assisted" here means the model writes YAML
  and the tool decides whether it is admissible — which is the only arrangement
  where "model output never reaches `builtin/`" is a fact rather than a policy.

- **`corpus/RULE_CANDIDATES.md` / `rule-candidates.json`** — the pack. 107
  clusters over 117 undiagnosed reports, each with a `when` skeleton and a
  generalisation verdict (`reusable` / `needs_generalisation` / `singleton` /
  `singleton+overfit`, the last when the message carries a UUID, a coordinate, a
  long number or a path).

- **`corpus/rule-drafts/candidate-debug-crash.yaml`** — the one candidate the
  measurement justified. Five reports share `Description: Manually triggered
  debug crash`, i.e. the user pressed F3+C to *produce* a report, and all five
  are attachments to unrelated complaints (flickering, texture bleed, an FPS
  drop, a freeze, "video settings won't open"). Today the tool says nothing on
  them, which reads as "could not diagnose" when the honest answer is "nothing
  here is broken".

- **`tests/test_rule_drafts.py`** — 9 tests re-checking every draft on disk, plus
  `test_no_draft_rule_is_in_builtin` for the other direction. Cost: 0.25 s.

- **`tests/test_rule_candidates.py` — a drift guard for the candidate pack.**
  The pack's third line ("117 of 454 uncovered, 107 clusters, top-10 = 17%,
  therefore R4 fires") is the sentence every later decision quotes, and
  `uncovered` is computed *twice*: once by `coverage_report.py` and once by
  `suggest_rules.py`, from the same corpus and the same ruleset. Add a rule,
  refresh `coverage.json` (which the coverage gate does) and forget this pack,
  and the repository ships a document contradicting its own coverage report —
  and a stale number looks exactly like a fresh one. So: 14 checks, 0.07 s,
  all of them arithmetic over the two committed files plus a cross-check
  against `coverage.json`; the real regeneration (35 s, parses 454 fragments)
  sits behind `MCD_DRIFT_FULL=1`, same split as `tools/blind_eval.py`. Verified
  in the failing direction three times: a planted `uncovered=118` reddens five
  checks, quietly lowering `R4_MIN_SHARE` from 0.30 to 0.10 reddens the R4
  check, and an unterminated quote in a `when` block reddens the YAML
  round-trip.

- **`suggest_rules.py` corpus enumeration aligned with `coverage_report.py`**
  (recursive glob, flat corpus either way) and **one unparseable fragment no
  longer kills `--report`** — it is skipped and reported, which is what
  `coverage_report.py` already did. Both are pure robustness: regenerating the
  pack before and after produced byte-identical output.

- **`tests/test_frame_parse.py`** — 18 tests pinning the frame-line contract
  (ROADMAP 1E.5), one per row of the defect table below: both `[jar]` spellings,
  `{}` in either order, the four module-prefix spellings, a hyphenated Fabric
  method name, `<init>`/`<clinit>`, and a path inside the parameter list that
  must not be mistaken for a prefix. Two of them open real corpus reports
  (`CaffeineMC/sodium#3460`, `FabricMC/fabric-api#4922`) because the synthetic
  cases were written after the bug and share its blind spots.

- **`tools/parser_snapshot.py` now records frame *shape*, not only counts.**
  Its old fields could not see the repair below: the number of frames was
  57,282 before and after. `frames_sig` (a hash of every `cls|method|line`) and
  `frame_defects` (frames whose `cls` still contains `)` or `]`) are what named
  the 148 affected reports and what makes "everything else is unchanged" a
  checkable claim.

- **Attribution ablation — measuring the half of the attribution that is ours**
  (ROADMAP 1E.4). `tools/attribution_ablation.py` deletes each report's own
  ``Suspected Mods:`` line and re-runs attribution, then asks whether the
  remaining evidence still reaches a mod id. This exists because the obvious
  metric is circular: `triage()` gives that line weight 12, the highest in the
  table, so "our top-1 is in the game's list" is partly quoting the input back.

  Result over the 35 reports that carry a non-platform suspected-mod entry:
  **without the hint, attribution was silent on 20/35 (57%)** and agreed with
  the loader on 7 of the 15 that answered. The oracle is a heuristic, not
  ground truth, so the number bounds consistency rather than correctness —
  which is exactly why it does not replace the maintainer-verdict evaluation.

  `corpus/ATTRIBUTION_ABLATION.md` documents the before column, the two
  rejected refinements, and the one known gap left open;
  `attribution-ablation-before.json` keeps the pre-change run so the numbers
  are checkable rather than prose.

- **`tests/test_attribution_signals.py`** — 17 tests pinning the two findings
  that made the fix a fix: seed anchoring (a bare `$...$` scan returns
  `bridge`/`new`/`static`, not mod ids) and depth limiting (a crash-reporter
  mixin at frame #12 must not become the suspect).

- **Interval estimates on every published ratio** (ROADMAP 1E.2①):
  `tools/blind_eval.py` gains `wilson()` (Wilson score interval, z hard-coded
  so the number cannot drift with a library upgrade) and reports every rate as
  `k/n (p%) 95% CI [lo, hi]`. The same values land in `blind-eval.json` under
  `ci95`, including a `quotable_as_rate` flag per metric.

  Why it was not optional: the headline blame-error rate is **1/7**. The
  textbook normal approximation returns `0.143 ± 0.26` — a lower bound below
  zero, clipped to "0%", i.e. read as *could be perfect*. Wilson gives
  **[2.6%, 51.3%]**: the same seven reports are consistent with a 3% error rate
  and with a 51% one. Below `n=30` the tool now refuses the framing and prints
  "we documented exactly N failure mode(s)" instead. The previous roadmap note
  quoted `[2.6%, 39.9%]`, which was simply the wrong upper bound; corrected.

  `corpus/BLIND_EVAL.md` is regenerated against these numbers, and its earlier
  claim of "no significant overfitting" is **retracted**: the blind and dev
  intervals overlap almost completely, which means the comparison has no power
  in either direction.

  `tests/test_blind_eval.py` grows from 4 to 9: the headline 1/7 value is
  pinned against the naive interval that underflows, the 0/n and n/n edges are
  pinned (0.2775 / 0.7225), all k/n up to 40 are checked to stay inside
  [0, 1] and to bracket k/n, and one structural test asserts that every rate
  in `blind-eval.json` has a `ci95` entry that really brackets it — so a future
  metric cannot be published without its interval. Writing those tests exposed
  floating-point dust in `wilson()` itself (`10/10` returned `0.99999999999999`,
  `0/3` returned `5.5e-17`); the function now snaps to the boundary within 1e-12
  rather than printing "99.99999999999999%".

- **`tests/test_invariance.py`** (ROADMAP 1E.2②③) — 4 tests. A pair of
  synthetic reports carrying identical evidence with the two mods written in
  opposite order must agree on top-1; six real harvested reports must not move
  when their Mod List rows are reversed; and rewriting timestamps, dates,
  player name, world name, install path and UUIDs must leave both the rule set
  and the top-1 suspect untouched. One extra test asserts the scrubber actually
  changed the text, so the metamorphic test cannot pass vacuously.

- **`tools/parser_snapshot.py`** — `--write` / `--check` over the whole
  harvested corpus, recording per report the mod-row count and a hash of the
  rows (so a diff names the report, not 1,047 lines), exception and frame
  counts, suspected mods, loader and kind. This is the instrument behind the
  "454/454 byte-identical" claim below, and it is now runnable instead of
  being a sentence in a commit message. `--check` exits 1 and prints the
  differing reports and fields; verified both directions.

- **`tests/test_forge_modlist.py`** — 13 tests pinning the Mod List row
  contract (tab indentation, padding, short rows, tab-in-field, free-form sixth
  column) plus two cost guards: 200 malformed rows must parse in under 2 s, and
  doubling row length must not more than decuple the cost.

- **Mod manifest reader** (ROADMAP 1D.1): `mcd/metadata/manifest.py` reads
  `fabric.mod.json`, `quilt.mod.json`, `META-INF/mods.toml` and
  `META-INF/neoforge.mods.toml` into one `ModManifest` shape. Three loaders spell
  the same three relations differently, so everything is normalised to
  `required` / `optional` / `incompatible`, with a separate `hard` flag — Fabric
  `conflicts` only warns while `breaks` refuses to launch, and collapsing the two
  would make the tool reject packs that merely warn. Version ranges are preserved
  **verbatim** (`[1.20.1,1.21)`); interpreting Maven range semantics belongs to
  the version-mismatch check (ROADMAP 2.2), not to the reader.

  Metadata only: no class extraction, no bytecode execution, no signature
  verification — reading a jar means reading a small text file inside a zip.
  Standard library only; Python 3.9/3.10 have no `tomllib`, so a bounded TOML
  subset parser ships here and its agreement with `tomllib` is **asserted** by
  tests on 3.11+ rather than assumed. `tests/test_manifest.py`: 28 tests across
  all four formats, multi-mod jars, malformed jars, non-zip input, UTF-8 BOM,
  `#` inside a quoted value, multi-line arrays, and a regression guard that fails
  if declared negative edges ever stop being surfaced.

  Stated gap: fixtures are transcribed from each loader's documented format, not
  20 jars pulled from live modpacks — downloading third-party binaries is out of
  scope for an automated suite. Real `mods/` validation is deferred until
  someone points the tool at one.

- **Modrinth coverage audit** (ROADMAP 1D.0):
  `tools/audit_modrinth_mapping.py` + `corpus/MODRINTH_MAPPING.md`. Measures
  whether the corpus's mod identifiers resolve to Modrinth projects *before* any
  fetching pipeline is built. Deterministic sha256 sampling, conservative
  matching (exact slug, or exact normalised title — **no fuzzy acceptance**,
  because a wrong edge is worse than a missing one), one cache file per URL under
  `data/modrinth-cache/` (gitignored), serialised requests with a descriptive
  User-Agent, 429 backoff, and a hard request budget.

  Result: **45.8% of mod candidates resolve** (55/120; 95% interval ≈ 37–55%,
  i.e. it straddles the 40% gate — the pass is not decision-grade on its own),
  and **only 5 of 71 declared dependencies are `incompatible`** (7%; 3 of 25
  projects declare any). The second number is the one that matters: it says
  declared negative edges are too sparse to be a compatibility-graph backbone.

- **`evidence_tier` on every compatibility edge** (ROADMAP 1D.3):
  `corpus/compat-edges.jsonl` now carries `declared` / `maintainer_verdict` /
  `inferred` / `cooccurrence` alongside `relation`. The two fields are
  orthogonal by design — `relation` says *what* an edge asserts, `evidence_tier`
  says *on what kind of evidence*, because a `caused` claim resting on a
  maintainer's label is not worth the same as one resting on our own ranking.
  Before this, 9,721 presence-only pairs and 82 causal ones had the same shape,
  so any consumer that forgot to filter by `relation` would read co-presence as
  guilt. Distribution: `cooccurrence` 9,721 / `inferred` 163 /
  `maintainer_verdict` 11 / `declared` **0**.

  The tier is a **pure function** of `(relation, maintainer_verdict)`
  (`derive_evidence_tier()`), so the generator and the migration cannot diverge.
  `declared` is deliberately unreachable from this tool's inputs — it only reads
  crash reports and has never read a jar manifest — and a tripwire test fails on
  the first `declared` row so that adding 1D.2's author declarations has to be a
  conscious commit rather than a silent mix-in.

  Migration: `--rederive-tier` recomputes the field in place, idempotently,
  without rescanning the 454-file corpus. All 9,895 existing rows were stamped
  and verified against the git baseline: **0 rows changed beyond the new field**,
  relation counts unchanged (82 `caused` / 92 `suspected` / 9,721 `co_occurred`).

- **`tests/test_compat_edges.py`** (14 tests, 15 after the provenance guard) —
  `corpus/compat-edges.jsonl` previously had **no test at all**: 9,895 rows of
  derived data with nothing stopping downstream misuse. Pinned now: valid tiers,
  tier-matches-derivation (a hand-edited JSONL fails instead of laundering weak
  evidence into strong), co-occurrence cannot claim causality, causal edges
  cannot be silently downgraded, self-loop vs pairwise semantics, migration
  idempotence, refusal of typo'd relations, **the Incident document leaks no edge
  vocabulary**, and every cited report still exists in the current index.
  Efficacy checked both ways: flipping one `co_occurred` row's tier to `inferred`
  turned 2 tests red; restoring the file returned 14 green. The provenance guard
  was checked the same way: deleting one cited index row turned exactly 1 test
  red and named the report, restoring the index returned 15 green.

- **Coverage dashboard** (ROADMAP 1D.4): `tools/coverage_report.py` →
  `corpus/COVERAGE.md` + `corpus/coverage.json`. Runs the real rule engine over
  the whole corpus and cross-tabulates failure mode against "did anything fire",
  so the repository can finally answer the only question that orders the next
  unit of work: *which failure mode is undiagnosed, and how big is it?*
  **454 fragments, 67.2% diagnosed (305/454), 0 parse failures, 224s.**

  Buckets are an **input** property — exception kind, description text, loader,
  deepest throw site — never "which rule matched", because bucketing by rule
  output would make "uncovered" undefined by construction. Order is the
  contract (`other` last, only catch-all) and is pinned by tests.

- **`mcd/metadata/jars.py`**: one auditable definition of 库 / 模组 / 加载器 /
  未知 for jar filenames. `corpus/index.jsonl`'s `jars` field is raw evidence
  from `~[...]` stack-frame suffixes, and 1.20+ reports no longer separate mods
  from libraries with a `-- Mod List --` section, so both arrive through one
  channel. Two frozensets (`LOADER_ARTIFACTS`, `RUNTIME_LIBS`) are the entire
  input, plus `classify_jar` and `partition_jars` (a real partition: nothing
  lost, nothing double-counted). `tools/audit_modrinth_mapping.py` now imports
  this instead of keeping a private copy. 33 tests.

- **`tools/rederive_index.py`**: offline repair of `corpus/index.jsonl`
  (`--dedupe`, `--mod-ids`, `--dry-run`). No API calls — the crash text for every
  row is already under `corpus/github/`. Idempotent; preserves field order;
  refuses to clear a non-empty field.

### Changed
- **The "write more rules" plan was measured and stopped** (ROADMAP 1E.3,
  risk R4). The premise of 1E.3 was that the bottleneck is the cost of writing a
  rule. The tail says otherwise:

  | | |
  |---|---|
  | undiagnosed reports | 117 / 454 |
  | distinct signatures | 107 |
  | clusters of size 1 | 100 (85% of the undiagnosed set) |
  | reports per rule, one rule per cluster | **1.09** |
  | top-10 share of the undiagnosed set | **17%** |

  R4 fixed the stopping rule in advance: top-10 < 30% means the tail is
  exhausted and the answer is structured output for the user. It fires at 17%.
  So the deliverable is a candidate *pack* with the yield attached, one admitted
  draft, and an explicit statement that the remaining 116 reports are not worth
  a rule each.

  Measured effect of that draft: undiagnosed 117 → 112, diagnosis rate
  74.2% → **75.3%** (run with `MCD_RULES_PATH=corpus/rule-drafts`, not
  extrapolated). That +1.1pp is five easy reports counted deliberately — anyone
  quoting the rate should say so, which is why the draft says it in its own
  header.

- **Blind-set diagnosis rate moved 65% → 68% (141/218 → 148/218) because of
  the new attribution signal, not because rules changed.** Seven more blind
  reports now reach a mod id, and rules that gate on `has_suspect` therefore
  fire on them. The scored blame-error rate did **not** move (still 1/7,
  `[3%, 51%]`) — none of the newly-attributed reports is in the scored set.
  `corpus/BLIND_EVAL.md` is regenerated and now says explicitly which number
  moved and why, so a later reader cannot mistake "speaks on more reports" for
  "speaks more accurately".

- **The coverage taxonomy failed its own first measurement and was rewritten.**
  `world-data` matched the bare words `chunk ` / `anvil` / `corrupt` — which are
  *class names* (`LevelChunk`, `AnvilChunkLoader`) present in almost every stack
  trace — and claimed 140 of 454 reports. Tightened to failure phrases, it holds
  21, and those 21 are diagnosed **90%** of the time: the old 72% was an artifact
  of dilution, not a real coverage gap. Any predicate that fires on ordinary
  stack-frame vocabulary measures the vocabulary, not the failure.
- **New `mod-bug` bucket**: the deepest `Caused by:` was thrown inside mod code.
  153 reports (34%), 63% diagnosed — the largest block that `other` was hiding.
  It reads the throw site from the parsed report, not from the rule engine or
  the attribution ranking, so the coverage number stays independent of what it
  is measuring.
- **Fabric `FormattedException` counts as `mod-loading`.** It is the loader's
  wrapper for "your mod set did not resolve" and for entrypoint failures;
  without it 49 reports (10.8%) fell through to whatever text signal came next.
  `mod-loading` went 43 → 82 and the misfiled cases stopped polluting
  `world-data`.
- **Empty buckets are rendered, not omitted.** `oom` is measured at **0/454**
  (`OutOfMemoryError` and `java heap space` both zero across the whole corpus)
  and `plugin` at 0 (only hybrid mohist/arclight servers, no pure Bukkit). An
  omitted row reads as "covered or irrelevant"; a bare `0` reads as "covered".
  Each empty bucket now states that the *corpus* lacks the category, with the
  loader distribution beside it as evidence.
- **`corpus/index.jsonl` rows: 488 → 454.** `load_index()` was written to make
  harvesting incremental and then never called, so `harvest_repo` appended a
  second copy of every issue it re-scanned. 33 of the 34 duplicate pairs were
  byte-identical; the last differed only in `comments` (6 vs 7, two harvest
  passes). The guard now sits inside the writing loop, so a single run cannot
  duplicate either.

- **Word-boundary retry is now the default** in `tools/audit_modrinth_mapping.py`
  (ROADMAP 1D.2b). Modrinth search matches on word tokens, so a squashed id both
  mods share — `notenoughanimations` — retrieves **nothing at all**, while
  `not enough animations` returns `not-enough-animations` first try. After a
  miss the tool now re-asks with mechanical boundaries (lower→upper,
  letter↔digit) and **acceptance is unchanged**: a hit must still normalise to
  exactly the candidate. It can therefore only find correct matches; it cannot
  invent a name-mismatched one. Measured yield **45.8% → 50.8%** (6 recoveries,
  all CamelCase: `XaerosWorldMap`, `MekanismGenerators`, `CustomMachinery`,
  `AirHop`, `HostileNeuralNetworks`, `MekanismAdditions`). `--no-variant-retry`
  turns it off. Residual risk that string rules cannot remove: among homonyms
  (original / port / sequel) it may pick the wrong project.

- **ROADMAP 1D.2b closed, deliberately short of 1D.2.** After the word-boundary
  fix, the remaining 59 misses fall into exactly two buckets and neither is a
  tuning problem: all-lowercase compounds (`justzoom`, `rarcompat`,
  `notenoughanimations`) have **no mechanical split point** and need a
  dictionary/segmenter, while genuine aliases (`appliedenergistics2`→`ae2`,
  `TConstruct`→`tinkers-construct`) need a curated table whose cost grows
  linearly with the number of mods and never converges. Both are trade-offs
  rather than technical details, so the work stops here pending a decision
  instead of quietly adding a dependency.

- **ROADMAP 1D.2 re-scoped and demoted.** It was planned as "Modrinth metadata
  as the source of declared negative edges", on the assumption that those edges
  were plentiful. The 1D.0 measurement falsified the assumption, so 1D.2 is now
  redefined as *the positive dependency graph + version ranges* for Pack Doctor,
  plus a *confirmation* tier for the compatibility graph (co-occurrence proposes,
  declared edges confirm) — and it is no longer a stage-1 priority. `1D.3`
  (evidence tiering) moves up instead, because with sparse declared edges the
  only way to keep downstream consumers honest is to label how much each edge is
  worth.
- **`docs/RESEARCH.md` J1 rewritten and a new §3.6 added** recording the
  measurement, including the four things it changed: the "declared edges replace
  co-occurrence" hypothesis is dead (it is *confirmation*, not *discovery*); a
  45.8% match rate means half a modpack is invisible, so any metadata-driven
  check must report "I cannot identify these mods" rather than skipping them
  silently; `jars` is not a mod list; and `mod_ids` is a dead field (0/488).

### Fixed
- **Half the stack frames in the corpus were being discarded, and nothing
  noticed** (ROADMAP 1E.5). `_parse_frame` reduced a raw line to
  `pkg.Class.method(File.java:N)` with three narrow rules, each of which failed
  silently on real input. Measured over 57,282 frames in 454 reports:

  | defect | frames | reports |
  |---|---|---|
  | trailing `[jar]` trailer not stripped — only `~[jar]` was | 5,432 | 148 |
  | `TRANSFORMER/<layer>/` or JPMS `module/` prefix kept in `cls` | 16,286 | — |
  | `-` in a Fabric method name swallowed into `cls` | 79 | 43 |

  Failure mode was always the same: the regex did not match, the fallback
  `f.cls = head` stored the whole line, and method + line number vanished. No
  exception, no empty field, no test failure — the frames just stopped matching
  anything.

  Frames parsing into `cls` + `method` went **48,728 → 57,158** of 57,282.
  Downstream, all in the fixable direction:
  - coverage: `mod-bug` 153 → **91**, `other` 113 → **175**. Sixty-two reports
    had been counted as "the bug is in mod code" because their throw site was
    `TRANSFORMER/minecraft@1.21.1/net.minecraft…`, which does not start with
    `net.minecraft`, so `is_minecraft` was False for every vanilla frame.
  - diagnosis: reports with ≥1 finding **318 → 337** (+19), **zero** losing one.
  - blind set: diagnosed 148/218 → **155/218**, mod repos 105/143 → **112/143**,
    blame-error unchanged at 1/7.
  - attribution ablation: silent-without-hint 4/35 → **3/35**.

  The last one is not purely good news and is documented as such:
  `twilightforest#2543` now names `twilightforest` where the loader's list starts
  with `accessories` and the maintainer labelled the issue `other mod`
  (`corpus/ATTRIBUTION_ABLATION.md`, `corpus/BLIND_EVAL.md`).

  `tools/parser_snapshot.py` grew a `frames_sig` and a `frame_defects` field for
  this: the old snapshot counted frames, and the count was identical before and
  after the whole repair. `tests/test_frame_parse.py` (18 tests) pins each row of
  the table above.

- **`net.minecraftforge.*` frames were labelled vanilla.** `fq.startswith(
  "net.minecraft")` is also true for `net.minecraftforge`, so `is_minecraft` won
  and the `elif` that sets `is_forge` could never fire. Both flags mean
  "platform code", so no verdict changed — the labels were simply wrong, which
  is why nobody found out.

- **Attribution was silent on 57% of the reports that carry a `Suspected Mods:`
  line, once that line was removed.** Not random: 17 of the 20 silent reports
  were Fabric API crashes, whose only written trace of the owner is a
  **mixin-generated method name** —
  `RegistryLoader.wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall`.
  `triage()` never read method names, and those reports print no
  `from mod (x)` marker, no mod-owned frame and no matching jar. The owner was
  sitting in the frame the whole time. New signal `W_MIXIN_METHOD=6`, with
  three constraints that were measured rather than guessed:

  - **seed anchoring** — a bare `$([\w-]+)$` scan returns Mixin jargon, not mod
    ids: its most frequent "ids" across the corpus were `bridge` (32 reports),
    `new` (29), `static` (26). Anchoring on the seed segment (`cdi000`) yields
    114 reports / 69 ids, all of them real mod names.
  - **top-5 frames only** — the first version scanned 25 and its first three
    hits included frame #12 and #14. One of them was Not Enough Crashes, whose
    mixin is literally named
    `atTheEndOfSecondCatchBeforePrintingCrashReport`: it patches the crash
    handler, so it appears in every report it decorates. Perfect evidence that
    the report was processed, worthless evidence of cause.
  - **once per (mod, signal)** — summed per frame the signal reached 6×N and
    began outvoting the loader's own line (with-hint agreement fell 28/35 →
    25/35). Counting the pair once restored it.

  Effect: silent 20/35 → 4/35, independent agreement 7/15 → 23/31, with-hint
  agreement 28/35 → 32/35, and no report moved from correct to incorrect.
  `f.cls` is scanned alongside `f.method` because the frame parser glues
  hyphenated method names onto the class (see Added).

- **A `TRANSFORMER/<modid>@<version>/` signal was implemented, measured, and
  removed.** It read the transformed-class layer that Connector/NeoForge print
  on every frame. On the oracle sample it added exactly one answer and that
  answer was wrong (`twilightforest` for a report the loader attributed to
  `accessories`), while also outvoting that same report's hint. Deleted rather
  than tuned — it is easy to reach for, since `TRANSFORMER/minecraft@…` is on
  nearly every vanilla frame.

- **Attribution broke ties by the order the report was written in.** `scores`
  is a `defaultdict(float)`, and `sorted(scores.items(), key=lambda kv: -kv[1])`
  leaves equal scores in dict insertion order — i.e. the order mods appear in
  the stack trace and Mod List. Two reports of the same two-mod interaction,
  written in opposite order, could name different top suspects, which made
  "top-1 is the repo's mod" (the metric ROADMAP 1B.2 rests on) partly an
  artefact of prose ordering. Now sorted by `(-score, modid.lower())`:
  deterministic and report-order independent. No published number moved
  (blame errors stay 1/7) because no scored pair was tied, but the guarantee
  is now an assertion rather than a coincidence.

- **Catastrophic regex backtracking in the Mod List parser — 8.1x slowdown for
  the whole corpus.** `_parse_forge_modlist` matched each row with a six-group
  lazy regex. On a *mangled* row (a partial table row: four pipes instead of
  five, padded with alignment spaces) the engine had exponentially many ways to
  distribute the same whitespace between the lazy groups and the interleaved
  `\s*`, and only gave up after exhausting them. Measured cost per row:
  **2 ms at 121 chars, 321 ms at 242 chars, 1.3 s at 306 chars**. Two harvested
  reports (Mekanism#2697, Placebo#8291) contain ~350 such rows each and took
  **9.4 s** to parse a 276 KB file. A full 454-report pass spent ~95% of its
  wall clock in this one call.

  Replaced with `split("|")` plus explicit field checks (`_forge_row`), which
  accepts exactly what the regex accepted. Verified by snapshotting parser
  output for all 454 reports before and after: **byte-identical**, 11,583 mod
  rows either way. Corpus pass **250.8 s → 30.7 s**; the test suite also
  dropped from 4m42s to 1m13s. This is not a micro-optimisation — a user
  pasting a 276 KB crash report into the tool was waiting nine seconds.

- **The web-wheel guard only compared module names, so stale contents shipped
  silently.** `tests/test_web_bundle.py` caught a wheel with a missing or
  deleted module, but not one carrying last week's *code*: when the parser fix
  above landed, no file was renamed, every guard stayed green, and the
  committed wheel kept the 9-second parser. `web/wheel-manifest.json` now
  records a `source_digest` (sha256 over every shipped `.py`/`.yaml` under
  `mcd/`, path + bytes) and a test compares it against the current tree, so
  "run `tools/build_web.py` after any `mcd/` change" is enforced rather than
  documented. Verified both ways: appending a comment to one module turns it
  red, restoring it turns it green.

- **A false provenance warning was published, then disproved by rebuilding.**
  After 1D.4 repaired `corpus/index.jsonl` (488 → 454 rows, `mod_ids` filled),
  `corpus/COMPAT_EDGES.md` was edited to warn that `compat-edges.jsonl` had gone
  stale and could no longer be reproduced from the corpus. Rebuilding against the
  repaired index gives **byte-identical output** — 9,895 rows, tier distribution
  unchanged. The error was conflating two tools: `build_compat_edges.py` derives
  co-occurrence from `rep.mods` (the Mod List re-parsed from each report), while
  `audit_modrinth_mapping.py` draws candidates from `mixin_configs` + `jars` and
  reports `mod_ids_populated` only as a diagnostic. Both documents are corrected,
  and the prose warning is replaced by an executable assertion — a wrong comment
  cannot be caught by CI, a failing test can.

- **`mod_ids` was a dead field in all 488 index rows** (1D.4). `MODID_RE` looks
  for the Forge-1.4-era `from mod (<id>)` marker; that marker occurs **480 times
  in this corpus and is `unknown` every single time**, so the `!= "unknown"`
  filter emptied the field while the schema kept promising it. It now reads the
  `-- Mod List --` section through `mcd.parser.report` (which already handles
  both the Forge pipe table and the Fabric indented tree): **0 → 106 records,
  3,080 ids**, with 125 platform rows (`minecraft`, `forge`, `fabricloader`)
  filtered out. The harvester prefers the same source, so a re-harvest cannot
  regress it. 343 of 454 reports genuinely have no Mod List — that gap is now a
  stated fact rather than an empty column.

- **`is_runtime_lib` compared a normalised key against un-normalised literals.**
  `commons-lang3` normalises to `commonslang3`, which is not the string
  `"commons-lang3"`, so the exact check always missed and the family-root
  fallback looked at `commons` — also a miss. Every hyphenated library entry
  (`commons-io`, `jopt-simple`, `night-config`, `checker-qual`, …) had been
  silently classified as a mod. Fixed by pre-normalising both lookup sets.

- **`jar_stem` returned `""` for every stack-frame token.** `~[guava-32.1.2-jre.jar:?]`
  ends with `]`, so the version-prefix rule `base.rsplit("]", 1)[-1]` kept the
  part *after* the bracket — nothing. The corpus happens to store pre-stripped
  values, which is why no number moved, but any caller passing a raw token got
  `unknown` for a plainly identifiable library. Wrapper (`[...]`), prefix
  (`[1.20.1] name.jar`) and stack-frame tail (`:?`, `!`) are now three separate
  steps.

- `corpus/index.jsonl`'s `jars` field mixes mod jars with **classpath libraries**:
  `JAR_RE` matches stack-frame suffixes (`~[guava-32.1.2-jre.jar:?]`), and 1.20+
  crash reports no longer contain a `-- Mod List --` section, so mods and
  libraries arrive through the same channel. The audit therefore subtracts a
  documented runtime/loader namespace list (`guava`, `bus`, `mixin`, `fmlloader`,
  …) and prints **both** the corrected (45.8%) and uncorrected (36.7%) rates
  instead of quietly reporting the flattering one. Any downstream code that
  treats `jars` as "the installed mod set" is wrong — notably the future Pack
  Doctor.
- Web wheel rebuilt: adding `mcd/metadata/` tripped
  `tests/test_web_bundle.py`'s drift guard exactly as designed (4 tests went red
  with "web wheel is stale"), then went green after `tools/build_web.py`.

- **`docs/RESEARCH.md`** — literature review and design rationale, the evidence
  layer between `VISION.md` (direction) and `ROADMAP.md` (ordering). Covers five
  research lines (log parsing accuracy ceilings, LLM4Log's open challenges,
  crash deduplication/triage, LLM-as-judge validity, and the Minecraft
  ecosystem's machine-readable compatibility data), then derives goals, scope,
  hard constraints, technology choices, a phased plan and a risk/feasibility
  checklist. Every claim carries a provenance label (`[事实]`/`[推断]`,
  confidence, and `已核原文`/`二手转述`/`未验证` status) — second-hand figures are
  flagged and are **not** used as acceptance criteria.

  Three findings changed the plan rather than merely describing it:
  1. **Declared negative compatibility edges exist and are being ignored.**
     `fabric.mod.json` has `conflicts`/`breaks`, `mods.toml` has
     `type = "incompatible"`, and Modrinth's `dependency_type` includes
     `incompatible`. These are author declarations, an order of magnitude more
     reliable than the 9,721 `co_occurred` edges currently in
     `corpus/compat-edges.jsonl`. So Modrinth metadata moves from ROADMAP 2.1
     (a downstream consumer of edges) to **1D.2** (an upstream source).
  2. **The 9,721 weak edges share a `relation` field with the 82 `caused` ones**
     — no schema-level distinction, so downstream consumers will eventually
     misuse them. Recorded as a real data-model defect to fix in 1D.3 by adding
     `evidence_tier` (`declared`/`weak_supervision`/`cooccurrence`).
  3. **Publishing before the metrics carry intervals would be dishonest.** The
     7-scorable-sample "1/7 = 14% blame rate" has a Wilson 95% CI of roughly
     [2.6%, 39.9%]. So a new **1E** phase (interval estimation, top-1/top-2
     swap stability, metamorphic tests) is now a precondition for ROADMAP 1C.2
     (PyPI release), not an optional refinement.

  Also records a competitive finding: "in-browser rule-based diagnosis with
  honest disclaimers" is already occupied (mctoolbox.net), and mcdoctor.ai owns
  the cloud-LLM position — so being rule-based and honest is no longer
  differentiation.

- **GitHub Action** (ROADMAP 1C.1): `action.yml` (composite) +
  `mcd/action.py` (stdlib-only glue) diagnose the crash report posted to an
  issue and comment the result — root cause, suspect mod, fixes. Inputs:
  `issue` (defaults to the triggering issue), `path`, `url`, `comment`,
  `follow-links`, `fail-on`, `token`; outputs: `found`, `findings`,
  `worst_severity`, `suspect`, `suspect_confidence`, `commented`.
  Design points: the comment is **idempotent** (hidden marker, so re-runs on
  `edited` PATCH the existing comment instead of stacking duplicates),
  **chatter is ignored** (no report extracted -> `found=false`, no comment),
  and **a commenting failure never hides the diagnosis** (the Markdown is
  already on stdout and in the step summary; a token without `issues: write`
  warns instead of reddening the run). Text extraction reuses
  `mcd/extract.py`; diagnosis is the same `diagnose()` pipeline as the CLI.
  `fetch_log()` moved from `mcd/cli.py` into `mcd/extract.py` so the CLI
  `--url` path and the action share one implementation.
  `tests/test_action.py`: 20 tests, including an end-to-end run against a
  local fake GitHub API (event -> diagnosis -> comment created -> re-run
  updates the same comment -> `$GITHUB_OUTPUT` values), pinned to the real
  watchdog fixture (2 findings, top suspect `lithium` 97%).
  Dogfood workflow: `.github/workflows/diagnose-issue.yml` (issue
  opened/edited/labeled, label `no-diagnosis` opts out). Not yet run on a
  live issue — that is the remaining acceptance step.

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
- **The web UI is bilingual — Chinese by default, EN one click away.**
  Every user-facing string moved into an `I18N` dictionary in `web/app.js`
  (80 keys per language, identical key sets) and `web/index.html` carries the
  Chinese copy inline with `data-i18n` / `data-i18n-html` /
  `data-i18n-placeholder` hooks, so the first paint is Chinese before any
  script runs. The toggle is persisted in `localStorage` and writes
  `<html lang>`, `<title>` and the meta description.
  Two details that a naive i18n pass gets wrong and this one does not:
  **the switch relabels an already-rendered result** (labels, buttons and the
  environment block are re-rendered from the same `LAST` Incident document —
  no re-diagnosis, no data loss), and **an open warning is re-painted in the
  new language** (notices store the translation KEY plus its variables, never
  the rendered HTML). Focus is deliberately left where it was, so the toggle
  cannot steal it mid-run.
  Severity badges are localized too (致命/错误/警告/提示/信息), which is why
  the E2E accepts either script.
  English remains selectable and the CLI, the Action and the JSON/Markdown
  output are untouched — this is a UI-layer change only.
  `tools/verify_web_e2e.py` now runs **30 checks**: the original 19 plus
  Chinese-by-default (`<html lang>`, status line, environment summary, copy
  buttons), the EN round-trip (notice + status relabelled live, `aria-pressed`
  correct, focus not stolen), switching back to Chinese re-rendering the same
  diagnosis, no untranslated `data-i18n` node, and both packs carrying the
  same keys.
- **CJK typography.** The font stack now falls back through PingFang SC /
  Hiragino Sans GB / Microsoft YaHei / Noto Sans CJK SC, body line-height went
  1.55 → 1.62, and the uppercase + letter-spacing treatment on field labels,
  the "start here" label and the finding labels is scoped to
  `html[lang="en"]` — uppercase does nothing useful for Chinese and the extra
  tracking makes the glyphs look washed out.
- **Web UI reorganised around the verdict (P0 UX pass).** The page used to dump
  every card in discovery order, so the one thing a user came for — "what broke
  and what do I do" — was buried under the environment block. It now leads with
  a verdict card: root cause as the headline, suspect chip with confidence, the
  matching "why" reasons, the first two fixes, and an action row (copy fix /
  copy full diagnosis / open an issue). Environment details collapse into a
  `<details>`; findings follow the verdict as supporting evidence. Diagnosis
  output itself is unchanged — same `build_incident()`, so the browser and the
  CLI still emit byte-identical `schema_version 1.0` documents.
- **Three ways in, one of them new.** Besides paste-the-log there is now a file
  picker (`.txt/.log/.text`, 8 MB cap with a readable error) and drag-and-drop
  onto the input area; the window-level drag guards only fire for targets
  *outside* the drop zone, so dropping onto the textarea still works normally.
- **Staged boot instead of a blank wait.** Loading Pyodide, installing the wheel
  and warming the engine are shown as a three-step progress list with per-step
  state, and a failure replaces the list with the error, a retry button, a
  copy-error button and the `pip install` CLI fallback rather than a dead page.
  The list hides itself once the engine is ready.
- **Live status + focus hand-off.** `#status` is `role="status" aria-live="polite"`,
  so boot, lookup and error messages are announced; when a diagnosis lands,
  focus moves to the verdict heading (`tabindex="-1"`, `preventScroll` + a
  `scrollIntoView` that respects `prefers-reduced-motion`) so keyboard and
  screen-reader users start at the answer instead of the top of the page.
- **Copy actions actually report back.** The copy buttons use
  `navigator.clipboard` with an `execCommand` fallback and announce the result
  through an `.sr-only` live region, so "did that work?" is answered in every
  modality.
- **Accessibility and touch fixes.** The textarea has a real `<label for="log">`
  (it was placeholder-only), `:focus-visible` draws a 2 px ring on every
  control, buttons are ≥44 px tall, evidence lines got `overflow-wrap:anywhere`
  so long stack frames stop overflowing narrow screens, and a
  `@media (max-width:520px)` block tightens the header/verdict/action layout.
  Motion-dependent bits sit behind `prefers-reduced-motion: no-preference`.
- **Input guardrails that guide instead of failing.** Empty input, a bare
  paste link, and prose that is not a log are now distinguished: the first two
  block with an explanation of what to paste, the third only warns and still
  runs (a mangled paste should not be silently dropped). While a diagnosis is
  running, every input is disabled.
- **Favicon.** An inline SVG data URI replaces the missing `/favicon.ico`
  request that made every page load log a 404.
- `tools/verify_web_e2e.py` grew from 7 to **19 acceptance checks** — verdict
  card ordering, verdict headline text, collapsed environment, ≥2 copy actions,
  focus landing on the verdict, live-region politeness, `<label for>`, file
  input accept list, progress hidden when ready, busy-state disabling, link
  rejection (0 cards rendered) and prose-warn-not-block.

- **Three copy-pasted paste-host loops became one table** (`mcd/extract.py`).
  mclo.gs / gist / pastebin each had their own near-identical 12-line loop
  (seen-check, fetch, looks-like-a-report, append, throttle). They are now one
  `_PASTE_HOSTS` tuple plus `_follow_links()`; a fourth host is a row, not
  another block. Source labels (`mclo.gs:<id>`) are unchanged, so the harvester
  and the Action see exactly what they saw before.
- **One HTTP path** (`_http_get`) and **one encoding ladder**
  (`read_report_text`) in `mcd/extract.py` / `mcd/parser/report.py`.
  `_fetch()` (cached, harvester) and `fetch_log()` (uncached, CLI/Action) now
  share the request/read/decode/timeout code; `parse_file()` and
  `action.source_from_path()` share the four-encoding ladder.
- **`_fmt_platform()`** in `mcd/report/render.py`: the `loader version (via
  launcher)` string was hand-built in all three renderers with three different
  separators. They now pass a format template, and a report with no loader line
  no longer prints `None` where a platform name belongs.
- **`_exit()` / `_worst()`** in `mcd/cli.py`: `--exit-code` was implemented
  twice (once over a findings list, once by tracking a running maximum in the
  directory loop). One `_worst()` + one `_exit()` now serve all three input
  paths.
- **`VERSION` is `__version__`**: the version string lived in `mcd/cli.py`,
  `mcd/__init__.py` and `pyproject.toml`, so a release could ship three
  different answers. `cli.VERSION` is now re-exported from the package.
- **`tests/test_web_bundle.py`** (4 tests) guards the `web/` wheel: it must
  contain every module in `mcd/`, no module deleted from `mcd/`, and every rule
  pack. Verified in both directions — the suite fails loudly when the wheel is
  missing or stale, with "run python tools/build_web.py" as the message.

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

### Removed
- **Build output that had leaked into the working tree**: `build/lib/mcd/**`
  (a second, stale copy of all 15 modules — invisible to imports, very visible
  to `grep` and to anyone reading the tree), `mc_crash_doctor.egg-info/`, and
  every `__pycache__/`. All are gitignored and regenerated by `python -m
  build`; they were there because a build had run in the repo root.
- **`docs/demo-oom.txt` / `docs/demo-watchdog.txt`**: captured CLI transcripts
  from an older run, referenced by nothing, and already wrong (both open with a
  `RuntimeWarning` the CLI no longer emits). The same output is one command
  away: `mc-crash-doctor tests/fixtures/ground-truth/<report>`.
- **Dead code with zero references.** pyflakes was non-zero only after the
  cleanup below; vulture at 80% confidence is now empty. Deleted after grepping
  the whole tree for each name: `extract.NEOFORGE_RE`,
  `Extracted.n_stackframes` (written, never read), `report.LOC_RE`,
  `report.MODLAUNCHER_RE`, `report._unit_to_bytes`, `cli._fetch_url()` (a
  one-line pass-through to `fetch_log`), `MemoryInfo.is_complete`,
  `MemoryInfo.utilisation`, `CrashReport.find_section`, and
  `CrashReport.to_dict`/`to_json`.
  `to_dict`/`to_json` were a **second serialisation path that nothing called**
  — precisely the kind of duplicate that drifts from `build_incident()`, so
  removing it also removes a future inconsistency.
  `platform._best()` lost its `order` parameter and the `_ORDER_LOADER` /
  `_ORDER_LAUNCHER` lists that only fed it: both were leftovers from the
  ranking approach the function's own docstring explains was abandoned.
  Unused imports (`glob`, `os`, `sys`, `StackFrame`, `Counter`, `re`,
  `shutil`) and four f-strings without placeholders went with them.

### Fixed
- **The browser was running older code than the CLI.** `web/` ships a prebuilt
  wheel (that is what Pyodide installs), and it had been built before
  `mcd/action.py` existed, so the committed artifact no longer matched the
  source — and every test still passed, because nothing looked at the bundle.
  Rebuilt via `tools/build_web.py` and pinned by `tests/test_web_bundle.py`.
- **The Action decoded non-UTF-8 reports differently from the CLI.**
  `action.source_from_path()` tried utf-8 then cp1252 with
  `errors="replace"`, while `parse_file()` walked four encodings strictly. A
  cp1252 report therefore reached the rules with U+FFFD characters sprinkled
  through it — enough to stop a regex from matching and produce a confident
  "no rule matched" on a report the CLI diagnoses correctly. Both paths now
  share `read_report_text()`.
- **Deprecated licence metadata would eventually break the build.**
  `license = { text = "MIT" }` plus the `License :: OSI Approved :: MIT`
  classifier are removed in the PEP 639 world; setuptools already warned that
  builds stop working after 2027-02-18. Now `license = "MIT"` +
  `license-files`, with `setuptools>=77` as the build floor that understands it.
  `python -m build` is warning-free again.

- **`hidden` was not hiding anything.** `#progress` sets `display:flex` and
  every `<button>` sets `display:inline-flex`, and an author `display` rule
  beats the UA's `[hidden] { display:none }`. So the three boot-progress chips
  stayed on screen after the engine was ready, and the "Clear" button was
  rendered even with an empty box — a visible control that did nothing.
  Fixed with an explicit `[hidden] { display: none !important; }`.
  The previous E2E missed it because it asserted the **property**
  (`el.hidden`) instead of the computed style; the screenshot pass caught it,
  and the E2E now checks `getComputedStyle(...).display` for the progress
  list, the empty notice and the Clear button.
- **Finding titles lost their first letter in the web UI.** The severity badge
  and the title were concatenated in the `<h3>` without a space
  (`<span class="sev">FATAL</span>Server hung`), so any consumer that strips
  the leading badge token — as the E2E regex did — read `erver hung for
  120.00s`. One space added in the template.
- **mclo.gs share links were never resolved.** `MCLOGS_RE` required two path
  segments (`mclo.gs/<word>/<id>`), so the form the README advertises —
  `mc-crash-doctor --url https://mclo.gs/6cWndzQ` — did not match and the
  fetcher downloaded the HTML page instead of the log (the harvester's
  issue-body link following missed those links for the same reason).
  The regex now accepts the one-segment share link, the older
  `mclo.gs/<name>/<id>` shape and the raw API form
  (`api.mclo.gs/1/raw/<id>`), via a new `mclogs_id()` helper; `fetch_log()`
  also tolerates a scheme-less `mclo.gs/<id>` paste. Pinned by
  `test_fetch_log_resolves_every_mclogs_link_shape` (4 link shapes) and
  `test_issue_body_link_is_followed`.
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
