# Minecraft Reliability Intelligence Platform — 愿景与路线

> 中文：**Minecraft 模组生态可靠性平台**
>
> 这是项目的北极星文档。`mc-crash-doctor` 不是终点，而是整个生态里的
> **诊断引擎核心（L0）**。本文档定义"要变成什么"，`ROADMAP.md` 定义
> "现在做什么、按什么顺序"。两者冲突时，以 ROADMAP 的近期步骤为准，
> 以本文档的长期方向为准。
>
> 状态数字核实于 2026-09-23。

---

## 一、总体愿景

从"分析一份崩溃日志"升级为覆盖 Minecraft 模组生态**完整生命周期**的可靠性平台：

```text
开发模组
   ↓
构建整合包 ──→ 兼容性检查 ──→ 发布前体检
   ↓
启动服务器 ──→ 启动失败诊断
   ↓
运行服务器 ──→ 日志监控 / 崩溃检测 / 性能预警
   ↓
发生事故 ──→ 根因分析 / 模组归因 / 修复建议
   ↓
问题沉淀 ──→ 知识库 / 兼容关系图 / 社区规则
```

最终要回答的不是：

> "这次为什么崩了？"

而是：

> "这个整合包目前有哪些可靠性风险？哪个模组和哪个版本组合最危险？
> 如果发生问题，应该如何修复、回滚和验证？"

**护城河判断**：规则会被抄，解析器会被重写，但**数据飞轮不会**——
语料 × 弱监督标注 × 归因结果 × 兼容关系图 × 维护者确认，越用越厚，
这是别人无法快速复制的资产。所以本项目从第一天起就把"数据"当一等公民。

---

## 二、六条产品线

### 1. Crash Doctor — 崩溃诊断引擎 【现状：L0 已有】

现有项目的核心。

- **能力**：分析 crash report / 服务端日志；识别根因；定位疑似模组；
  判断是模组 / 加载器 / 环境 / 数据问题；输出证据、置信度、修复建议。
- **形态**：Python 库 · CLI · Web · GitHub Action · API · Discord/Matrix/QQ Bot。
- **现状**（2026-09-23）：库 + CLI 完成；41 条规则；445 测试绿；
  平台识别 201/201；归因接入游戏官方 `Suspected Mods`（top-1 一致率 90%）；
  Web 骨架已写但**端到端未验证**；Action / Bot 未做。

### 2. Pack Doctor — 整合包健康检查 【第一个"做大"的方向】

用户上传/扫描整合包，**事故前**发现问题：

- 重复模组 · 缺失前置 · Forge/Fabric/NeoForge 混用 · MC 版本不匹配
- Java 版本不兼容 · 客户端模组误装服务端（及反向）· 已知崩溃组合
- 高风险模组版本 · 内存配置不足 · 模组数量/启动参数异常 · Mixin 冲突
- 过期/弃用依赖 · 许可证与分发问题

输入：`mods/ config/ latest.log crash-reports/ manifest.json modlist.html server.properties JVM 参数`

输出（示例）：

```text
严重问题：3   警告：11   建议升级：8   已知兼容风险：5
预计启动风险：中等   预计内存压力：高
```

> **工程意见（Hermes 注）**：慎用"健康分数 72/100"这种单一数字。未标定的
> 分数看着权威、实则误导（凭什么 72 不是 68？）。**先输出可追溯的具体
> findings（每条带证据+置信度+来源），分数等有足够标注数据后再标定引入**，
> 且必须公开算法。这与北极星"错误甩锅率"一致——宁可不给分，不给假精确的分。

### 3. Server Doctor — 服务端持续监控

本地常驻 Agent，不只分析一次：

```text
Minecraft Server → Agent（本地解析/脱敏/聚合）→ 控制台 / Web / Discord / GitHub
```

- 实时识别异常日志 · 重复崩溃 · 崩溃频率 · 内存缓增 · Watchdog 风险
- TPS 下降前兆 · 玩家触发的固定崩溃 · 模组更新导致的回归
- 自动事故报告 · 自动重启/回滚/通知

