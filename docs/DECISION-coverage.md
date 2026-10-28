# 决策记录 · 覆盖率的长尾到底枯竭没有（A2）

> 2026-10-27。回答 `ROADMAP` R4 与 `corpus/RULE_CANDIDATES.md` 的一个隐含结论：
> "每条规则只覆盖 1.09 份，写规则不再是瓶颈"。这个结论如果错了，W2 该重写候选清单；
> 如果对了，W2 应该缩到 3 条规则并把工时挪走。
>
> 复现：`python tools/coverage_granularity.py --json` → `corpus/coverage-granularity.json`

## 落地结果（2026-10-27，本节后写）

三条规则已写进 `mcd/rules/builtin/mod-loading.yaml`：`loader.game-provider-missing`、
`mixin.class-already-loaded`、`quilt.version-constraint-unreadable`。

| 指标 | 写之前 | 写之后 |
|---|---|---|
| 未覆盖 | 117 | **110** |
| 语料诊断率 | 337/454 = 74.2% | **344/454 = 75.8%** |
| 签名聚类 | 107 簇 / 100 单例 / 1.09 份每规则 | **103 簇 / 99 单例 / 1.07** |
| kind+template 聚类 | 106 簇 / 101 单例 / 1.10 份每规则 | **102 簇 / 100 单例 / 1.08 份/规则** |
| 盲测 | 155/218 = 71.1%，加载器仓 43/75 = 57.3% | **156/216 = 72.2%，加载器仓 44/73 = 60.3%** |

**盲测那两个数不要当成绩读。** 三条规则各钉了一份来源报告作为 provenance，
`pinned_paths()` 会把这些报告强制划入 dev，所以盲测集从 218 缩到 216；
其中只有 1 份（fabric-loader/1093）原本在盲测里且现在被诊断出来。也就是说
72.2% 里有一半是"移走了两份未诊断样本"的结构效应。可引用的成绩是语料那条：
**74.2% → 75.8%，且这 454 份一份没少。**

## 结论

1. **长尾确实枯竭了。** 但 `RULE_CANDIDATES.md` 的 1.09 份/规则**不是**聚类粒度造成的——
   把消息里的类名、数字、路径、引号内容全部抹平后重新聚类，结果几乎不变（1.10 份/规则，
   106 簇 / 101 单例）。长尾在**消息层面**就是散的，不是被切碎的。
2. **粗粒度看起来的暴利是假的。** 只按异常类聚类，10 条规则能覆盖 60.7% 的未覆盖集
   （3 条到 25%），但那些簇是**杂烩**：`IllegalStateException | other | platform` 那 6 份
   来自 ModernFix / fabric-loader / RFTools / Mekanism 等 6 个互不相关的报告，一条规则
   对它们只能给出"某个东西状态不对"这种在多数报告上是错的话术。这与本项目今早刚修的
   缺陷（`when` 键全拼错 → 规则变成匹配一切）是同一种病。
3. **真正能写的只有 5 簇 / 16 份**，其中 5 份是"手动触发调试崩溃"（不是故障）。
   零撞车的干净收益是 **7 份 / +1.5pp**（3 条规则）。
4. **加载器仓那 32 份也是长尾。** 按同样口径只有 3 个族、共 6 份。它比 117 份更适合做
   靶子（同仓、可重采、有区间），但**不改变"长尾"这个事实**，只值 3 条规则。
5. **`missing-class` 不能写成通用规则**：它会在 30 份**已经有诊断**的报告上再报一次，
   其中 24 份已被 `mod.coremod-missing` 解释。用它换 6 份新覆盖，等于给 30 份报告加噪音。

## 方法

同一批 117 份未覆盖报告，五档粒度：

| 粒度 | 含义 |
|---|---|
| `signature (shipped)` | 现有 `RULE_CANDIDATES.md` 的口径：完整签名原文 |
| `kind` | 只按异常类（`java.lang.NullPointerException`） |
| `kind+bucket` | 异常类 + 分桶 |
| `kind+bucket+site` | 再加"抛出点是否平台帧" |
| `kind+template` | 异常类 + **消息模板**（类名/数字/路径/引号内容 → `<fqcn>` `<#>` `<path>` `<q>`） |

质量判据：一个簇值一条规则，必须**同 kind、同消息模板、同 description**。规模小但同质的
簇可以写；规模大但杂的簇不能写——后者只是把"未覆盖"变成"覆盖错了"。

## 结果

| 粒度 | 簇 | 单例 | top10 占比 | 份/规则 | 到 25% 需几条 | 到 50% 需几条 |
|---|---:|---:|---:|---:|---:|---:|
| `signature (shipped)` | 107 | 100 | 17.1% | 1.09 | 20 | 49 |
| `kind` | 48 | 30 | **60.7%** | 2.44 | **3** | 7 |
| `kind+bucket` | 60 | 38 | 44.4% | 1.95 | 5 | 13 |
| `kind+bucket+site` | 64 | 43 | 42.7% | 1.83 | 6 | 14 |
| `kind+template` | 106 | 101 | 17.9% | 1.10 | 19 | 48 |

**读法**：`kind` 那行的高收益来自丢弃信息，`kind+template` 那行证明"信息一还回来，
长尾就回来了"。所以收益不是粒度参数可以调节的——除非接受规则说空话。

### 能写成一条规则的 5 个簇（16 份）

