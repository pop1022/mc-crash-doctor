# Ground-truth fixtures

Six real crash reports from a live **266-mod Forge 1.20.1 / Java 21** server
(Windows, 9950X3D host), collected 2026-09-08.

These are the only samples with a hand-verified diagnosis, so they are the
strictest test in the repo. `tests/test_e2e.py` asserts:

| File | Description | Must fire | Must NOT fire |
|---|---|---|---|
| `crash-...18.01.19` | Exception ticking world | `oom.heap` | `oom.save-time` |
| `crash-...18.39.21` | Exception ticking world | `oom.heap` | `oom.save-time` |
| `crash-...18.45.43` | Exception in server tick loop | `oom.heap` | — |
| `crash-...18.47.46` | Ticking entity | `oom.heap`, `crash.ticking-entity` | `oom.save-time` |
| `crash-...22.31.14` | Watching Server | `hang.watchdog` | — |
| `crash-...22.42.32` | Watching Server | `hang.watchdog` | — |

## Why "must NOT fire" matters

The first four are **heap exhaustion during normal ticking**, not during a
world save: their stacks contain no `Saving worlds` line and no
chunk-serialisation path (the 18:01 report is entirely vanilla
`MinecraftServer` frames). An earlier draft of this project assumed they were
save-time OOM because that is a known pattern. The reports' own evidence said
otherwise, so the expectation was corrected and pinned here.

Misfiring `oom.save-time` is not a cosmetic bug: its fix text says "this is NOT
a memory leak, do not go hunting for one", which would send a user away from a
real leak. The negative assertions exist to keep that honest.

## Redaction

Processed through `tools/harvest_corpus.py:redact()` before being committed:
home paths → `<HOME>`, player names → `<PLAYER>`, UUIDs → `<UUID>`, instance
names → `<INSTANCE>`, network addresses → `<IP>`.

Deliberately **not** redacted: four-segment mod version numbers in the Mod List
(`|jei |15.20.0.129|`) and driver versions (`DriverVersion=15.6.5.199`). They
are shaped like IPv4 addresses but are attribution data — blanking them would
destroy exactly what the suspect-mod logic reads. `tests/test_redaction.py`
pins that distinction in both directions.

Mod names, mod ids, versions, the full 266-entry Mod List, JVM flags and
stack traces are unchanged, so diagnosis results are identical to the
unredacted originals.

## Provenance

Own server, own data. No third-party bug reports here — those live in
`corpus/github/`, which is gitignored and stays local.
