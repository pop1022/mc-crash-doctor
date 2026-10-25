#!/usr/bin/env python
"""Coverage report: which failure modes we diagnose, and which we do not (1D.4).

WHY THIS EXISTS
---------------
`docs/RESEARCH.md` J2 says the honest thing to ship is not "more rules" but a
**measured** statement of where the rules stop. Until now the repository could
say "diagnosis rate is 65% on the blind set" but could not answer the only
question that decides the next unit of work:

    which failure mode is undiagnosed, and how big is it?

This tool answers that. It walks the harvested corpus, runs the real rule engine
(which includes attribution, because `has_suspect`-gated rules depend on it),
and cross-tabulates **failure mode** against **whether anything fired**.

DESIGN NOTE -- buckets are an INPUT property, not an output
-----------------------------------------------------------
A bucket describes what the report *shows* (exception class, description text,
loader, deepest throw site), never which rule matched. Bucketing by matched rule
would be circular: "uncovered" categories would be undefined by construction,
and the report could never tell you what to write next. So classification reads
only the parsed report and the raw text.

Two amendments after the first full run, both driven by measurement:

  * `_world_data` used to match bare `chunk ` / `anvil` / `corrupt`, which are
    class-name vocabulary (`LevelChunk`, `AnvilChunkLoader`) rather than failure
    descriptions. It claimed 140 of 454 reports; the real figure is under 20.
  * a `mod-bug` bucket now captures "the deepest `Caused by:` was thrown inside
    mod code" -- 201 of 454 reports (44%), which is the dominant reality of
    Minecraft crashes and was previously hidden inside `other`.

BUCKET ORDER MATTERS
--------------------
The first matching bucket wins, so the order below is the contract: an
OutOfMemoryError inside a mod-loading phase counts as `oom`, because that is
the failure a user needs fixed. `mod-bug` is the least specific claim, so it
sits last before the catch-all. Change the order and the numbers change; the
order is therefore documented here and pinned by `tests/test_coverage_buckets.py`.

    python tools/coverage_report.py            # ~4 min for 454 fragments
    python tools/coverage_report.py --limit 40 # quick look

Writes corpus/COVERAGE.md + corpus/coverage.json (committed: counts and
exception signatures only, no report text, no player data).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcd.parser.report import parse_file          # noqa: E402
from mcd.rules.engine import RuleSet, run_rules   # noqa: E402

GITHUB = os.path.join(ROOT, "corpus", "github")
INDEX = os.path.join(ROOT, "corpus", "index.jsonl")
OUT_MD = os.path.join(ROOT, "corpus", "COVERAGE.md")
OUT_JSON = os.path.join(ROOT, "corpus", "coverage.json")


# --------------------------------------------------------------------------
# failure modes
# --------------------------------------------------------------------------
# PREDICATES MUST KEY ON WHAT THE REPORT SAYS WENT WRONG, NOT ON VOCABULARY.
#
# The first version of `_world_data` matched the bare words `chunk `, `anvil`
# and `corrupt`. Measured on the 454-report corpus, `anvil` appears in 114
# reports and `chunk ` in 138 -- almost all of them as *class names*
# (`AnvilChunkLoader`, `LevelChunk`), which any stack frame contains regardless
# of what failed. The bucket reported 140 "world data" failures where the real
# number is under 20, and it swallowed reports whose own exception said
# `ExceptionInInitializerError` or `launching the server!`.
#
# A predicate that fires on ordinary stack-frame vocabulary measures the
# vocabulary, not the failure. Every signal below is therefore a phrase that
# only appears when the report is *describing* that failure.
def _kinds(rep) -> list[str]:
    return [e.kind or "" for e in rep.exceptions]


def _has_kind(rep, *needles: str) -> bool:
    joint = " ".join(_kinds(rep))
    return any(n in joint for n in needles)


def _oom(text: str, rep) -> bool:
    return _has_kind(rep, "OutOfMemoryError", "GC overhead limit") or (
        "java heap space" in text or "direct buffer memory" in text
    )
def _watchdog(text: str, rep) -> bool:
    # Watchdog is a thread dump, not an exception: it only appears in prose.
    return "watchdog" in text or "server has not responded" in text


def _mixin(text: str, rep) -> bool:
    return _has_kind(rep, "Mixin", "InjectionError", "InvalidMixin") or (
        "mixin apply failed" in text or "mixin.injection" in text
    )


def _native(text: str, rep) -> bool:
    return "problematic frame" in text or _has_kind(
        rep, "SIGSEGV", "EXCEPTION_ACCESS_VIOLATION", "UnsatisfiedLinkError"
    )


#: `FormattedException` is Fabric's wrapper for "your mod set did not resolve"
#: and for entrypoint failures; without it those 49 reports (10.8% of the
#: corpus) fell through to whatever text signal came next. `ModResolutionException`
#: and `IncompatibleModSetException` are the newer Fabric wording.
_LOADING_KINDS = (
    "ModLoadingException", "MissingOrRemoved", "NoClassDefFoundError",
    "ClassNotFoundException", "UnsupportedClassVersionError",
    "DuplicateModsFound", "ModLoadingCrashException", "LoaderException",
    "FormattedException", "ModResolutionException", "IncompatibleModSetException",
)
_LOADING_PHRASES = (
    "mod loading has failed", "some of your mods",
    "incompatible mod set", "missing or unsupported",
    "a potential solution has been determined",
)


def _mod_loading(text: str, rep) -> bool:
    if _has_kind(rep, *_LOADING_KINDS):
        return True
    return any(p in text for p in _LOADING_PHRASES)


_WORLD_SIGNALS = (
    "ticking entity", "ticking block entity",
    "region file", "level.dat", "chunk storage", "chunk file",
    "corrupt chunk", "corrupted chunk", "chunk not found", "chunk loading",
    "error loading chunk", "failed to load chunk", "couldn't load chunk",
    "unable to load chunk",
)


def _world_data(text: str, rep) -> bool:
    return any(s in text for s in _WORLD_SIGNALS)


def _plugin(text: str, rep) -> bool:
    return (rep.system.loader or "") in ("bukkit", "spigot", "paper", "purpur")


# --------------------------------------------------------------------------
# whose code raised the root cause
# --------------------------------------------------------------------------
#: Packages owned by the JVM, Minecraft, the loaders and the libraries they
#: ship. A throw site inside one of these is NOT evidence of a mod bug. The
#: list is auditable in full, which is what makes "everything else is a mod"
#: a claim someone can check rather than an assumption.
#:
#: The Minecraft / Forge namespaces are listed here as well as being covered by
#: the parser's `is_minecraft` / `is_forge` flags. Relying on the flags alone
#: makes the predicate wrong for any caller that builds a frame itself (a test,
#: or a future non-crash-report input), and a wrong `mod-bug` verdict blames a
#: mod for a vanilla crash.
_PLATFORM_PREFIXES = (
    "java.", "javax.", "jdk.", "sun.", "com.sun.",
    "net.minecraft", "net.minecraftforge", "net.neoforged", "cpw.mods",
    "org.spongepowered.",          # mixin engine
    "net.fabricmc.loader", "org.quiltmc",
    "com.mojang.",                 # brigadier, datafixerupper, authlib
    "org.apache.", "com.google.", "io.netty.",
    "it.unimi.", "org.lwjgl.", "oshi.",
)


def _throw_site(rep):
    """Where the ROOT cause was raised: top frame of the deepest `Caused by:`.

    A crash report lists the chain top-level first, so `exceptions[-1]` is the
    deepest cause and its `frames[0]` is where that cause was thrown. Taking the
    deepest block -- not the first one, and not the parser's suspect ranking --
    keeps this a property of the report rather than a restatement of the
    attribution engine, which would make the coverage number circular.
    """
    if not rep.exceptions:
        return None
    frames = rep.exceptions[-1].frames
    return frames[0] if frames else None


def _is_platform_frame(frame) -> bool:
    cls = (frame.cls or "").strip()
    if not cls:
        return True                    # unparseable -> do not claim a mod
    if frame.is_minecraft or frame.is_forge:
        return True
    return cls.startswith(_PLATFORM_PREFIXES)


def _mod_bug(_text: str, rep) -> bool:
    site = _throw_site(rep)
    return site is not None and not _is_platform_frame(site)


def _other(_text: str, _rep) -> bool:
    return True


#: Ordered (name, predicate, human label). FIRST MATCH WINS -- see module docstring.
#:
#: Order rationale: named failure signatures first (oom, watchdog, mixin, native,
#: loader), then the server-platform slice, then content corruption, then --
#: last before the catch-all, because it is the least specific claim -- "the
#: deepest cause was thrown inside mod code".
BUCKETS: tuple[tuple[str, Callable[[str, Any], bool], str], ...] = (
    ("oom", _oom, "内存耗尽 (OutOfMemoryError / heap space)"),
    ("watchdog", _watchdog, "看门狗强杀 / 主线程卡死"),
    ("mixin", _mixin, "Mixin 注入失败"),
    ("native", _native, "原生崩溃（JVM 层 / 显卡驱动）"),
    ("mod-loading", _mod_loading, "模组加载 / 依赖 / 类缺失"),
    ("plugin", _plugin, "服务端插件（Bukkit 系）"),
    ("world-data", _world_data, "世界数据 / 区块 / 实体 tick"),
    ("mod-bug", _mod_bug, "根因抛在模组自身代码里"),
    ("other", _other, "其他 / 未分类"),
)

BUCKET_NAMES = tuple(b[0] for b in BUCKETS)

#: Buckets that can legitimately be empty for a given corpus. The report says so
#: explicitly instead of omitting the row: an absent row reads as "covered or
#: irrelevant", while a measured zero reads as "not in this corpus".
BUCKET_ABSENCE = {
    "oom": "语料里没有任何 OOM 报告（`OutOfMemoryError` / `java heap space` 命中 0 份）",
    "plugin": "语料里没有纯 Bukkit 系服务端报告（只有 mohist / arclight 这类混合端）",
}


def classify(text: str, rep) -> str:
    """First matching bucket wins; `other` is the catch-all and must stay last."""
    low = text.lower()
    for name, predicate, _label in BUCKETS:
        if predicate(low, rep):
            return name
    return "other"


# --------------------------------------------------------------------------
# corpus walk
# --------------------------------------------------------------------------
def load_verdicts() -> dict[tuple[str, str], str | None]:
    """(repo_short, issue) -> maintainer verdict, for the honesty check below."""
    out: dict[tuple[str, str], str | None] = {}
    if not os.path.exists(INDEX):
        return out
    with open(INDEX, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            short = rec["repo"].split("/")[-1]
            out[(short, str(rec["number"]))] = rec.get("verdict")
    return out


def source_key(path: str) -> tuple[str, str]:
    rel = os.path.relpath(path, GITHUB).replace(os.sep, "/")
    repo_dir, num = rel.split("/", 1)
    issue = num[:-10] if num.endswith(".crash.txt") else num
    return repo_dir.split("__")[-1], issue


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="only scan N files (dev)")
    ap.add_argument("--out-md", default=OUT_MD)
    ap.add_argument("--out-json", default=OUT_JSON)
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(GITHUB, "**", "*.crash.txt"),
                             recursive=True))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("no harvested corpus -- run tools/harvest_corpus.py first",
              file=sys.stderr)
        return 1

    verdicts = load_verdicts()
    ruleset = RuleSet.load()

    per_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"n": 0, "diagnosed": 0, "severe": 0, "verdict_known": 0}
    )
    uncovered_sigs: Counter[tuple[str, str]] = Counter()
    uncovered_bucket: dict[tuple[str, str], str] = {}
    uncovered_verdicts: Counter[str] = Counter()
    loader_counts: Counter[str] = Counter()
    parse_errors: list[str] = []
    parse_error_examples: list[str] = []

    started = time.time()
    for i, path in enumerate(files, 1):
        try:
            rep = parse_file(path)
        except Exception as exc:  # noqa: BLE001 - a bad file must not stop the scan
            parse_errors.append(f"{os.path.basename(path)}: {type(exc).__name__}")
            if len(parse_error_examples) < 5:
                parse_error_examples.append(f"{os.path.relpath(path, GITHUB)}: {exc}")
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            text = ""
        bucket = classify(text, rep)
        loader_counts[rep.system.loader or "(none)"] += 1
        try:
            findings = run_rules(rep, ruleset)
        except Exception:  # noqa: BLE001 - rules must never break the scan
            findings = []

        row = per_bucket[bucket]
        row["n"] += 1
        repo, issue = source_key(path)
        verdict = verdicts.get((repo, issue))
        if verdict:
            row["verdict_known"] += 1

        if findings:
            row["diagnosed"] += 1
            if any(int(getattr(f.severity, "value", f.severity)) >= 3
                   for f in findings):
                row["severe"] += 1
        else:
            sig = "no exception block"
            if rep.exceptions:
                sig = rep.exceptions[0].signature or "no exception block"
            uncovered_sigs[sig] += 1
            uncovered_bucket[sig] = bucket
            uncovered_verdicts[verdict or "(none)"] += 1

        if i % 50 == 0:
            print(f"  ... {i}/{len(files)} ({time.time() - started:.0f}s)",
                  file=sys.stderr)

    total = sum(b["n"] for b in per_bucket.values())
    diagnosed = sum(b["diagnosed"] for b in per_bucket.values())

    result: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files_scanned": len(files),
        "parse_errors": len(parse_errors),
        "parse_error_examples": parse_error_examples,
        "totals": {
            "n": total,
            "diagnosed": diagnosed,
            "rate": round(diagnosed / total, 4) if total else 0.0,
            "uncovered": total - diagnosed,
        },
        "buckets": {
            name: dict(per_bucket[name])
            for name, _p, _l in BUCKETS
            if per_bucket.get(name)
        },
        "bucket_order": list(BUCKET_NAMES),
        "loaders": dict(loader_counts.most_common()),
        "uncovered_signatures": [
            {"signature": sig, "count": n, "bucket": uncovered_bucket.get(sig, "")}
            for sig, n in uncovered_sigs.most_common(30)
        ],
        "uncovered_verdicts": dict(uncovered_verdicts),
        "elapsed_seconds": round(time.time() - started, 1),
    }

    with open(args.out_json, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    with open(args.out_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_md(result))

    print(f"scanned {total} fragments in {result['elapsed_seconds']}s -> "
          f"diagnosed {diagnosed} ({result['totals']['rate']:.1%})",
          file=sys.stderr)
    return 0


def render_md(result: dict[str, Any]) -> str:
    t = result["totals"]

    # Section numbers are assigned by position, not typed in. A literal "六、方法"
    # leaves a visible gap when the parse-error section is empty (which is the
    # normal case), and that gap reads as a missing chapter rather than a clean run.
    _cn = "一二三四五六七八九十"
    _n = 0

    def sec(title: str) -> str:
        nonlocal _n
        _n += 1
        return f"## {_cn[_n - 1]}、{title}"

    lines = [
        "# COVERAGE — 按失败模式的诊断覆盖率",
        "",
        "> 由 `tools/coverage_report.py` 生成，**不要手改**。",
        "> 回答的问题是：「下一条规则该写什么」。",
        "> 分类只看报告的**输入属性**（异常类型、描述文本、加载器、最深一层抛出点），",
        "> 不看命中了哪条规则——否则「未覆盖的类别」会按定义不存在。",
        "",
        f"生成时间：{result['generated_at']}　·　"
        f"扫描 {result['files_scanned']} 份　·　"
        f"耗时 {result['elapsed_seconds']}s",
        "",
        sec("总体"),
        "",
        f"**诊断率 {t['rate']:.1%}**（{t['diagnosed']}/{t['n']}），"
        f"未覆盖 {t['uncovered']} 份，解析失败 {result['parse_errors']} 份。",
        "",
    ]

    # Answer the document's own question up front, from the numbers below.
    # `other` is ranked with everything else: excluding it would report the
    # second-largest gap as 14 when the catch-all actually holds 64, which reads
    # as "the gaps are small".
    gaps = []
    rates = []
    for name, _p, _l in BUCKETS:
        row = result["buckets"].get(name) or {"n": 0, "diagnosed": 0}
        if not row["n"]:
            continue
        gaps.append((name, row["n"] - row["diagnosed"], row["n"]))
        rates.append((name, row["diagnosed"] / row["n"], row["n"]))
    gaps.sort(key=lambda t: (-t[1], -t[2]))
    rates.sort(key=lambda t: (t[1], -t[2]))
    if gaps:
        head = "、".join(f"`{n}` {miss} 份" for n, miss, _n in gaps[:3])
        covered = sum(m for _n, m, _s in gaps[:3])
        lines += [
            f"未覆盖绝对数最大：{head}（合计 {covered}/{t['uncovered']}）。",
            "",
        ]
    if rates:
        worst = "、".join(f"`{n}` {r:.0%}（{n2} 份）" for n, r, n2 in rates[:2])
        lines += [f"诊断率最低：{worst}。**下一条规则应当从这两处来。**", ""]

    lines += [
        sec("按失败模式"),
        "",
        "| 失败模式 | 样本数 | 已诊断 | 诊断率 | 含致命/错误级 | 有维护者结论 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, _p, label in BUCKETS:
        # Emit every bucket, including empty ones. An omitted row reads as
        # "covered or irrelevant"; a measured 0 reads as "not in this corpus".
        row = result["buckets"].get(name) or {
            "n": 0, "diagnosed": 0, "severe": 0, "verdict_known": 0
        }
        if row["n"]:
            rate = f"{row['diagnosed'] / row['n']:.0%}"
        else:
            rate = "—"
        lines.append(
            f"| `{name}` {label} | {row['n']} | {row['diagnosed']} | "
            f"{rate} | {row['severe']} | {row['verdict_known']} |"
        )

    empty = [n for n, _p, _l in BUCKETS
             if not (result["buckets"].get(n) or {}).get("n")]
    if empty:
        lines += ["", "### 空桶：不是规则缺陷，是语料里没有这一类"]
        lines += [""]
        for name in empty:
            why = BUCKET_ABSENCE.get(name, "该类别在本语料中样本为 0")
            lines.append(f"- `{name}`：{why}")
        lines += [
            "",
            "> 空桶必须显式出现。若只写 0 行，读者会以为「已覆盖」；"
            "若直接省略，读者会以为「不存在」。两者都是错的。",
        ]

    loaders = result.get("loaders") or {}
    if loaders:
        lines += [
            "",
            "加载器分布（判断「空桶」是否有语料依据）："
            + "　".join(f"`{k}` {v}" for k, v in loaders.items()) + "。",
        ]

    lines += [
        "",
        "> 匹配顺序（先命中先归入，`other` 兜底）："
        + " → ".join(f"`{n}`" for n in result["bucket_order"]) + "。",
        "> 顺序即契约：同一个 OutOfMemoryError 若发生在模组加载阶段，归入 `oom`，",
        "> 因为用户要修的是内存。改动顺序会改变数字，故由测试钉死。",
        "> `mod-bug` 排在最后（`other` 之前），因为「根因抛在模组代码里」是最不具体的断言；",
        "> 它读的是最深一层 `Caused by:` 的首个栈帧，不读规则引擎与归因结果——否则覆盖率会循环论证。",
        "",
        sec("未覆盖报告的实际长相（Top 20）"),
        "",
        "这些是「解析成功但没有任何规则命中」的报告按异常签名聚类。",
        "**排在最上面的就是下一条规则的候选**。",
        "",
        "| 异常签名 | 数量 | 所属失败模式 |",
        "|---|---:|---|",
    ]
    sigs = result["uncovered_signatures"][:20]
    if sigs:
        for row in sigs:
            sig = row["signature"].replace("|", "\\|")
            lines.append(f"| `{sig}` | {row['count']} | `{row['bucket']}` |")
    else:
        lines.append("| （无未覆盖报告） | 0 | — |")

    lines += [
        "",
        sec("未覆盖报告是否本来就无解？"),
        "",
        "用维护者标签做交叉检查：如果这些报告的 issue 也没有结论，那缺口是",
        "**报告本身信息不足**，不该由规则去填。",
        "",
        "| 维护者结论 | 数量 |",
        "|---|---:|",
    ]
    for verdict, count in sorted(result["uncovered_verdicts"].items(),
                                 key=lambda kv: -kv[1]):
        lines.append(f"| `{verdict}` | {count} |")

    unknown_n = result["uncovered_verdicts"].get("(none)", 0)
    if t["uncovered"] and unknown_n:
        share = unknown_n / t["uncovered"]
        lines += [
            "",
            f"**这项检查对 {share:.0%} 的缺口没有结论**：{unknown_n}/{t['uncovered']} "
            "份未覆盖报告的 issue 本身没有任何维护者标签。所以不能读成"
            "「缺口本来就无解」——只能说对剩下的 "
            f"{t['uncovered'] - unknown_n} 份，维护者认为它们有明确原因，"
            "其中 `user_error_or_config` 与 `bug_in_this_mod` 是规则应该能命中的。",
        ]

    if result["parse_error_examples"]:
        lines += ["", sec("解析失败样例"), ""]
        for ex in result["parse_error_examples"]:
            lines.append(f"- `{ex}`")
        lines.append("")
        lines.append("> 解析失败与「解析成功但无规则命中」是两件事，分开计数：")
        lines.append("> 前者是抽取缺陷，后者是覆盖缺口。")

    lines += [
        "",
        sec("方法"),
        "",
        "- 桶分类**先命中先归入**，顺序见第二节；`other` 是兜底且必须最后。",
        "- 每份报告都跑真实规则引擎（含归因，因为 `has_suspect` 门控的规则依赖它），",
        "  不是「模拟命中」。",
        "- 解析失败单独计数，**不混进诊断率**——否则解析 bug 会伪装成覆盖缺口。",
        "- 只记录异常签名与计数，不含报告正文与玩家数据。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