**隐私原则**（不可妥协）：默认本地处理；默认不上传完整日志；只上传用户
明确允许的脱敏事件；支持完全离线。

### 4. Mod Doctor — 模组作者质量平台

面向模组作者，从"玩家工具"进入"开发基础设施"：

- 接收 GitHub Issue 崩溃报告 · 自动分类 · 判断是否属于自身模组
- 识别加载器/第三方冲突 · 关联历史 Issue · 生成维护者回复草稿
- 统计某版本引入的崩溃 · 跨 MC/Loader 版本对比 · CI 中回归测试已知崩溃样本

```text
版本 1.8.2 相比 1.8.1：
  新增：3 个 NeoForge 启动失败 · 2 个客户端渲染崩溃
  消失：5 个旧版配置问题
  回归风险：高
```

> **现状优势（Hermes 注）**：这条线的数据管道**已经存在**——
> `tools/harvest_corpus.py` 已在爬 12 个模组仓库的 issue、抓维护者标签
> （`confirmed` / `Not <Mod>` / `Loader Issue`）。Mod Doctor 不是从零开始，
> 是把已有采集器升级成"持续监控 + 回归对比"。

### 5. Compatibility Graph — 模组兼容关系图 【长期护城河】

多维关系：

```text
Minecraft 1.20.1
   ├── Forge 47.2.20
   │      ├── Mekanism 10.4.5
   │      ├── JEI 15.2
   │      └── Create 0.5.1
   └── Java 21
```

关系类型：可用 · 已知冲突 · 缺前置 · 版本不兼容 · 仅客户端 · 仅服务端 ·
已知性能问题 · 已知崩溃 · 维护者已确认 · 社区推测 · 未验证。

数据来源（不止静态依赖声明）：crash report · GitHub Issue · Modrinth/CurseForge
元数据 · 用户反馈 · CI 测试 · 维护者确认 · 版本变更记录 · 真实整合包。

最终能回答：

> "Create 0.5.1 + 某版本 Sodium + 某版本 Oculus + 某版本 Forge 组合是否有已知风险？"

> **这是整个平台最有长期价值、也最难被复制的部分。关键前置：它吃的是
> 结构化数据。所以 §四的数据模型必须"现在就按图的需求设计"，哪怕图产品
> 在第二阶段才做——否则积累了两年非结构化数据， retrofit 成本极高。**

### 6. Reliability Hub — 社区与知识平台

公开知识网络：已知崩溃案例 · 模组版本兼容性 · Loader 问题 · Java 环境问题 ·
高风险配置 · 解决方案 · 维护者确认 · 规则包 · 测试样本 · 版本变化记录。

**每条结论必须带状态**（对抗"把猜测伪装成事实"）：

```text
事实：     日志中出现 NoSuchMethodError
推断：     可能是 A 模组与 B 模组版本不兼容
置信度：   0.78
来源：     15 个真实报告 · 3 个维护者确认 · 2 个回归测试
状态：     已验证
```

---

## 三、目标技术结构（演进终点，非现在形态）

```text
mc-reliability-platform/
├─ packages/
│  ├─ mcd-core/           # 核心数据模型、诊断接口
│  ├─ mcd-parser/         # 日志和 crash report 解析
│  ├─ mcd-attribution/    # 模组归因
│  ├─ mcd-rules/          # YAML 规则引擎
│  ├─ mcd-evidence/       # 证据链和置信度
│  ├─ mcd-compatibility/  # 兼容关系查询
│  ├─ mcd-remediation/    # 修复计划和回滚建议
│  ├─ mcd-redaction/      # 隐私脱敏
│  └─ mcd-schema/         # JSON / API / 报告协议
├─ apps/
│  ├─ cli/  web-studio/  desktop/  github-action/  discord-bot/  server-agent/
├─ services/
│  ├─ diagnosis-api/  corpus-ingest/  rule-registry/
│  ├─ compatibility-api/  issue-linker/  notification-service/
├─ data/
│  ├─ schemas/  public-corpus/  private-corpus/  benchmarks/
│  ├─ compatibility/  provenance/
├─ infra/  docker/  github-actions/  pages/  deployment/
├─ docs/   architecture/  rule-authoring/  privacy/  api/  contributor-guide/
└─ tests/  parser/  attribution/  rules/  compatibility/  benchmarks/  e2e/
```