| 簇 | 份数 | 描述数 | 值不值得写 |
|---|---:|---:|---|
| `java.lang.ClassNotFoundException \| <fqcn>` | 5 | 1 | **不写**：撞车 30 次，见下 |
| `java.lang.Throwable \| Manually triggered debug crash` | 5 | 1 | **不写**：不是故障。已有草稿 `candidate.debug-crash.manual` 明确只买"5 份容易的" |
| `ClassAlreadyLoadedException \| <fqcn> was already…` | 2 | 1 | **写**：同一 mixin 目标类被两个 jar 提供 |
| `RuntimeException \| Minecraft game provider couldn't locate…` | 2 | 1 | **写**：启动器给的游戏目录读不到 |
| `ClassCastException \| Cannot coerce loader value to a String` | 2 | 1 | **写**：Quilt 读不懂某个 mod 的版本约束 |

## 候选规则的真实收益（454 份全语料，按"异常链中任一条命中"计）

> 下表是实现**之前**的测量。实现之后，前三条的 gain 与 collision 都是 0——
> 它们已经变成规则本身，`tools/coverage_granularity.py` 里用 rule-id 区分，
> 否则一条已实现的候选会被自己的 finding 记成"撞车"。

| 候选 | gain（实现前：未覆盖 → 覆盖） | collision（实现前：已覆盖 → 再报一次） |
|---|---:|---:|
| `missing-class` | 6 | **30** |
| `game-provider` | 3 | 0 |
| `class-already-loaded` | 2 | 0 |
| `quilt-coerce` | 2 | 0 |
| `debug-crash`（非故障） | 5 | 0 |

撞车明细：36 份含 `ClassNotFoundException`，其中 30 份已有诊断——`mod.coremod-missing`
解释 24 份，其余散落在 `crash.runtime-mod`(10)、`perf.tick-timeout`(5)、
`mod.config-invalid`(5) 等。注意这些数字相加 >30，因为一份报告可以同时命中多条规则。

那 6 份未覆盖的形状也不一致：`net.minecraft.client.Minecraft`（原版类缺失）、
`KnotClient`（客户端入口在服务端跑）、`kotlin.jvm.internal.Lambda`（缺 Kotlin 标准库）、
`PlaceboTaskQueue`（自己 jar 里的类缺失）。**它们是四个不同的失败模式，不是一条规则。**

> 若要覆盖其中 2–3 份，正确做法不是新增通用规则，而是**修 `mod.client-class-on-server`
> 为什么没在这两份上触发**——现有规则漏了 `net.minecraft.client.*` 的一种写法。这是修
> 已有规则，不是加新规则，属 W2 的"护栏"任务而不是"写规则"任务。

## 加载器仓的 32 份

盲测 218 份里，加载器仓 75 份、已诊断 43、未诊断 32（57.3%）。它们看着比长尾更适合打，
因为同仓可重采、有区间。实测：

| 维度 | 分布 |
|---|---|
| 按仓库 | fabric-loader 20 / quilt-loader 7 / fabric-api 5 |
| 按桶 | other 20 / mod-bug 5 / mod-loading 4 / mixin 3 |
| 按异常类 | IllegalArgumentException 6 / RuntimeException 5，其余 17 个类各 1–2 份 |
| 按消息模板（size≥2） | **3 个族 / 6 份**：`ClassNotFoundException`、`game provider couldn't locate`、`Cannot invoke <q> because <q> is null`（后者 2 份 2 种描述，不可写成一条） |

**结论**：32 份里的可复用部分是 2 个族（4 份）。加上它们在 mod 仓的同族报告
（`game-provider` + `class-already-loaded` + `quilt-coerce` = 7 份），三条规则的实际收益是：

- 全语料 454：74.2% → **75.8%**（337 + 7 = 344，+1.5pp）
- 盲测加载器仓 75：57.3% → **62.7%**（43 + 4 = 47，+5.3pp，样本太小，只能说计数）

## 对 W2 的影响（排期修正）

原 W2（12h）：32 份逐份归因 → 写 ≤4 条族规则 → 护栏 → 复测。
按本次实测改为：

| 原任务 | 修正 |
|---|---|
| B1 逐份归因 32 份（2h） | **取消**。32 份已在 `coverage-granularity.json` 里逐条列好，不需要再人工过一遍 |
| B2 写 ≤4 条族规则（5h） | **缩到 3 条 / 2.5h**：`game-provider`、`class-already-loaded`、`quilt-coerce` |
| B3 分桶护栏（2h） | **保留并加强**：新增断言"新规则不得在已有诊断的报告上再报"（撞车测试，直接用 `candidate_coverage` 的 gain/collision 口径） |
| B4 复测（3h） | **保留 1.5h**：只需重跑 `blind_eval` + `coverage_report` |
| — | **新增 1h**：查 `mod.client-class-on-server` 为何漏掉 `net.minecraft.client.*` 写法（修规则，不是加规则） |
| 合计 | **12h → 5h**，省下 7h 移到 W3（真实 jar 取证）与 W5（发布前指标重生成） |

## 被否掉的怀疑（记录，不擦掉）

我原先怀疑"1.09 份/规则 是精确签名聚类的产物，粗聚类会发现长尾没那么长"。**这个怀疑被
本次测量否掉了**：抹掉消息里的所有可变部分后重新聚类，106 簇 / 101 单例 / 1.10 份每规则，
与原文几乎一致。怀疑成立的只有"`kind` 这一档"——而它成立的原因是丢掉了判据需要的信息。

教训与今早那条一致：**"看着像聚类问题"和"是聚类问题"之间差一次测量**。这次测量的价值
不是发现了新机会，而是把"要不要再写 20 条规则"这个反复出现的争论一次性关掉。

## 不做

- 不为 117 份长尾逐条写规则（0.44pp/条，且最大簇不是故障）。
- 不写通用 `missing-class`（30 次撞车，24 次与 `mod.coremod-missing` 重复）。
- 不把"手动触发调试崩溃"计入诊断率改进；已有草稿保持 `draft`，是否启用由发布口径决定。
