# mc-crash-doctor

**Diagnose Minecraft crash reports and logs: root cause, the mod at fault, and the fix.**

Paste a crash report from your 200-mod server and get back *"lithium, 97% confidence, stack frame #32"* instead of 1,500 lines of stack trace.

```
  platform : forge 47.4.16
  version  : Minecraft 1.20.1 | Java 21.0.12
  heap     : 6965/8192 MiB (85% used)   mods: 266
  root     : java.lang.Error: ServerHangWatchdog detected that a single
             server tick took 120.00 seconds

  SUSPECT MODS
  ● lithium    97%
      - stack frame #32: me.jellysquid.mods.lithium.common.reflection
        .ReflectionUtil.hasMethodOverride (line 13)

  [1] FATAL  Server hung for 120.00s and was killed by the watchdog
      One server tick took 120 seconds (limit is 60). The watchdog killed
      the JVM, so this report shows *where it was stuck*, not what threw.
      fix:
        1. Look at the top stack frames -- the first non-vanilla class is
           usually the culprit.
```

[中文说明](README.zh-CN.md) · [Why this exists](#why-this-exists) · [Install](#install) · [Usage](#usage) · [Add a rule](#add-a-rule)

---

## Why this exists

[mclo.gs](https://mclo.gs) is excellent and we use it too. But its engine ([aternosorg/codex-minecraft](https://github.com/aternosorg/codex-minecraft), MIT) has **zero rules for memory and performance failures**.

We read the whole thing to be sure:

| | measured |
|---|---|
| Problem classes | 69 |
| Message strings | 96 |
| Matching `memory\|heap\|oom\|watchdog\|hang\|gc\|xmx` | **0** |

(The 4 raw hits are false positives — `c**hang**e-motd-solution` contains "hang".) Its 201-file test corpus contains no memory-class crash at all. Its Forge rules cover load-time only (missing deps, duplicate mods, wrong version); `Ticking entity` gets "delete this entity", never *"which mod caused it"*.

Meanwhile those are exactly how modded servers die:

- **heap OOM** — "plays fine, crashes on `stop`" (it is not a leak; see [the rule](mcd/rules/builtin/memory-performance.yaml))
- **ServerHangWatchdog** — a tick took 120s, the JVM was killed, the report shows only where it hung
- **mixin conflicts** — two mods patching the same class
- **Metaspace OOM** — raising `-Xmx` will not help at all

mc-crash-doctor covers that category, and cross-indexes three independent provenance signals to name the mod.

## What makes attribution work

A crash report carries mod provenance in three places. Using all three is what turns "something crashed" into "mod X, 97%":

1. **Mixin ownership** — `pl:mixin:APP:create.mixins.json:Class from mod (create)`. A mixin crash is nearly always the mixin owner's fault. Strongest signal.
2. **Mod-owned stack frames** — first non-vanilla, non-loader class in the root-cause trace, resolved against the report's own Mod List (266 mods parse fine).
3. **Jar names** — `~[some-mod-1.2.3.jar%2312!/:1.2.3]`.

Scores are normalised to confidence. When two mods score within 20% of each other it says so, instead of bluffing:

```
  ● cupboard         50%
  ● l2screentracker  50%
  ! 'cupboard' and 'l2screentracker' score almost equally -- this looks like
    an interaction between the two rather than one broken mod. Remove one
    at a time to confirm.
```

## Install

```bash
pip install mc-crash-doctor          # CLI + engine
pip install "mc-crash-doctor[pretty]"  # + rich terminal output
```

Python 3.9+. Only hard dependency is PyYAML.

From source:

```bash
git clone https://github.com/YOURNAME/mc-crash-doctor
cd mc-crash-doctor
pip install -e ".[pretty]"
```

## Usage

```bash
# a crash report
mc-crash-doctor crash-2026-09-08_22.42.32-server.txt

# a whole server directory (auto-finds crash-reports/ then logs/)
mc-crash-doctor /path/to/server

# a mclo.gs link — fetched for you
mc-crash-doctor --url https://mclo.gs/6cWndzQ

# piped
cat latest.log | mc-crash-doctor --stdin

# paste into a GitHub issue / Discord
mc-crash-doctor report.txt --markdown

# machine-readable
mc-crash-doctor report.txt --json

# CI gate: exit 1 on any ERROR/FATAL
mc-crash-doctor --dir ./server --exit-code
```

As a library:

```python
from mcd import diagnose

rep, findings, triage = diagnose("crash-report.txt")

print(rep.system.loader, rep.system.xmx_mib)     # forge 2048
print(rep.root_cause.signature)                   # java.lang.OutOfMemoryError: ...
for s in triage.suspects:                         # ranked suspects
    print(s.modid, f"{s.confidence:.0%}", s.reasons[0])
for f in findings:
    print(f.severity.name, f.rule_id, f.title)
    for fix in f.fixes:
        print("  →", fix)
```

## Covered failure modes

25 rules across two packs. Rules are YAML — adding one needs no Python.

| Pack | Rules |
|---|---|
| [`memory-performance.yaml`](mcd/rules/builtin/memory-performance.yaml) | heap OOM · save-time OOM · Metaspace OOM · GC overhead · ServerHangWatchdog · tick timeout · Java class version · mixin apply failure · mixin target missing · ticking entity/block entity · rendering · OpenGL/driver · disk full · corrupt region |
| [`mod-loading.yaml`](mcd/rules/builtin/mod-loading.yaml) | missing dependency (Forge 1.13+/1.12 and older, Fabric/Quilt) · incompatible mod set · wrong MC version · duplicate mods · fatal load error · config parse error · missing coremod/library |

Platform detection covers Forge, NeoForge, Fabric, Quilt, Paper, Purpur, Folia, Spigot, CraftBukkit, Glowstone, Magma, Mohist, Arclight, CatServer, Velocity, Waterfall, BungeeCord, Bedrock, PocketMine, Geyser, and the major launchers — **100% on the 201-file regression corpus**.

## Accuracy

Measured by [`tests/eval_parser.py`](tests/eval_parser.py) against the upstream expectations, and [`tests/test_e2e.py`](tests/test_e2e.py) against real reports:

```
platform accuracy : 201/201 = 100.0%
version accuracy  : 176/177 =  99.4%
ground truth      : 6/6 matched
```

The ground-truth set is six real reports from a 266-mod Forge 1.20.1 server (four heap OOM, two watchdog kills). The test also asserts what must **not** fire — e.g. `oom.save-time` must not trigger on reports whose stacks show no chunk-serialisation path. Getting that wrong sends users hunting a memory leak that does not exist.

The one version miss is a corpus file containing two contradictory versions (a `1.8.8` startup line and a Magma banner reporting `MC: 1.12.2`, three hours apart). We take the software's own banner.

## Add a rule

Rules are declarative, so a new failure mode is a YAML PR:

```yaml
rules:
  - id: my.new-rule
    title: "Something went wrong with {{cap:text:1}}"
    severity: fatal          # fatal | error | warning | hint | info
    priority: 25             # lower runs first
    confidence: 0.85
    tags: [my-category]
    when:                    # all keys AND; entries within a key OR
      exception: ["java\\.lang\\.IllegalStateException"]
      text: ["my mod said ([\\w\\-]+) was broken"]
    explanation: >-
      What happened and why. {{mc_version}} and {{loader}} are available,
      as is {{cap:text:1}} from the capture group above.
    fixes:
      - "Do the first thing."
      - "Then the second."
    suspects_from: [frame_mods, mixin, jar]
```

Available placeholders: `{{description}} {{loader}} {{loader_version}} {{mc_version}} {{java_version}} {{java_major}} {{xms_mib}} {{xmx_mib}} {{heap_used_mib}} {{heap_max_mib}} {{mod_count}} {{os}} {{time}} {{root_exception}} {{root_message}}`, plus `{{cap:<key>:<group>}}` for regex captures.

`when` supports: `description exception exception_msg exception_any caused_by frame frame_top jar mixin text` (regex), `loader kind` (exact), `java_major max_heap_mib mod_count` (`{lt,le,gt,ge,eq}`), `has_mod not_has_mod` (glob).

Test your rule without installing anything:

```bash
MCD_RULES_PATH=./my-rules mc-crash-doctor report.txt
mc-crash-doctor --rules      # list everything loaded
```

## Corpus & evaluation

Two corpora back the tests:

- **`corpus/aternos/`** — 201 real logs + expected-analysis JSON from [aternosorg/codex-minecraft](https://github.com/aternosorg/codex-minecraft) (MIT). Attribution in [`corpus/aternos/NOTICE.md`](corpus/aternos/NOTICE.md). Re-seed with `python tools/fetch_aternos_corpus.py`.
- **`corpus/github/`** — real crash reports harvested from mod repositories' issue trackers by [`tools/harvest_corpus.py`](tools/harvest_corpus.py). It follows mclo.gs / gist / pastebin links, redacts player names, home paths, IPs and UUIDs, and records maintainer labels (`confirmed`, `Not <Mod>`, `Loader Issue`, `Support`) as weak supervision for root-cause verdicts.

Raw harvested text stays local (gitignored) — it is other people's bug reports. Only the factual index is committed.

```bash
python tools/harvest_corpus.py --repo mekanism/Mekanism --max-issues 500
python tests/eval_parser.py --strict    # platform/version accuracy gates
python tests/test_e2e.py                # end-to-end + ground truth
python tests/debug_platform.py --file <log>   # why did it detect X?
```

## Roadmap

- [ ] Web UI — paste and diagnose in the browser, no install
- [ ] GitHub Action — auto-diagnose crash reports posted to issues
- [ ] Mod graph from the Modrinth API (75k mods) — known-conflict and version-compat lookup
- [ ] Weak-supervised classifier trained on maintainer labels, to rank suspects when rules are inconclusive
- [ ] Client-side log tailing (watch `latest.log` live)

## Not covered yet

Honest scope: Bukkit/Spigot **plugin** failures get platform detection but few rules (that is mclo.gs's strength — use it there). Bedrock, PocketMine and proxy logs parse but have minimal diagnostics. If your case is not covered, the tool says so rather than guessing:

```
No rule matched this report. It parsed cleanly, but this failure mode is
not covered yet — please open an issue with the report attached.
```

## License

MIT — see [LICENSE](LICENSE). Third-party corpus attribution in [corpus/aternos/NOTICE.md](corpus/aternos/NOTICE.md).

Not affiliated with Mojang, Microsoft, Forge, NeoForge, Fabric or Aternos.
