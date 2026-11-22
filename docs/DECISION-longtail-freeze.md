# 决策记录 · 覆盖率长尾冻结（F1 / R4）

> 2026-11-07。状态：**冻结，生效中**。本文是可引用的决策记录，不是计划。
> 证据：`docs/DECISION-coverage.md`（A2）、`corpus/RULE_CANDIDATES.md`、
> `corpus/CRASH-FINGERPRINTS.md`（D3）、`corpus/COVERAGE.md`。
> **2026-11-22 复算**：下表数字由 `corpus/coverage.json` 与
> `corpus/coverage-granularity.json` 重新生成（规则此后有增加）；决策与阈值未变。

## 决定

**不再为未覆盖长尾里的非泛化单例写规则。** 覆盖率作为质量指标继续追踪，但
"再加几条规则把 76.6% 推到 80%" 不再是一项工作项。省下的工时投向真实数据验证、
证据质量与发布链路。

## 依据（全部是实测，不是估计）

| 量 | 值 | 来源 |
|---|---|---|
| 语料诊断率 | **348/454 = 76.6%** | `coverage.json` |
| 未覆盖 | **106** 份，`other` 桶占 69 份 | `coverage.json` |
| 签名聚类 | 103 簇 / **99 个单例** / 1.07 份每规则 | `coverage-granularity.json` |
| top-10 占比 | **15.5%**（R4 停手阈值 30%） | 同上 |
| 抹掉类名/数字/路径/引号后 | 102 簇 / 100 单例 / **1.08 份每规则** | 同上：长尾不是聚类粒度造成的 |
| 崩溃指纹（D3） | 454 份 → **377 个指纹**，平均簇 1.204，多成员簇 38，其中 **7 个混合了不同描述** | `crash-fingerprints.json` |

三条独立证据指向同一结论：

1. **A2 否掉了"是聚类问题"这个怀疑**：把消息里的类名、数字、路径、引号内容全部
   抹平后重新聚类，仍是 102 簇 / 100 单例 / 1.08 份每规则。长尾在消息层面就是散的。
2. **粗粒度的高收益是假的**：只按异常类聚类，3 条规则能到 25%，但那 6 份簇来自
   6 个互不相关的报告，一条规则对它们只能说空话。判据：同 kind、同消息模板、
   同 description 才算一个可写的失败模式。
3. **D3 从另一头量了一次**：指纹细到平均 1.20 份一簇，仍有 7 个簇混合不同
   description —— 连"按崩溃形状合并"都不能无条件当成同一结论，更不用说写一条
   通用规则。R11 因此要求 `CRASH-FINGERPRINTS.md` 永远列出簇内差异。

## 已经做完的（不是欠账）

- 三条零撞车规则（`game-provider` 3 / `class-already-loaded` 2 / `quilt-coerce` 2），
  语料 337/454 → 344/454（当时口径；此后规则继续增加，当前见上表）。
  写之前每条都按"异常链中任一条命中"量过 gain 与 collision。
- **明确拒绝**通用 `missing-class`：gain 6，但 collision **30**，其中 24 次已被
  `mod.coremod-missing` 解释。用 6 份新覆盖换 30 份报告多一条 finding 是负收益。
- 5 份 `Manually triggered debug crash` 是人按调试键产生的，**不是故障**，不计入
  "诊断能力改进"；`candidate.debug-crash.manual` 保持 draft。

## 解冻条件（满足任一，且必须重跑下面的复测）

1. **新语料带来 ≥30 份同形报告**（n≥30 才可引用为比率），且同 kind、同消息模板、
   同 description —— 这时它不再长尾，是一个真实的高频失败模式。
2. **出现 ≥10 份同质簇**，且 `coverage_granularity.py` 的 `writable_clusters` 里
   出现新的 `descriptions == 1` 条目。
3. **发现现有规则误报**（新候选 collision = 0 而 gain ≥5）——优先修误报规则，
   而不是绕着它加新规则。

复测命令（任何解冻都要附这三条的输出）：

```bash
python tools/coverage_granularity.py --json
python tools/coverage_report.py
python tools/suggest_rules.py --report corpus/RULE_CANDIDATES.md --json corpus/rule-candidates.json
bash run_tests.sh                      # 门禁 [7] 会拦下没同步的文档数字
```

## 明确不做

- 为单例逐条写规则（预计 0.4pp/条，且最大簇不是故障）。
- 把"手动触发调试崩溃"算成诊断率改进。
- 用粗粒度 `kind` 簇的高覆盖率当作成绩 —— 那是把不同失败模式塞进一条规则。
- 用指纹聚类自动合并结论（`CRASH-FINGERPRINTS.md` 的 7 个混合簇是反例）。
