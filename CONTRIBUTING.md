# Contributing to mc-crash-doctor

The highest-value contribution is **a rule for a crash you actually hit**. The
rule set is YAML; no Python needed.

## Quick start

```bash
git clone https://github.com/pop1022/mc-crash-doctor
cd mc-crash-doctor
pip install -e ".[pretty]"
bash run_tests.sh          # all gates
```

Python 3.9+. The suite runs offline (corpus is vendored).

## Adding a rule

1. Pick the right pack under [`mcd/rules/builtin/`](mcd/rules/builtin/):
   `memory-performance.yaml` (OOM, hangs, mixins, ticking, rendering, disk),
   `mod-loading.yaml` (dependencies, versions, duplicates, startup), or
   `runtime-crashes.yaml` (runtime exceptions, loader-failure wordings,
   threading, catch-alls).
   A new pack is fine too — any `*.yaml` in that directory is auto-loaded.

2. Copy the shape from [the README](README.md#add-a-rule) or a neighbouring
   rule. Key points:
   - `id` is `category.specific-thing` (e.g. `oom.metaspace`), lowercase,
     dotted, unique across all packs.
   - `priority` orders evaluation (lower first); neighbours are a good guide.
   - Every regex is matched with `re.I | re.M`. Escape dots: `java\\.lang\\.`.
   - Capture groups feed the title/explanation via `{{cap:text:1}}`.
   - `fixes` must be **actionable**: name the file, the flag, the button.
     "Update your mods" alone is not a fix.
   - `suspects_from` picks attribution signals: `frame_mods`, `mixin`, `jar`.

3. Test against a real report:

   ```bash
   mc-crash-doctor my-crash.txt
   ```

4. **Pin it — give the rule provenance.** Rules without a fixture regress
   silently. Add a `provenance` block to the rule's YAML:

   ```yaml
     provenance:
       fixtures:
       - mekanism/8590          # harvested corpus pin: "<repo>/<issue>"
       - synthetic/my-case.txt  # or a committed fixture under tests/fixtures/synthetic/
       expect_suspects:          # optional: attribution the pin must produce
         "mekanism/8590": mekanism
     lifecycle_status: verified  # draft|experimental|verified|stable|deprecated|retired
   ```

   `tests/test_gaps.py` reads these pins from the YAML (no hardcoded list)
   and `tests/test_rule_metadata.py` enforces the contract: every rule has
   fixtures, and `verified` requires at least one **real** (non-synthetic)
   fixture. If your rule is proven only by a synthetic fixture, set
   `lifecycle_status: experimental` — it gets upgraded when a real report
   fires it (re-run `python tools/stamp_provenance.py` to refresh
   provenance from the corpora; it is idempotent).

   Negative assertions matter as much as positive ones: a rule that fires on
   the wrong report actively misleads users (see the `oom.save-time` note in
   `tests/fixtures/ground-truth/README.md`).

5. Run `bash run_tests.sh` — every gate must pass.

## Writing good rules

- **Match structure, not vibes.** Prefer exception classes, loader banners and
  System Details fields over free prose. Log wording changes between versions;
  `UnsupportedClassVersionError` does not.
- **Beware game content.** Bare words like `glowstone`, `fabric`, `create`
  appear as block/item/mod names inside unrelated logs. Anchor to package
  names (`net.glowstone`), banners (`git-Paper`), or file structure.
  `mcd/parser/platform.py`'s header comment documents the war stories.
- **State what the report shows.** The explanation should quote evidence
  (`{{heap_max_mib}}`, `{{mod_count}}`) so users can verify the diagnosis
  instead of trusting it.
- **One rule, one root cause.** If two fixes diverge, write two rules with
  different `when:` conditions.

## Corpus & tooling

```bash
python tools/verify_seed_repos.py            # seed list still resolves?
python tools/harvest_corpus.py --from-file tools/seed_repos.txt --max-issues 200
python tools/fetch_aternos_corpus.py         # refresh vendored MIT corpus
python tests/debug_platform.py --file <log>  # why did platform detection pick X?
```

Harvested raw text stays local (`corpus/github/` is gitignored) — those are
other people's bug reports. Only the redacted factual index
(`corpus/index.jsonl`) is committable, and anything committed must pass
`tests/test_redaction.py` semantics (home paths, player names, UUIDs, real
IPs out; mod version numbers in — they are attribution data).

A GitHub PAT (`GITHUB_PAT` env) lifts the harvester from 60 to 5000 req/h.
Never commit it.

## Parser changes

Platform/version detection changes must keep both gates green:

```
python tests/eval_parser.py --strict    # 201-file corpus: platform 100%, version >=98%
python tests/test_e2e.py                # ground truth 6/6, incl. MUST_NOT_FIRE
```

If a corpus file disagrees with your change, run
`python tests/debug_platform.py --file <path>` first — it shows every probe
that fired, its tier, rank and offset. Fix from evidence.

## Code style

- Standard library only in `mcd/`; PyYAML is the single hard dependency.
  `rich` is optional and must degrade gracefully (it does — plain renderer).
- `from __future__ import annotations` at the top of every module (3.9 floor).
- Dataclasses for structure, plain functions for logic. The model lives in
  `mcd/model.py` — extend it rather than passing dicts around.
- Comments explain *why*, especially the non-obvious regex anchors.

## Commit & PR

- One logical change per commit. The message should say what was wrong and
  how you know it is fixed (test names, accuracy numbers).
- PRs: describe the crash the rule addresses, link the report/issue if it is
  public, and show the `mc-crash-doctor` output before/after.
- CI runs the same gates on 3.9/3.11/3.13 plus a wheel-packaging check.

## Things we will not merge

- Rules scraped from LLM output without a real report behind them (they
  over-match; see "Beware game content").
- Anything that redistributes harvested issue text verbatim.
- "AI-powered" wrappers that shell out to an API for diagnosis — the point of
  this tool is deterministic, offline, explainable rules. An ML *ranking*
  layer on top of attribution scores is on the roadmap and welcome as an
  issue discussion.
