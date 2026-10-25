#!/usr/bin/env python
"""Turn the undiagnosed tail into *reviewable* rule candidates -- never into rules.

WHY THIS IS NOT "AN LLM THAT WRITES RULES"
  ROADMAP 1E.3 asks for LLM-assisted rule drafting with a human in the loop.
  The hard constraint attached to it is that model output must never reach
  `mcd/rules/builtin/`, must pass `tests/test_rule_metadata.py`, and must carry
  the generating model and date. Those three constraints are only worth
  something if they are enforced by code rather than by good intentions, so this
  tool splits the job in two halves:

    --report   deterministic, offline. Clusters the reports no rule fires on,
               and for each cluster emits the `when` skeleton plus the two
               numbers that decide whether a rule is worth writing at all:
               how many reports the cluster holds, and whether its message is
               reusable or report-specific.

    --ingest   the only door into `corpus/rule-drafts/`. It refuses a candidate
               whose lifecycle is not `draft`, whose id does not start with
               `candidate.`, whose fixtures do not exist, that lacks
               `generated_by`, or that fires on nothing.

  So the LLM (or the human) writes YAML; this tool decides whether it is
  admissible. Nothing here calls a network.

WHY THE SHAPE OF THE TAIL MATTERS MORE THAN THE CLUSTERS
  The tempting move is "cluster, then write one rule per cluster". Before doing
  that, measure what one rule buys. At the time of writing:

      uncovered reports                     117 / 454
      distinct signatures                   107
      clusters of size 1                    100   (85% of the uncovered set)
      reports per rule, one rule/cluster    1.09
      top-10 share of the uncovered set     17%

  ROADMAP risk R4 fixed the stopping rule in advance: if the top-10 uncovered
  patterns hold < 30%, the long tail is exhausted and the answer is structured
  output for the user, not more rules. 17% < 30%, so R4 fires. The pack still
  lists every cluster -- but it labels the ones that would buy a single report
  `singleton`, because a rule that can only ever fire on the report it was
  derived from is an overfit, not coverage.

  This is the honest output of 1E.3: the bottleneck it was supposed to fix
  (manual rule-writing cost) is real, but at 1.09 reports per rule the *value*
  is not there, and no amount of LLM throughput changes that arithmetic.

    python tools/suggest_rules.py --report corpus/RULE_CANDIDATES.md \\
                                 --json corpus/rule-candidates.json
    python tools/suggest_rules.py --ingest corpus/rule-drafts/foo.yaml \\
                                 --model "some-model" --date 2026-10-25
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

GITHUB = ROOT / "corpus" / "github"
DRAFTS = ROOT / "corpus" / "rule-drafts"
BUILTIN = ROOT / "mcd" / "rules" / "builtin"

#: A rule id that proposes itself must be distinguishable from a shipped one at
#: a glance, in a diff and in a stack trace. The prefix is the cheapest way.
CANDIDATE_PREFIX = "candidate."

#: ROADMAP risk R4 stopping rule, in one place so the pack and the docs cannot
#: drift apart.
R4_TOP_N = 10
R4_MIN_SHARE = 0.30

#: Patterns that mean "this message is about one specific report". A `when`
#: built by escaping one of these can only ever match the report it came from.
_OVERFIT_PATTERNS = (
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"), "uuid"),
    (re.compile(r"\bval\$\w+_\d+"), "mixin shadow field"),
    (re.compile(r"\b\d{3,}\b"), "long number"),
    (re.compile(r"\b0x[0-9a-fA-F]{4,}"), "hex literal"),
    (re.compile(r"(?:[A-Za-z]:)?[\\/][\w.\-]+[\\/][\w.\-]+[\\/]"), "path"),
    (re.compile(r"\bat -?\d+,-?\d+,-?\d+\b|\bat \d+,\d+,\d+\b"), "coordinates"),
)


def corpus_files() -> list[Path]:
    """The corpus file set, enumerated exactly as `coverage_report.py` does.

    Recursive on purpose. The pack is cross-checked against `coverage.json`
    (`tests/test_rule_candidates.py`), and that file walks `**/*.crash.txt`. The
    corpus is flat today so the two agree either way -- but the moment one of
    them nests, `total_reports` and `files_scanned` stop being the same
    quantity and the cross-check fails for a reason unrelated to rules. One
    enumerator, used by both the walk and the total.
    """
    return sorted(GITHUB.glob("**/*.crash.txt"))


def load_uncovered() -> list[dict]:
    """Every report no rule fires on, with the attributes a `when` can key on."""
    from mcd.parser.report import parse_file, read_report_text
    from mcd.rules.engine import RuleSet, run_rules

    import coverage_report as cr

    ruleset = RuleSet.load()
    out: list[dict] = []
    skipped: list[str] = []
    for path in corpus_files():
        try:
            rep = parse_file(path)
        except Exception as exc:  # noqa: BLE001 - one bad fragment must not
            # stop the pack from being generated at all. `coverage_report.py`
            # made the same call and counts these out of both `totals.n` and
            # `uncovered`, so the two artifacts stay comparable.
            skipped.append(f"{path.parent.name}/{path.name}: {type(exc).__name__}")
            continue
        if run_rules(rep, ruleset):
            continue
        sig = rep.exceptions[0].signature if rep.exceptions else "no exception block"
        block = rep.exceptions[-1] if rep.exceptions else None
        kind = (block.kind if block else "") or sig.split(":", 1)[0].strip()
        out.append({
            "report": f"{path.parent.name}/{path.name.replace('.crash.txt', '')}",
            "report_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "signature": sig,
            "kind": kind.strip(),
            "message": sig.split(":", 1)[1].strip() if ":" in sig else "",
            "description": rep.description or "",
            "bucket": cr.classify(read_report_text(path), rep),
            "loader": rep.system.loader or "",
        })
    if skipped:
        print(f"warning: {len(skipped)} fragment(s) failed to parse and were "
              f"left out of the pack: {skipped[:3]}", file=sys.stderr)
    return out


def overfit_markers(text: str) -> list[str]:
    """Which report-specific things a literal copy of `text` would encode."""
    return [label for rx, label in _OVERFIT_PATTERNS if rx.search(text or "")]


def _common_prefix(values: list[str]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    i = 0
    while i < min(len(lo), len(hi)) and lo[i] == hi[i]:
        i += 1
    return lo[:i]


def candidate_when(members: list[dict]) -> tuple[dict, str]:
    """The `when` skeleton for a cluster, plus a generalisation verdict.

    Deliberately does *not* emit a `text:` condition: `text` is the whole report
    body, so a phrase lifted from one report is both the most overfittable and
    the least readable of the available anchors. `description` and
    `exception`/`exception_msg` are the ones a reviewer can check by eye.
    """
    kinds = sorted({m["kind"] for m in members if m["kind"]})
    descs = sorted({m["description"] for m in members if m["description"]})
    msgs = [m["message"] for m in members]

    when: dict = {}
    if len(descs) == 1:
        when["description"] = [descs[0]]
    if len(kinds) == 1 and kinds[0]:
        when["exception"] = [f"^{re.escape(kinds[0])}$"]
    elif kinds:
        when["exception"] = [f"^({'|'.join(re.escape(k) for k in kinds)})$"]

    if len(set(msgs)) == 1 and msgs[0]:
        when["exception_msg"] = [re.escape(msgs[0])]
        verdict = "reusable"
    elif len(msgs) > 1 and any(msgs):
        pref = _common_prefix(msgs).strip()
        if len(pref) >= 8:
            when["exception_msg"] = [re.escape(pref)]
            verdict = "needs_generalisation"
        else:
            verdict = "needs_generalisation"
    else:
        verdict = "needs_generalisation"

    if len(members) == 1:
        verdict = "singleton"
        for m in members:
            if overfit_markers(m["message"]):
                verdict = "singleton+overfit"
    return when, verdict


def build_clusters(uncovered: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in uncovered:
        groups[rec["signature"]].append(rec)
    clusters = []
    for sig, members in groups.items():
        when, verdict = candidate_when(members)
        clusters.append({
            "signature": sig,
            "size": len(members),
            "bucket": Counter(m["bucket"] for m in members).most_common(1)[0][0],
            "kinds": sorted({m["kind"] for m in members if m["kind"]}),
            "description": sorted({m["description"] for m in members
                                   if m["description"]}),
            "overfit": sorted({x for m in members
                               for x in overfit_markers(m["message"])}),
            "verdict": verdict,
            "when": when,
            "reports": [m["report"] for m in members],
        })
    clusters.sort(key=lambda c: (-c["size"], c["signature"]))
    return clusters


def summarise(uncovered: list[dict], clusters: list[dict]) -> dict:
    n = len(uncovered) or 1
    top_n = sum(c["size"] for c in clusters[:R4_TOP_N])
    total_reports = len(corpus_files())
    return {
        "total_reports": total_reports,
        "uncovered": len(uncovered),
        "clusters": len(clusters),
        "singletons": sum(1 for c in clusters if c["size"] == 1),
        "singleton_reports": sum(c["size"] for c in clusters if c["size"] == 1),
        "reports_per_rule": round(len(uncovered) / max(1, len(clusters)), 2),
        "top_n": R4_TOP_N,
        "top_n_reports": top_n,
        "top_n_share": round(top_n / n, 4),
        "r4_threshold": R4_MIN_SHARE,
        "r4_fires": (top_n / n) < R4_MIN_SHARE,
        "verdicts": dict(Counter(c["verdict"] for c in clusters)),
    }


def _yaml_scalar(text: str) -> str:
    r"""YAML single-quoted scalar: no escape processing, so a regex stays legible.

    The pack is read by a human before anything else, and `'^java\.lang\.X$'`
    (single-quoted, one level of escaping) is twice as easy to check by eye as
    the same regex inside double quotes, where every backslash is doubled.
    """
    return "'" + str(text).replace("'", "''") + "'"


def render_md(summary: dict, clusters: list[dict]) -> str:
    s = summary
    lines = [
        "# RULE_CANDIDATES — 未覆盖长尾的候选清单（不是规则）",
        "",
        "> 由 `tools/suggest_rules.py --report` 生成，**不要手改**。",
        "> 本文件只提出候选，**不含任何生效规则**；生效路径见文末「怎么用」。",
        "",
        f"扫描 {s['total_reports']} 份 · 未覆盖 **{s['uncovered']}** 份 · "
        f"签名聚类 {s['clusters']} 个",
        "",
        "## 先看这两个数：一条规则能买到几份报告",
        "",
        f"- 只按签名聚类，一条规则平均覆盖 **{s['reports_per_rule']} 份**报告",
        f"- 其中 **{s['singletons']}** 个聚类只有 1 份报告"
        f"（合计 {s['singleton_reports']} 份，占未覆盖集的 "
        f"{s['singleton_reports'] / max(1, s['uncovered']):.0%}）",
        f"- top-{s['top_n']} 聚类合计 {s['top_n_reports']} 份 = "
        f"**{s['top_n_share']:.0%}**",
        "",
        f"ROADMAP 风险 R4 的停手判据是「top-{s['top_n']} < {s['r4_threshold']:.0%} "
        "→ 长尾已枯竭，转结构化输出，停止堆规则」。"
        f"本次实测 {s['top_n_share']:.0%}，"
        + ("**判据触发**：写规则不再是瓶颈。" if s["r4_fires"]
           else "判据未触发：还有值得写的成簇模式。"),
        "",
        "## 聚类清单",
        "",
        "| # | 份数 | 桶 | 签名 | 泛化判定 |",
        "|---|---|---|---|---|",
    ]
    for i, c in enumerate(clusters, 1):
        sig = c["signature"].replace("|", "\\|")[:80]
        lines.append(f"| {i} | {c['size']} | `{c['bucket']}` | `{sig}` "
                     f"| `{c['verdict']}` |")

    lines += [
        "",
        "## 每个聚类建议的 `when` 骨架",
        "",
        "`singleton` 的条目也列出来，理由不是「可以写」，而是让后来人看到"
        "「这里写过一次就没再出现过」——否则每半年都会有人重新发现它们。",
        "",
    ]
    for i, c in enumerate(clusters, 1):
        lines.append(f"### {i}. {c['signature'][:100]} — {c['size']} 份")
        lines.append("")
        lines.append(f"- 桶：`{c['bucket']}` · 异常类："
                     f"{', '.join('`%s`' % k for k in c['kinds']) or '（无）'}")
        if c["description"]:
            lines.append("- 描述：" + ", ".join(
                f"`{d}`" for d in c["description"]))
        lines.append(f"- 泛化判定：`{c['verdict']}`"
                     + (f" · 报告特有内容：{', '.join(c['overfit'])}"
                        if c["overfit"] else ""))
        lines.append(f"- 报告：{', '.join('`%s`' % r for r in c['reports'][:6])}"
                     + (" …" if len(c["reports"]) > 6 else ""))
        if c["when"]:
            lines.append("- 建议 `when`：")
            lines.append("")
            lines.append("```yaml")
            lines.append("when:")
            for k, v in c["when"].items():
                lines.append(f"  {k}:")
                for item in v:
                    lines.append(f"    - {_yaml_scalar(item)}")
            lines.append("```")
        lines.append("")

    lines += [
        "## 怎么用（人在环，两步）",
        "",
        "1. **写**：把某个聚类（或几个聚类）写成候选 YAML，放到任意临时路径。"
        "`lifecycle_status` 必须是 `draft`，`id` 必须以 `candidate.` 开头，"
        "`provenance.fixtures` 必须指向真实存在的报告，并带 `generated_by:"
        " {model, date}`。",
        "2. **过闸**：",
        "",
        "```bash",
        "python tools/suggest_rules.py --ingest <候选.yaml> \\",
        '    --model "<生成模型名>" --date <YYYY-MM-DD>',
        "```",
        "",
        "工具会拒收以下任一情况：不是 `draft`、`id` 前缀不对、fixture 不存在、"
        "缺 `generated_by`、以及**在语料上一份报告都不命中**（写不出证据的规则"
        "就是死重量）。通过后落到 `corpus/rule-drafts/`，**永远不进 "
        "`mcd/rules/builtin/`**。",
        "",
        "`tests/test_rule_drafts.py` 对 `corpus/rule-drafts/` 复查同一组约束，"
        "`tests/test_rule_metadata.py::test_no_draft_rule_is_in_builtin` 保证"
        "草稿不会混进发货规则。",
        "",
    ]
    return "\n".join(lines)


# --- ingest ----------------------------------------------------------------
def _builtin_ids() -> set[str]:
    from mcd.rules.engine import RuleSet
    return {r.id for r in RuleSet.load().rules}


def _fixture_exists(name: str) -> bool:
    """Resolve a fixture key the same way `tests/test_gaps.py` does.

    A harvested pin is `repo/number` with the *repo suffix only* (`sodium/3473`),
    because the corpus directory is `<org>__<repo>` and issue numbers collide
    across repositories. Synthetic fixtures are bare filenames or
    `synthetic/<file>`.
    """
    name = str(name)
    if name.startswith(("gt:", "aternos:")):
        return True                      # external pins are not corpus files
    if name.startswith("synthetic/"):
        name = name[len("synthetic/"):]
    if "/" in name and name.split("/")[-1].isdigit():
        repo, _, number = name.rpartition("/")
        repo = repo.rpartition("/")[-1]  # accept org/repo/number too
        return bool(list(GITHUB.glob(f"*__{repo}/{number}.crash.txt")))
    if "/" in name:
        return False
    return (ROOT / "tests" / "fixtures" / "synthetic" / name).exists()


def validate_candidate(path: Path, model: str,
                       date: str) -> tuple[dict, list[str], dict]:
    """Return (doc, errors, meta). Empty errors means the candidate is admissible."""
    import yaml

    errors: list[str] = []
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        return {}, [f"YAML did not parse: {type(exc).__name__}: {exc}"], {}
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        return {}, ["top level must be a mapping with a `rules:` list"], {}

    gen = doc.get("generated_by")
    if not isinstance(gen, dict) or not gen.get("model") or not gen.get("date"):
        errors.append("missing top-level `generated_by: {model, date}`")
    if model and isinstance(gen, dict) and gen.get("model") != model:
        errors.append(f"generated_by.model is {gen.get('model')!r}, "
                      f"--model says {model!r}")
    if date and isinstance(gen, dict) and str(gen.get("date")) != date:
        errors.append(f"generated_by.date is {gen.get('date')!r}, "
                      f"--date says {date!r}")

    builtin = _builtin_ids()
    for r in doc["rules"]:
        rid = r.get("id", "<no id>")
        if not str(rid).startswith(CANDIDATE_PREFIX):
            errors.append(f"{rid}: id must start with {CANDIDATE_PREFIX!r}")
        if rid in builtin:
            errors.append(f"{rid}: id collides with a shipped rule")
        if str(r.get("lifecycle_status")) != "draft":
            errors.append(f"{rid}: lifecycle_status must be 'draft' "
                          f"(got {r.get('lifecycle_status')!r})")
        fxs = (r.get("provenance") or {}).get("fixtures") or []
        if not fxs:
            errors.append(f"{rid}: provenance.fixtures is empty")
        for f in fxs:
            if not _fixture_exists(f):
                errors.append(f"{rid}: fixture {f!r} does not exist")

    if errors:
        return doc, errors, {}

    # Last gate: does it actually fire on anything? A draft that covers nothing
    # is exactly the "rule with no proof" that ROADMAP 0.3 deleted by the dozen.
    from mcd.parser.report import parse_file
    from mcd.rules.engine import Rule, RuleSet, run_rules

    rules = [Rule.from_dict(r, source=path.name) for r in doc["rules"]]
    rs = RuleSet(rules)
    hits: dict[str, list[str]] = {r.id: [] for r in rules}
    for fx_path in sorted(GITHUB.glob("*/*.crash.txt")):
        rep = parse_file(fx_path)
        for f in run_rules(rep, rs):
            hits.setdefault(f.rule_id, []).append(
                f"{fx_path.parent.name}/{fx_path.name.replace('.crash.txt', '')}")
    dead = [rid for rid, h in hits.items() if not h]
    if dead:
        errors.append(f"fires on no corpus report at all: {dead}")
        return doc, errors, {}

    return doc, [], {"hits": {k: len(v) for k, v in hits.items()},
                     "sample_hits": {k: v[:5] for k, v in hits.items()}}


def ingest(path: Path, model: str, date: str) -> int:
    if BUILTIN in path.resolve().parents or path.resolve() == BUILTIN:
        print("refusing: builtin/ is not an ingest target", file=sys.stderr)
        return 2
    doc, errors, meta = validate_candidate(path, model, date)
    if errors:
        print(f"refused {path.name}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    DRAFTS.mkdir(parents=True, exist_ok=True)
    target = DRAFTS / path.name
    shutil.copyfile(path, target)
    print(f"ingested -> {target.relative_to(ROOT)}")
    for rid, n in meta.get("hits", {}).items():
        sample = ", ".join(meta["sample_hits"].get(rid, []))
        print(f"  {rid}: fires on {n} corpus report(s) -- {sample}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", metavar="PATH", help="write the markdown pack")
    ap.add_argument("--json", metavar="PATH", help="write the JSON twin")
    ap.add_argument("--ingest", metavar="PATH", help="validate a candidate YAML "
                                                    "and copy it to corpus/rule-drafts/")
    ap.add_argument("--model", default="", help="expected generated_by.model")
    ap.add_argument("--date", default="", help="expected generated_by.date")
    args = ap.parse_args(argv)

    if args.ingest:
        return ingest(Path(args.ingest), args.model, args.date)
    if not (args.report or args.json):
        ap.error("pass --report/--json to build the pack, or --ingest to admit a draft")

    uncovered = load_uncovered()
    if not uncovered:
        print("no uncovered reports -- nothing to suggest", file=sys.stderr)
        return 0
    clusters = build_clusters(uncovered)
    summary = summarise(uncovered, clusters)

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        # NOT `out.write_text(..., newline="\n")`: that keyword is 3.10+, and
        # `requires-python` is ">=3.9". Builtin `open()` has had `newline` since
        # forever, and for writing it is byte-for-byte the same thing.
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render_md(summary, clusters))
        print(f"wrote {out}")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "clusters": clusters}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
        print(f"wrote {out}")

    print(f"uncovered {summary['uncovered']}/{summary['total_reports']} · "
          f"{summary['clusters']} clusters · "
          f"{summary['reports_per_rule']} reports/rule · "
          f"top-{summary['top_n']} = {summary['top_n_share']:.0%} "
          f"(R4 {'fires' if summary['r4_fires'] else 'does not fire'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
