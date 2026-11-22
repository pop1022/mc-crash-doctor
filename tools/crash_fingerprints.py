"""Cluster the corpus by crash fingerprint and *show what each group hides*.

AUDIT §4 asks for "N near-identical reports -> one conclusion + a count". The
danger named in the risk register (R11) is a fingerprint so coarse that it
merges different failures. So this tool does not just count: for every group of
two or more it prints the distinct descriptions, rule ids and loaders inside
it, and refuses to call the clustering clean when a group mixes descriptions.

    python tools/crash_fingerprints.py            # print + write both artifacts
    python tools/crash_fingerprints.py --check    # exit 1 when a group is mixed
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.fingerprint import fingerprint  # noqa: E402
from mcd.parser.report import parse_file  # noqa: E402
from mcd.rules.engine import RuleSet, run_rules  # noqa: E402
from mcd.triage.attribution import triage  # noqa: E402

OUT_JSON = ROOT / "corpus" / "crash-fingerprints.json"
OUT_MD = ROOT / "corpus" / "CRASH-FINGERPRINTS.md"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    paths = sorted((ROOT / "corpus" / "github").rglob("*.crash.txt"))
    if not paths:
        print("corpus/github is empty (gitignored on fresh clones) -- nothing to "
              "cluster; run tools/harvest_corpus.py first", file=sys.stderr)
        return 2

    rules = RuleSet.load()
    groups: dict[str, list[dict]] = {}
    for p in paths:
        try:
            rep = parse_file(p)
        except Exception:  # noqa: BLE001 - one bad fragment must not stop a scan
            continue
        findings = run_rules(rep, rules)
        t = triage(rep)
        top = t.suspects[0].modid if t.suspects else ""
        fp = fingerprint(rep, top_suspect=top)
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        groups.setdefault(fp, []).append({
            "report": rel,
            "description": rep.description or "",
            "loader": rep.system.loader or "",
            "mc_version": rep.system.minecraft_version or "",
            "rules": sorted({f.rule_id for f in findings}),
            "top_suspect": top,
            "root_cause": (rep.root_cause.signature if rep.root_cause else "")[:120],
        })

    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    multi = [(fp, rows) for fp, rows in ranked if len(rows) >= 2]
    mixed = [(fp, rows) for fp, rows in multi
             if len({r["description"] for r in rows}) > 1]
    total = sum(len(v) for v in groups.values())
    mean_cluster = total / len(groups) if groups else 0.0

    print(f"{total} reports -> {len(groups)} fingerprints | "
          f"mean cluster {mean_cluster:.2f} | multi {len(multi)} | "
          f"mixed-description clusters {len(mixed)}")
    print(f"{'fp':14s} {'n':>3s} {'descs':>5s}  root cause")
    for fp, rows in multi[:15]:
        print(f"  {fp:12s} {len(rows):3d} "
              f"{len({r['description'] for r in rows}):5d}  "
              f"{rows[0]['root_cause'][:70]}")

    payload = {
        "corpus_files": len(paths),
        "reports": total,
        "clusters": len(groups),
        "singletons": sum(1 for v in groups.values() if len(v) == 1),
        "mean_cluster_size": round(mean_cluster, 3),
        "multi_member_clusters": len(multi),
        "mixed_description_clusters": len(mixed),
        "clusters_detail": [
            {"fingerprint": fp, "size": len(rows),
             "distinct_descriptions": sorted({r["description"] for r in rows}),
             "distinct_rules": sorted({x for r in rows for x in r["rules"]}),
             "distinct_loaders": sorted({r["loader"] for r in rows}),
             "reports": rows}
            for fp, rows in multi
        ],
    }
    if "--json" in argv or True:
        OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8", newline="\n")

    lines = [
        "# 崩溃指纹聚类（D3 / R11 验收）",
        "",
        f"> 生成：`python tools/crash_fingerprints.py`。语料 {len(paths)} 份，",
        f"> 成功解析 {total} 份 → **{len(groups)} 个指纹**，平均簇 {mean_cluster:.2f}，",
        f"> 多成员簇 {len(multi)} 个。",
        "",
        "指纹 = `(loader, 根因 kind + 归一化 message, top suspect, 顶层帧)`。",
        "报告 id、时间戳、路径、数字一律不进指纹——它们只会让同一个 bug 的两份日志",
        "看起来不同。",
        "",
        "## R11：过粗合并的判据",
        "",
        "一个簇里出现 **>1 种 description**，说明它把不同的问题合在了一起。",
        f"本次：{len(mixed)} / {len(multi)} 个多成员簇混合了 description。",
        "下表把每个簇的差异全部列出来，合并是否可接受由人判断，工具不替人删。",
        "",
        "| 指纹 | 份数 | 不同描述 | 不同规则 | 根因 |",
        "|---|---:|---:|---:|---|",
    ]
    for fp, rows in multi:
        d = {r["description"] for r in rows}
        rules = {x for r in rows for x in r["rules"]}
        cause = rows[0]["root_cause"].replace("|", "\\|")[:60]
        lines.append(f"| `{fp}` | {len(rows)} | {len(d)} | {len(rules)} | `{cause}` |")
    lines += ["", "## 每个多成员簇的成员与差异", ""]
    for fp, rows in multi:
        lines += [f"### `{fp}` — {len(rows)} 份", ""]
        descs = sorted({r["description"] for r in rows})
        if len(descs) > 1:
            lines.append("- **不同描述**: " + " / ".join(f"`{x or '(空)'}`" for x in descs))
        for r in rows:
            lines.append(f"- `{r['report'].split('/')[-1]}` "
                         f"[{r['loader'] or '?'}] desc=`{r['description'] or '(空)'}` "
                         f"rules={','.join(r['rules']) or '-'}")
        lines.append("")
    # bytes, not write_text(newline=): that keyword is 3.10+ and this is a
    # tool users on the declared 3.9 floor may run.
    OUT_MD.write_bytes("\n".join(lines).encode("utf-8"))
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")

    if "--check" in argv and mixed:
        print(f"R11: {len(mixed)} clusters mix descriptions -- do not use this "
              "grouping as a single conclusion", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
