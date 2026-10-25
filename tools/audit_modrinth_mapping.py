#!/usr/bin/env python
"""Audit how far Modrinth metadata can carry us (ROADMAP 1D.0).

WHY THIS EXISTS
---------------
`docs/RESEARCH.md` J1 claims the ecosystem already publishes machine-readable
NEGATIVE compatibility edges (fabric.mod.json `conflicts`/`breaks`,
mods.toml `type = "incompatible"`, Modrinth `dependency_type: incompatible`)
and that those beat our 9,721 `co_occurred` pairs. That claim is worthless
until measured: if mod identifiers in our corpus do not resolve to Modrinth
projects, and if authors rarely declare `incompatible`, then 1D.2 is not worth
building. This tool measures both before any product code is written.

THE IRON RULE (ROADMAP 1D.0)
----------------------------
Measure first, code second. Nothing here touches `mcd/`; the diagnosis engine
stays a pure function. If the match rate comes back below the gate in
ROADMAP 1D.0, the finding is "do not build 1D.2 yet", and that is a success
for this tool, not a failure.

WHAT IT MEASURES
----------------
M1  Distinct mod candidates in corpus/index.jsonl, split by origin
    (`mixin_configs`, `jars`) -- the two identifiers the harvester already
    extracts. `mod_ids` is declared in the index but is always empty, which
    this tool reports rather than silently tolerating.
M2  How many candidates resolve to a real Modrinth project. Resolution is
    deliberately CONSERVATIVE: exact slug, then exact normalised slug/title
    from search. No fuzzy acceptance -- a wrong match would poison every
    downstream compatibility claim, and a wrong edge is worse than no edge.
M3  Whether the `subject` of each causal edge in corpus/compat-edges.jsonl
    resolves (those are modids, e.g. `curios`, `fabric-registry-sync-v0`).
M4  For a bounded sample of resolved projects, how many versions declare at
    least one `dependency_type: incompatible` -- i.e. is the negative-edge
    signal actually there, or is it a fond hope?

POLITENESS
----------
Offline-first: every response is cached under data/modrinth-cache/ (gitignored),
so re-runs are free. Network calls are serialised with a >=300 ms gap, carry a
descriptive User-Agent (Modrinth requires contact info), honour 429 backoff,
and stop after --max-lookups. Nothing here downloads jars or bodies of text.

    python tools/audit_modrinth_mapping.py
    python tools/audit_modrinth_mapping.py --max-lookups 100 --probe-deps 10
    python tools/audit_modrinth_mapping.py --offline   # cache only, no network

Writes corpus/MODRINTH_MAPPING.md + corpus/MODRINTH_MAPPING.json (both
committed: they contain ids, slugs and counts only -- no third-party metadata).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:          # `python tools/x.py` puts tools/ first
    sys.path.insert(0, str(ROOT))

API = "https://api.modrinth.com/v2"
USER_AGENT = (
    "mc-crash-doctor/0.0.0-1D0-audit "
    "(+https://github.com/pop1022/mc-crash-doctor; compatibility-source audit)"
)
CACHE_DIR = Path("data/modrinth-cache")
INDEX = Path("corpus/index.jsonl")
EDGES = Path("corpus/compat-edges.jsonl")
OUT_MD = Path("corpus/MODRINTH_MAPPING.md")
OUT_JSON = Path("corpus/MODRINTH_MAPPING.json")

# Jar classification lives in `mcd.metadata.jars` (ROADMAP 1D.4), because it is
# not an audit concern: any consumer of the corpus `jars` field needs the same
# 库/模组/未知 distinction. Keeping a private copy here would let the two drift.
#
# `--no-exclude-libs` below reproduces the uncorrected denominator (mods and
# runtime libraries mixed), which is how the 36.7% figure in
# corpus/MODRINTH_MAPPING.md was obtained.
from mcd.metadata.jars import (            # noqa: E402
    LOADER_ARTIFACTS,
    RUNTIME_LIBS,
    is_runtime_lib,
    jar_stem,
    mixin_stem,
    norm_key,
)

# --------------------------------------------------------------------------
# HTTP with cache + politeness
# --------------------------------------------------------------------------
class Client:
    def __init__(self, *, offline: bool, max_lookups: int, gap: float) -> None:
        self.offline = offline
        self.max_lookups = max_lookups
        self.gap = gap
        self.lookups = 0
        self.cache_hits = 0
        self.errors: Counter[str] = Counter()
        self.exhausted = False
        self._last = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{digest}.json"

    def get(self, url: str) -> tuple[int, Any]:
        """Return (status, payload). Cached; 404 is a normal answer, not an error."""
        cache = self._cache_path(url)
        if cache.exists():
            self.cache_hits += 1
            blob = json.loads(cache.read_text(encoding="utf-8"))
            return blob["status"], blob["body"]
        if self.offline or self.exhausted:
            return 0, None
        if self.lookups >= self.max_lookups:
            self.exhausted = True
            return 0, None

        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.lookups += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        status, body = 0, None
        for attempt in range(3):
            try:
                self._last = time.monotonic()
                with urllib.request.urlopen(req, timeout=20) as resp:
                    status, body = resp.status, json.load(resp)
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status == 404:
                    body = None
                    break
                if status == 429:                     # rate limited: back off
                    delay = float(exc.headers.get("Retry-After") or 5)
                    self.errors["429"] += 1
                    time.sleep(min(delay, 30) * (attempt + 1))
                    continue
                self.errors[str(status)] += 1
                body = None
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.errors[type(exc).__name__] += 1
                time.sleep(2 * (attempt + 1))
        cache.write_text(
            json.dumps({"status": status, "body": body}), encoding="utf-8"
        )
        return status, body


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------
def slug_variants(candidate: str) -> list[str]:
    """Candidate spellings worth a direct slug lookup, cheapest-first.

    Modrinth slugs use hyphens, so the hyphen form goes first: `create_connected`
    is published as `create-connected`. Capped at two variants on purpose --
    every extra variant costs a request, and a 404-then-search fallback covers
    the rest. A long variant list would burn the request budget before the
    sample is measured, which would look like a low match rate.
    """
    low = candidate.lower().strip()
    out = [low.replace("_", "-"), low]
    seen, uniq = set(), []
    for v in out:
        v = v.strip("- ")
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq[:2]


def query_variants(candidate: str) -> list[str]:
    """Mechanical respellings that add word boundaries, for RETRIEVAL only.

    Why: Modrinth's search matches on word tokens. A squashed id like
    `notenoughanimations` retrieves NOTHING (not even unrelated hits), while
    `not enough animations` returns `not-enough-animations` on the first try.
    The acceptance rule is unchanged -- a variant is just a different question,
    and a hit still has to normalise to exactly the candidate -- so this can
    only find a correct match, never create a wrong one.

    Only boundaries that exist in the string itself are used (letter<->digit,
    lower->upper). We deliberately do NOT try to insert arbitrary spaces: with
    no dictionary, `notenoughanimations` has no mechanical split point, and
    guessing one would be fuzzy matching by another name.
    """
    out: list[str] = []
    digit_split = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", candidate)
    digit_split = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", digit_split)
    if digit_split != candidate:
        out.append(digit_split)
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", candidate)
    if camel_split != candidate and camel_split not in out:
        out.append(camel_split)
    return out


def search_exact(client: Client, query: str, key: str) -> dict[str, Any] | None:
    """One search request; return a hit only if it IS the candidate."""
    facets = json.dumps([["project_type:mod"]], separators=(",", ":"))
    status, body = client.get(
        f"{API}/search?query={urllib.parse.quote(query)}&limit=10"
        f"&facets={urllib.parse.quote(facets)}"
    )
    if status == 0 or status != 200 or not isinstance(body, dict):
        return None
    for hit in body.get("hits") or []:
        if norm_key(hit.get("slug") or "") == key or norm_key(hit.get("title") or "") == key:
            return hit
    return None


def resolve(client: Client, candidate: str, *, variant_retry: bool = False) -> dict[str, Any]:
    """Conservative resolution: exact slug, else exact slug/title from search.

    Returns {resolved, project_id, slug, title, via, reason}. A miss records a
    reason so the report can say WHY, instead of a single unhelpful percentage.
    """
    key = norm_key(candidate)
    if not key:
        return {"resolved": False, "reason": "empty"}
    if key in {norm_key(x) for x in LOADER_ARTIFACTS}:
        return {"resolved": False, "reason": "loader_artifact"}

    for variant in slug_variants(candidate):
        status, body = client.get(f"{API}/project/{urllib.parse.quote(variant)}")
        if status == 200 and isinstance(body, dict):
            return {
                "resolved": True,
                "project_id": body.get("id"),
                "slug": body.get("slug"),
                "title": body.get("title"),
                "versions": body.get("versions") or [],
                "via": "slug",
                "reason": "",
            }
        if status == 0:
            return {"resolved": False, "reason": "budget_exhausted"}

    hit = search_exact(client, candidate, key)
    if hit:
        return {
            "resolved": True,
            "project_id": hit.get("project_id"),
            "slug": hit.get("slug"),
            "title": hit.get("title"),
            "versions": hit.get("versions") or [],
            "via": "search",
            "reason": "",
        }

    if variant_retry:
        for query in query_variants(candidate):
            hit = search_exact(client, query, key)
            if hit:
                return {
                    "resolved": True,
                    "project_id": hit.get("project_id"),
                    "slug": hit.get("slug"),
                    "title": hit.get("title"),
                    "versions": hit.get("versions") or [],
                    "via": "variant",
                    "reason": "",
                }

    # Distinguish "the search returned rivals" from "the search returned nothing"
    status, body = client.get(
        f"{API}/search?query={urllib.parse.quote(candidate)}&limit=5"
    )
    if status == 0:
        return {"resolved": False, "reason": "budget_exhausted"}
    if status != 200 or not isinstance(body, dict):
        return {"resolved": False, "reason": f"search_http_{status}"}
    if body.get("hits"):
        return {"resolved": False, "reason": "name_collision_or_alias"}
    return {"resolved": False, "reason": "not_on_modrinth"}


# --------------------------------------------------------------------------
# corpus loading
# --------------------------------------------------------------------------
def load_reports(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        sys.exit(f"missing {path} -- run tools/harvest_corpus.py first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_candidates(reports: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """candidate -> origins ({mixin, jar}). Deduped across the whole corpus."""
    out: dict[str, set[str]] = defaultdict(set)
    for rep in reports:
        for cfg in rep.get("mixin_configs") or []:
            stem = mixin_stem(cfg)
            if stem:
                out[stem].add("mixin")
        for jar in rep.get("jars") or []:
            stem = jar_stem(jar)
            if stem:
                out[stem].add("jar")
    return dict(out)


def causal_subjects(path: Path) -> list[str]:
    if not path.exists():
        return []
    subs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        edge = json.loads(line)
        if edge.get("relation") in ("caused", "suspected") and edge.get("subject"):
            subs.add(edge["subject"])
    return sorted(subs)


# --------------------------------------------------------------------------
# dependency probe
# --------------------------------------------------------------------------
def probe_dependencies(
    client: Client, projects: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    """How many projects declare a negative edge, and on which versions?

    Samples up to `limit` resolved projects and inspects at most two versions
    each (first and last in the project's version list -- the ordering is not
    documented, so probing both ends avoids reading the wrong era). This is a
    LOWER BOUND on declaration density, and the report says so.
    """
    tally: Counter[str] = Counter()
    with_incompat = 0
    with_conflictish = 0
    probed = 0
    examples: list[dict[str, str]] = []
    for proj in projects[:limit]:
        vids = [v for v in (proj.get("versions") or []) if isinstance(v, str)]
        if not vids:
            continue
        picks = [vids[-1]] if len(vids) == 1 else [vids[-1], vids[0]]
        saw_incompat = False
        saw_dep = False
        for vid in picks:
            status, body = client.get(f"{API}/version/{urllib.parse.quote(vid)}")
            if status != 200 or not isinstance(body, dict):
                continue
            for dep in body.get("dependencies") or []:
                kind = (dep.get("dependency_type") or "unknown").lower()
                tally[kind] += 1
                saw_dep = True
                if kind == "incompatible":
                    saw_incompat = True
                    if len(examples) < 12:
                        examples.append(
                            {
                                "project": proj.get("slug") or "",
                                "version": body.get("version_number") or "",
                                "target_project": dep.get("project_id") or "",
                            }
                        )
        probed += 1
        if saw_dep:
            with_conflictish += 1
        if saw_incompat:
            with_incompat += 1
    return {
        "projects_probed": probed,
        "projects_with_any_dependency": with_conflictish,
        "projects_with_incompatible": with_incompat,
        "dependency_type_counts": dict(tally),
        "incompatible_examples": examples,
    }


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def render_md(result: dict[str, Any]) -> str:
    m = result["metrics"]
    gate = result["gate"]
    probe = result.get("dependency_probe") or {}
    lines = [
        "# MODRINTH_MAPPING — 1D.0 现状量化结果",
        "",
        "> 由 `tools/audit_modrinth_mapping.py` 生成，**不要手改**。",
        "> 目的：在写 1D.2（Modrinth 元数据抓取）之前，量清楚语料里的模组",
        "> 标识能不能映射到 Modrinth 项目，以及作者到底会不会声明",
        "> `incompatible`。判据见 `ROADMAP.md` 1D.0。",
        "",
        f"生成时间：{result['generated_at']}　·　"
        f"语料报告数：{m['reports']}　·　"
        f"网络请求：{result['http']['lookups']}（缓存命中 {result['http']['cache_hits']}）",
        "",
        "## 一、判定",
        "",
        f"**门槛（匹配率 ≥ 40%）：{'通过' if gate['passed'] else '未通过'}**",
        "",
        f"- 整体匹配率：**{m['match_rate']:.1%}**（{m['resolved']}/{m['candidates']}）",
        "  命中方式：" + "、".join(
            f"`{k}` {v}" for k, v in sorted(
                (m.get('resolved_via') or {}).items(), key=lambda kv: -kv[1])
        ) if m.get('resolved_via') else "  （无命中）",
        f"- 候选总数 {m['candidates_total']}，其中**运行时库 {m['runtime_lib_candidates']} 个**"
        f"（guava/bus/mixin/asm/netty 等）与**加载器产物 {m['loader_artifact_candidates']} 个**"
        f"（fmlloader/fabric-loader 等）——两者都不是模组，已排除出分母，"
        f"待测模组候选 {m['mod_candidates']} 个；本报告按 sha256(name) 序"
        f"确定性抽取 **{m['sample_size']}** 个实测"
        "（可复现、与名称和频次无关）。",
        "  按二项分布，该样本量在 95% 置信下误差约 ±9 个百分点——"
        "够用于「做/不做」的判定，不够用于精度声明。",
        "  **修正前口径**（不排除运行时库）实测为 36.7%（44/120）；"
        "两个数字都保留，读者可自行判断差别来自方法还是生态。"
        "用 `--no-exclude-libs` 可复现修正前口径。",
        (
            f"- ⚠ 因 `--max-lookups` 用尽，有 **{m['skipped']}** 个候选**从未查询**，"
            "已排除出分母（若计入会伪装成低匹配率）。"
            if m["skipped"] else
            "- 预算足以覆盖全部抽样候选，无截断。"
        ),
        f"- 结论：{gate['verdict']}",
        "",
        "## 二、候选标识来源分布",
        "",
        "| 来源 | 候选数 | 已解析 | 匹配率 |",
        "|---|---:|---:|---:|",
    ]
    for origin in ("both", "mixin", "jar"):
        row = m["by_origin"].get(origin)
        if not row:
            continue
        rate = row["resolved"] / row["total"] if row["total"] else 0.0
        lines.append(
            f"| {origin} | {row['total']} | {row['resolved']} | {rate:.1%} |"
        )
    lines += [
        "",
        f"`mod_ids` 字段：**{m['mod_ids_populated']}/{m['reports']} 份报告有值**"
        "（索引里声明了该字段但采集器从未填充——这是 1D.1 的输入缺口）。",
        "",
        "## 三、失败原因分布",
        "",
        "| 原因 | 数量 | 含义 |",
        "|---|---:|---|",
    ]
    meaning = {
        "not_on_modrinth": "名称在 Modrinth 上查不到（可能只在 CurseForge）",
        "name_collision_or_alias": "有搜索结果但无一精确匹配（别名/缩写/中文名）",
        "loader_artifact": "加载器/运行时产物，本就不是模组（已排除出分母）",
        "empty": "归一化后为空",
        "search_http_404": "搜索接口 404",
        "budget_exhausted": "达到 --max-lookups 上限，未查",
    }
    for reason, count in sorted(m["reasons"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{reason}` | {count} | {meaning.get(reason, '—')} |")
    if not m["reasons"]:
        lines.append("| — | 0 | 无失败 |")

    lines += [
        "",
        "## 四、被排除的非模组产物（Top 15）",
        "",
        "这些名字来自栈帧后缀（`~[guava-32.1.2-jre.jar:?]`），随 JVM/MC/加载器",
        "分发，用户不会从模组站安装。1.20+ 崩溃报告已无 `-- Mod List --` 段，",
        "模组与库走同一通道，故按运行时命名空间语义排除；加载器产物（fmlloader 等）同理。",
        "",
    ]
    if result.get("runtime_libs"):
        lines += ["| 名称 | 出现在报告数 |", "|---|---:|"]
        for row in result["runtime_libs"]:
            lines.append(f"| `{row['name']}` | {row['reports']} |")
    else:
        lines.append("（本次未排除任何运行时库）")

    lines += [
        "",
        "## 五、未被解析的模组候选（Top 25，按出现报告数排序）",
        "",
    ]
    unresolved = sorted(
        result["unresolved"], key=lambda r: (-r["reports"], r["name"])
    )[:25]
    if unresolved:
        lines += ["| 候选 | 来源 | 出现在报告数 | 原因 |", "|---|---|---:|---|"]
        for row in unresolved:
            origins = "+".join(sorted(row["origins"]))
            lines.append(
                f"| `{row['name']}` | {origins} | {row['reports']} | {row['reason']} |"
            )
    else:
        lines.append("（无）")

    lines += [
        "",
        "## 六、因果边的 subject 可解析性",
        "",
        f"`compat-edges.jsonl` 里 `caused`/`suspected` 的 subject 去重后 "
        f"**{m['causal_subjects']} 个**，实测 {m['causal_measured']} 个，"
        f"解析成功 **{m['causal_resolved']} 个**（{m['causal_rate']:.1%}）。",
        "",
        "> 背景：这些边全部是自环（`subject == object`），即「某模组被指为",
        "> 元凶」。语料里**没有任何一条 A↔B 的成对不兼容边**——这正是",
        "> 声明式边要填的空白。",
        "",
        "## 七、`incompatible` 声明密度（抽样）",
        "",
    ]
    if probe.get("projects_probed"):
        lines += [
            f"抽样 {probe['projects_probed']} 个项目、各探最多 2 个版本：",
            "",
            f"- 至少有一个 `incompatible` 依赖声明的项目："
            f"**{probe['projects_with_incompatible']}/{probe['projects_probed']}**"
            f"（{probe['projects_with_incompatible'] / probe['projects_probed']:.1%}）",
            f"- 至少有一个（任意类型）依赖声明的项目："
            f"{probe['projects_with_any_dependency']}/{probe['projects_probed']}",
            "",
            "依赖类型分布：",
            "",
            "| dependency_type | 数量 |",
            "|---|---:|",
        ]
        for kind, count in sorted(
            (probe.get("dependency_type_counts") or {}).items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| `{kind}` | {count} |")
        if probe.get("incompatible_examples"):
            lines += ["", "`incompatible` 样例（项目 → 目标项目 ID）：", ""]
            for ex in probe["incompatible_examples"][:8]:
                lines.append(
                    f"- `{ex['project']}` @ {ex['version']} → `{ex['target_project']}`"
                )
    else:
        lines.append("（未抽样：网络不可用或预算耗尽）")

    lines += [
        "",
        "## 八、方法与局限",
        "",
        "- **保守匹配**：只接受精确 slug，或搜索结果中归一化后完全相等的",
        "  slug/标题。不做模糊接受——错一条边比少一条边更糟，因为下游会当真。",
        "- **分母不含加载器产物**（forge/fabric-loader/paper 等），否则匹配率",
        "  会被永远查不到的合法名称拉低。",
        "- **只抽 2 个版本**做依赖探测，且 `versions` 数组顺序未在文档中约定，",
        "  故取首尾两端。因此声明密度是**下界**，不是精确值。",
        "- **词边界重试（默认开启）**：Modrinth 搜索按词匹配，而压缩写法",
        "  （`notenoughanimations`）一个词都召不回。所以命中失败后会再问一次",
        "  「驼峰/字母数字边界」形式（`XaerosWorldMap` → `xaeros world map`）。",
        "  **接受的规则不变**——命中项仍须归一化后与候选完全相等，因此它只可能",
        "  找到正确的项目，不可能编出一个名字不对的匹配。但它仍可能在一组同名",
        "  项目（本体/移植/续作）里挑错，这一点无法用字符串规则消除。",
        "  实测收益：45.8% → 50.8%（6/120 全部是驼峰名）。",
        "  用 `--no-variant-retry` 可关闭。",
        "- **未覆盖 CurseForge**：需 `x-api-key` + 审批 + 商用协议。若大量",
        "  `not_on_modrinth` 实际在 CurseForge，本报告的匹配率会低估真实可达性。",
        "- **全小写连写与真别名机械无解**：`justzoom`、`rarcompat` 没有可切分点",
        "  （需要词典/分词器），`appliedenergistics2`→`ae2`、`TConstruct`→",
        "  `tinkers-construct` 是项目改名/别名（需要人工别名表）。这两类占残差的",
        "  主体，**都不是调参数能解决的**。",
        "",
        f"网络错误统计：`{json.dumps(result['http']['errors'], ensure_ascii=False)}`",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--edges", type=Path, default=EDGES)
    ap.add_argument("--out-md", type=Path, default=OUT_MD)
    ap.add_argument("--out-json", type=Path, default=OUT_JSON)
    ap.add_argument("--max-lookups", type=int, default=500,
                    help="hard cap on network requests (default 500)")
    ap.add_argument("--sample", type=int, default=120,
                    help="resolve a deterministic sample of N candidates "
                         "(0 = all; default 120). Sampling is by sha256(name) "
                         "order, so it is reproducible and unbiased w.r.t. "
                         "name and frequency.")
    ap.add_argument("--probe-deps", type=int, default=25,
                    help="projects to inspect for incompatible declarations")
    ap.add_argument("--no-variant-retry", action="store_true",
                    help="disable the mechanical word-boundary re-query. On by "
                         "default because it is safe by construction: a variant "
                         "only changes the QUESTION, while acceptance still "
                         "requires the hit to normalise to exactly the candidate. "
                         "It cannot invent a name-mismatched match (it can still "
                         "pick the wrong project among homonyms -- see docs).")
    ap.add_argument("--causal-sample", type=int, default=60,
                    help="causal-edge subjects to resolve (0 = all; default 60). "
                         "Bounded so this pass cannot starve the main metric.")
    ap.add_argument("--gap", type=float, default=0.3,
                    help="seconds between requests (Modrinth allows 300/min)")
    ap.add_argument("--offline", action="store_true",
                    help="use cache only; never touch the network")
    ap.add_argument("--no-exclude-libs", action="store_true",
                    help="keep Java/Minecraft runtime libraries in the "
                         "denominator (reproduces the uncorrected rate)")
    args = ap.parse_args(argv)

    reports = load_reports(args.index)
    candidates = collect_candidates(reports)

    # how many reports each candidate appears in -- drives the "what to fix
    # first" ordering in the report
    freq: Counter[str] = Counter()
    for rep in reports:
        seen = {mixin_stem(c) for c in rep.get("mixin_configs") or [] if c}
        seen |= {jar_stem(j) for j in rep.get("jars") or [] if j}
        for name in seen:
            freq[name] += 1

    client = Client(offline=args.offline, max_lookups=args.max_lookups, gap=args.gap)

    all_candidates = sorted(candidates)
    # Two kinds of name are not mods and can never resolve: Java/MC runtime
    # libraries, and loader artifacts (fmlloader, fabric-loader...). Keeping
    # either in the denominator measures harvester noise, not API coverage --
    # `fmlloader` alone appeared in 60 reports.
    _loader_keys = {norm_key(x) for x in LOADER_ARTIFACTS}
    lib_set = {n for n in all_candidates if is_runtime_lib(n)}
    loader_set = {
        n for n in all_candidates
        if n not in lib_set and norm_key(n) in _loader_keys
    }
    non_mod = (
        set() if args.no_exclude_libs else (lib_set | loader_set)
    )
    pool = [name for name in all_candidates if name not in non_mod]
    if args.sample and len(pool) > args.sample:
        # sha256 order: reproducible, and uncorrelated with name or frequency
        # (taking the first N alphabetically would bias toward 'a*' mods).
        ordered = sorted(pool, key=lambda n: hashlib.sha256(
            n.encode("utf-8")).hexdigest())
        chosen = ordered[: args.sample]
    else:
        chosen = pool

    resolved: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    by_origin: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "resolved": 0}
    )
    resolved_via: Counter[str] = Counter()

    measured = 0
    skipped = 0
    for i, name in enumerate(chosen, 1):
        origins = candidates[name]
        verdict = resolve(client, name, variant_retry=not args.no_variant_retry)
        if verdict["reason"] == "budget_exhausted":
            # Never looked up. Counting these as "unresolved" would deflate the
            # match rate and turn an exhausted budget into a false failure, so
            # they are excluded from the denominator and reported separately.
            skipped = len(chosen) - i + 1
            break
        measured += 1
        bucket = "both" if len(origins) > 1 else next(iter(origins))
        by_origin[bucket]["total"] += 1
        if verdict["resolved"]:
            by_origin[bucket]["resolved"] += 1
            resolved_via[verdict["via"]] += 1
            resolved[name] = verdict
        else:
            reasons[verdict["reason"]] += 1
            unresolved.append(
                {
                    "name": name,
                    "origins": sorted(origins),
                    "reports": freq[name],
                    "reason": verdict["reason"],
                }
            )
        if i % 50 == 0:
            print(f"  ... {i}/{len(chosen)} resolved={len(resolved)} "
                  f"lookups={client.lookups}", file=sys.stderr)

    subs = causal_subjects(args.edges)
    # The causal-subject pass needs its own bound: there are ~170 distinct
    # modids and each costs up to 3 requests, which would starve the main
    # measurement. Same deterministic hash sampling, and only measured
    # subjects count toward the rate.
    if args.causal_sample and len(subs) > args.causal_sample:
        subs_ordered = sorted(subs, key=lambda s: hashlib.sha256(
            s.encode("utf-8")).hexdigest())
        subs_sample = subs_ordered[: args.causal_sample]
    else:
        subs_sample = subs
    sub_measured = 0
    sub_resolved: list[str] = []
    for sub in subs_sample:
        verdict = resolve(client, sub, variant_retry=not args.no_variant_retry)
        if verdict["reason"] == "budget_exhausted":
            break
        sub_measured += 1
        if verdict["resolved"]:
            sub_resolved.append(sub)

    probe = probe_dependencies(
        client, list(resolved.values()), args.probe_deps
    ) if args.probe_deps else {}

    total = measured
    rate = len(resolved) / total if total else 0.0
    passed = rate >= 0.40
    if passed:
        verdict_text = (
            "匹配率达标，1D.2（Modrinth 元数据抓取）可以做；"
            "优先级取决于第七节的 `incompatible` 密度——若该密度过低，"
            "声明式边的价值主要来自 jar 清单（1D.1），而非 API。"
        )
    else:
        verdict_text = (
            "匹配率未达标。**暂停 1D.2**，先解决「模组名 → 项目 ID」映射"
            "（别名表 / jar 清单 modid / CurseForge 补充），否则抓回来的元数据"
            "会大量挂空。1D.1（本地 jar 清单解析）不受此影响，可继续。"
        )

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gate": {"threshold": 0.40, "passed": passed, "verdict": verdict_text},
        "http": {
            "lookups": client.lookups,
            "cache_hits": client.cache_hits,
            "errors": dict(client.errors),
            "budget_exhausted": client.exhausted,
        },
        "metrics": {
            "reports": len(reports),
            "candidates_total": len(all_candidates),
            "runtime_lib_candidates": len(lib_set),
            "loader_artifact_candidates": len(loader_set),
            "mod_candidates": len(pool),
            "sample_size": len(chosen),
            "candidates": total,
            "measured": measured,
            "skipped": skipped,
            "resolved": len(resolved),
            "match_rate": round(rate, 4),
            "by_origin": {k: dict(v) for k, v in by_origin.items()},
            "resolved_via": dict(resolved_via),
            "reasons": dict(reasons),
            "mod_ids_populated": sum(1 for r in reports if r.get("mod_ids")),
            "causal_subjects": len(subs),
            "causal_measured": sub_measured,
            "causal_resolved": len(sub_resolved),
            "causal_rate": (
                round(len(sub_resolved) / sub_measured, 4) if sub_measured else 0.0
            ),
        },
        "resolved_sample": [
            {"name": k, "slug": v["slug"], "via": v["via"]}
            for k, v in list(sorted(resolved.items()))[:30]
        ],
        "runtime_libs": sorted(
            ({"name": n, "reports": freq.get(n, 0)} for n in non_mod),
            key=lambda r: (-r["reports"], r["name"]),
        )[:15],
        "unresolved": unresolved,
        "dependency_probe": probe,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.out_md.write_text(render_md(result), encoding="utf-8")

    print(
        f"candidates={total} resolved={len(resolved)} rate={rate:.1%} "
        f"lookups={client.lookups} cache_hits={client.cache_hits} "
        f"gate={'PASS' if passed else 'FAIL'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
