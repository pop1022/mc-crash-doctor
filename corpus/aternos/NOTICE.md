# Corpus provenance: corpus/aternos/

The `.log` fixtures and their `.json` expected-output files in this directory
are taken from the test suite of:

    aternosorg/codex-minecraft
    https://github.com/aternosorg/codex-minecraft
    Copyright (c) 2019-2025 Aternos GmbH — MIT License (see LICENSE here)

Retrieved 2026-09. They are the log-parsing fixtures that back mclo.gs
(https://mclo.gs), the largest public Minecraft log analyser.

## Why they are here

mc-crash-doctor uses them purely as a **regression corpus**: `tests/eval_parser.py`
parses every `.log` and checks the detected platform and Minecraft version
against the `.json` expectation. This is how the parser's 100% platform /
99.4% version accuracy is measured. They are *test data*, not runtime input.

## What is NOT here

- No analysis/diagnostic code from codex-minecraft is copied into this project.
  `mcd/parser/`, `mcd/rules/` and `mcd/triage/` are original work. The rule set
  deliberately covers failure modes codex-minecraft does not (memory/OOM,
  ServerHangWatchdog, mixin conflicts, mod attribution) — verified by reading
  its 69 Problem classes and 96 message strings.
- The multi-language message catalogues (`lang/*.json`) from upstream are not
  vendored; mc-crash-doctor has its own rule text.

## Regenerating / updating

The corpus is a point-in-time snapshot. To refresh against upstream:

    tools/fetch_aternos_corpus.py    # re-pulls the fixtures from the tarball

(If that script is absent, the corpus was seeded manually from the repository
tarball; keep this NOTICE and LICENSE alongside any re-extraction.)