> **铁律（用户原话 + Hermes 强化）**：这是**目标结构，不是现在立即拆成
> 几十个包**。现在保持**单仓库、单 Python 核心（`mcd/`）**，只把模块边界
> 划清楚。**拆分触发条件**（满足才拆，否则不拆）：
> ① CLI / Web / Action / Agent 中有 ≥2 个需要独立发版节奏；
> ② 出现非 Python 消费者（如 Action 要打包成独立 Docker 镜像）；
> ③ 单次 import `mcd` 的依赖重到影响 CLI 冷启动。
> 在那之前，拆包只会增加维护成本、拖慢出活。

---

## 四、核心数据模型（现在就要按此设计）

> **为什么放在这么靠前**：兼容关系图（产品线 5）和 Hub（产品线 6）吃的
> 都是结构化数据。数据模型晚定 = 未来 retrofit 已积累的数据 = 极痛。
> 所以现在即使只做 Crash Doctor，也要让它的输出**就是** Incident schema。

### 1. Incident — 一次事故

```text
Incident
├── source · timestamp · environment
├── platform · minecraft_version · java_version · loader
├── mods[] · exception_chain[] · stack_frames[]
├── root_cause · suspects[] · findings[] · evidence[]
├── confidence · remediation
```

> 现状映射：`mcd/model.py` 的 `CrashReport` + `Finding` + `triage.TriageResult`
> 已覆盖大部分。**缺**：稳定的 JSON Schema 版本号、`remediation` 结构化、
> `provenance`（证据来源追溯）。这是第一阶段要补的。

### 2. ModArtifact — 一个具体模组版本

```text
ModArtifact
├── mod_id · display_name · version · loader
├── minecraft_versions[] · jar_hash · source_url · metadata
```

> 现状：`model.Mod` 只有 file/name/modid/version/status。**缺** jar_hash、
> source_url、loader、minecraft_versions——这些是兼容图的节点键，第二阶段
> 接 Modrinth/CurseForge 元数据时补。

### 3. CompatibilityClaim — 一条兼容性结论

```text
CompatibilityClaim
├── subject · object · relation · confidence
├── evidence_count · source_reports[] · maintainer_verdict
├── first_seen · last_seen · status
```

> 现状：**完全未实现**。但采集器已经在攒它的原料（归因结果 + 维护者标签）。
> 第一阶段先把"每次诊断产出的 suspect 对"以可追加的 JSONL 落盘，就是在
> 无声地为这张图积累边——不需要现在建图服务，只需要现在**开始记录**。

### 4. Rule — 一条诊断规则（带生命周期）

```text
Rule
├── rule_id · category · conditions · explanation · remediation
├── evidence_requirements · provenance · fixture_ids
├── false_positive_guards · lifecycle_status
```

生命周期：`draft → experimental → verified → stable → deprecated → retired`

> 现状：`rules/engine.py` 的 `Rule` 有 id/title/severity/when/explanation/
> fixes/tags/confidence/suspects_from。**缺** lifecycle_status、provenance
> （绑定 fixture_ids，现在靠 test_gaps.py 外部维护）、false_positive_guards。
> 把"钉桩"从测试文件**内联进规则元数据**，是第一阶段的低成本高价值动作。

---

## 五、AI 的位置（边界明确）

AI **可以用，但不能放在核心判定位置**：

```text
确定性解析 → 规则/证据引擎 → 结构化诊断结果 → AI 解释层 → 自然语言报告
```

**AI 可以**：把结构化结果翻译成易懂解释 · 总结多次事故 · 对比两个版本 ·
生成 Issue 回复 · 按已有证据组织修复步骤 · 检索历史相似案例。

**AI 绝不能**：凭空判断哪个模组有罪 · 无证据时生成规则 · 修改用户整合包 ·
把"可能"改写成"确定" · 上传用户完整日志去训练模型。

> **核心诊断必须能在没有 AI、没有网络的情况下运行。** 这是底线，也是与
> "套壳 AI 工具"的本质区别——我们的判定是可复现、可测试、可追溯的确定性
> 引擎，AI 只是最后一层可选的"翻译"。

---

## 六、开源与商业结构（三层）

| 层 | 面向 | 内容 |
|---|---|---|
| **Community**（全开源） | 所有人 | CLI · Python API · 基础规则 · 本地网页 · 脱敏工具 · 基础语料 · 离线诊断 |
| **Maintainer** | 模组/整合包作者 | GitHub Action · 私有规则包 · 批量诊断 · Issue 自动回复 · 团队报告 · 历史趋势 · 私有语料 · 版本回归分析 |
| **Hosted/Enterprise**（远期） | 组织 | 多服务器管理 · 组织级兼容库 · 私有部署 · 高级 API · 告警 · 质量报表 · 长期事故分析 · 私有知识库 |

> **不要现在做 SaaS 后端。** 先证明本地引擎、数据、用户场景成立。
> 商业层是"如果 Community 版被广泛依赖"之后的自然延伸，不是起点。
> 许可：核心 MIT 不变；未来 Maintainer/Hosted 层可另立目录用不同许可。

---

## 七、分阶段路线（年级别）

> 详细到"这个季度做什么"的可执行步骤见 `ROADMAP.md`。这里只定方向。

### 第一阶段：基础引擎（2026-09 ~ 2027-03）

稳定 CLI · 稳定 JSON Schema · 浏览器版可用 · GitHub Action 可用 ·
盲测系统 · 规则/语料贡献机制 · 第一个可信诊断基线。

> **核心成果不是功能数量，而是：别人可以依赖诊断结果。**

### 第二阶段：整合包与模组质量平台（2027-04 ~ 2027-12）

Pack Doctor · Mod Doctor · 兼容性数据库 · Issue 自动分析 · 版本回归检测 ·
Modrinth/CurseForge 元数据接入 · 可视化兼容图 · 公开规则注册表。

> 从"单次诊断工具"变成"模组生态工具链"。

### 第三阶段：服务端可靠性平台（2028）

Server Doctor Agent · 多服务器监控 · 崩溃趋势 · 内存/Watchdog 预警 ·
自动事故报告 · Discord/Matrix 通知 · 可选远程团队控制台 · 私有部署。

> 此时才真正进入"平台"阶段。

### 第四阶段：生态基础设施（2029+）

兼容性图谱 · 模组作者质量评分 · 整合包发布前风险评估 · 社区验证系统 ·
第三方插件/API 生态 · 企业私有部署 · 规则与知识库市场。

---

## 八、当前仓库在大项目中的位置

> **L0：核心诊断引擎原型 + 语料驱动规则实验室。**

现有模块**已经对应**未来平台的底层核心，边界要固化：

```text
parser   只负责事实提取
triage   只负责候选模组归因
rules    只负责证据规则
report   只负责结果呈现
corpus   只负责数据和评测
```

之后**按需**增加（不是现在）：`compatibility/ · remediation/ · registry/ · agent/ · integrations/`

---

## 九、北极星指标

**不用"规则有多少条"衡量成功。** 用：

- 多少事故被提前发现
- 多少崩溃被正确归因
- 多少维护者减少了人工排查时间
- 多少 Issue 自动得到有效初步回复
- 多少整合包在发布前发现兼容问题
- 多少结论有可追溯证据
- **错误甩锅率有多低**

最核心的产品指标：

> **从日志出现到用户得到可信、可执行结论的平均时间。**

---

## 最终定位

不停留在"一个更好的 Minecraft 崩溃日志解析器"，而是发展成：

> **Minecraft 模组生态的诊断、兼容性、质量和运行可靠性基础设施。**

`mc-crash-doctor` 负责"事故后诊断"；Pack/Mod/Server Doctor 负责
"事故前预防、事故中监控、事故后沉淀"。这是一个可持续多年扩展的结构。

---

*本文档由用户规划、Hermes Agent（qwen3.8-max-0902）整理并加注工程意见
（标注为"Hermes 注"的段落）。愿景主体是用户的；注释是执行层的诚实补充。*
