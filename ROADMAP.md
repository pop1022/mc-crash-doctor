# ROADMAP — 可执行步骤

> `VISION.md` 回答"要变成什么"；本文档回答"**现在做什么、按什么顺序、
> 怎么算做完**"。每一步都有验收标准（acceptance），做完打勾。
>
> 原则（来自 VISION 的工程意见）：
> 1. **先固化边界，再扩功能**——不拆包，但让模块职责单一、接口稳定。
> 2. **数据模型先行**——兼容图两年后才做，但它吃的结构化数据现在就要开始落盘。
> 3. **每步都要可验证、可回滚**——门禁 445 绿是底线，不许删测试凑绿。
> 4. **出活优先于脚手架**——拒绝"永远在重构"。

状态图例：`[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成 · `[!]` 阻塞

---

## 阶段 0：收尾现有半成品（本周，最高优先）

> 理由：网页版骨架曾以"未验证"状态提交，这是"说了没做"的债务，先清掉。
> 0.1 已于 2026-09-23 完成真实浏览器验证；剩 0.2 部署、0.3 死规则清理。

- [x] **0.1 网页版端到端验证**（2026-09-23 完成）
  - 做法：本地 `python -m http.server 8765` 起服务 + headless Edge
    `--remote-debugging-port=9222` 起浏览器，`tools/verify_web_e2e.py` 通过
    CDP 驱动真实页面：等引擎 ready → 点 "Try a sample" → 读回渲染后的 DOM。
    （desktop_preview 面板与 browser_exec harness 在本机都不可用，CDP 直驱
    是可靠通道；Edge 需 `suppress_origin` 否则 WS 握手 403。）
  - 结果：**6/6 验收通过**。样本是脱敏后的真实 watchdog 报告（75 KB，
    `web/sample.js`），浏览器里渲染出 suspect 芯片 `lithium`、FATAL/ERROR
    徽章、6 条修复、4 条证据行。非逻辑模拟——是真实浏览器 DOM 读回。
  - 产物：`tools/verify_web_e2e.py`（可复跑）、`tools/make_web_sample.py`
    （生成脱敏样本，带泄漏守卫，已并入 `build_web.py`）。
- [ ] **0.2 网页版部署 GitHub Pages**（依赖 0.1）
  - 做：`.github/workflows/pages.yml`：`python tools/build_web.py` →
    `actions/upload-pages-artifact web/` → `actions/deploy-pages`。
  - 验收：`https://pop1022.github.io/mc-crash-doctor/` 可访问，贴样本出诊断。
    （部署 workflow 需要推送方对仓库有 Workflows 写权限。）
- [ ] **0.3 零触发规则清理**
  - 做：41 条里约 11 条在现有语料没响过。每条二选一：
    (a) 补合成 fixture 单测证明规则正确（推荐，tests/ 已有先例）；
    (b) 确认是死规则则删。
  - 验收：`verify_new_rules.py` 风格的脚本报告"0 条无证据规则"；每条规则
    要么有语料命中、要么有 fixture 单测。

---

## 阶段 1：基础引擎可信化（2026-09 ~ 2027-03）

> 对应 VISION 第一阶段。核心成果：**别人可以依赖诊断结果**。
> 不是加功能，是把"能用"变成"可信赖"。

### 1A. 数据模型固化（最优先，因为兼容图依赖它）

- [ ] **1A.1 Incident JSON Schema 定版**
  - 做：把 `CrashReport + Finding + TriageResult` 的 `to_dict()` 输出固化为
    带 `schema_version` 的 JSON Schema，写 `data/schemas/incident.v1.json`。
    `mcd --json` 输出必须 conform。
  - 验收：加 `tests/test_schema.py`，用 jsonschema 校验全部语料的输出；
    schema 文件入仓。
- [ ] **1A.2 兼容边落盘（为产品线 5 埋管道，现在不建图）**
  - 做：每次诊断把 `(loader, mc_version, modid, mod_version, suspect, relation)`
    以可追加 JSONL 写入 `corpus/compat-edges.jsonl`（脱敏后）。relation ∈
    {caused, suspected, co-occurred}。
  - 验收：跑一遍 harvested 语料，产出 N 条边；文件格式有 README 说明。
    **这是 VISION §四 CompatibilityClaim 的最小起点——只记录，不查询。**
- [ ] **1A.3 规则元数据内联钉桩**
  - 做：把 test_gaps.py 的"规则↔真实报告"绑定**搬进规则 YAML**
    （`provenance: {fixture: "sodium/3711", issue: ...}`），加 `lifecycle_status`
    字段（默认 `verified`）。引擎加载时校验。
  - 验收：每条规则自带 provenance；test_gaps 改为从规则元数据读钉桩，
    单一事实来源。

### 1B. 诊断可信度

- [ ] **1B.1 盲测系统**
  - 做：留出一批语料**不参与**规则编写，作为盲测集；`tools/blind_eval.py`
    报告 precision/recall（用弱监督标注当 ground truth）。
  - 验收：能输出"规则集在未见语料上的归因准确率"，作为回归基线。
- [ ] **1B.2 错误甩锅率指标**
  - 做：定义并测量"归因到错误模组"的比例（用维护者 `Not <Mod>` 标签反验）。
  - 验收：北极星指标之一有了可跑的测量脚本。

### 1C. 分发形态

- [ ] **1C.1 GitHub Action**
  - 做：`action.yml`，输入 crash 文件路径，输出诊断 comment。复用 CLI `--markdown`。
  - 验收：在本仓库自己的 issue 上跑通（dogfood）。
- [ ] **1C.2 PyPI 发布**
  - 做：`mc-crash-doctor` 上 PyPI（已有 wheel 构建）。
  - 验收：`pip install mc-crash-doctor` 可用。

---

## 阶段 2：整合包与模组质量（2027-04 ~ 2027-12）

> 对应 VISION 第二阶段。从工具变工具链。**进入条件**：阶段 1 的 Schema
> 和兼容边管道稳定运行 ≥3 个月，有真实数据积累。

- [ ] **2.1 Modrinth/CurseForge 元数据接入** → 填充 ModArtifact（jar_hash、
  source_url、minecraft_versions、loader）。
- [ ] **2.2 Pack Doctor MVP**：扫描 `mods/` + `manifest.json`，输出**具体
  findings**（重复/缺前置/混用/版本不匹配/客户端模组误装）。
  **不做健康分数**（见 VISION §2.2 工程意见），只做可追溯条目。
- [ ] **2.3 Mod Doctor**：把 `harvest_corpus.py` 升级为持续监控 + 版本回归
  对比（"1.8.2 相比 1.8.1 新增/消失哪些崩溃"）。
- [ ] **2.4 兼容关系查询**：基于 1A.2 积累的边，做 `mcd compat <modA> <modB>`
  查询（先 CLI，后可视化）。
- [ ] **2.5 规则注册表**：公开规则包发布/版本管理。

---

## 阶段 3：服务端可靠性（2028）

> 对应 VISION 第三阶段。**进入条件**：阶段 2 的兼容库有社区使用证据。

- [ ] 3.1 Server Doctor Agent（本地常驻，隐私默认本地处理）
- [ ] 3.2 崩溃趋势 / 内存 / Watchdog 预警
- [ ] 3.3 自动事故报告 + Discord/Matrix 通知
- [ ] 3.4 可选远程团队控制台

---

## 阶段 4：生态基础设施（2029+）

兼容图谱 · 作者质量评分 · 发布前风险评估 · 社区验证 · 插件/API 生态 ·
企业私有部署 · 规则市场。（详见 VISION §七第四阶段）

---

## 拆分触发器（什么时候才把 mcd/ 拆成 packages/）

> VISION §三的铁律的可执行版。**满足任一条才拆，否则保持单包**：

1. CLI / Web / Action / Agent 中 ≥2 个需要独立发版节奏；
2. 出现非 Python 消费者（如 Action 要打成独立 Docker 镜像）；
3. `import mcd` 依赖重到拖慢 CLI 冷启动（实测 >300ms）。

拆之前先做：把 `parser/triage/rules/report/corpus` 的**内部**接口写成
稳定 API（即使还在一个包里），这样未来拆分是"移动文件"而非"重写"。

---

## 当前焦点（给接手者）

> **就看这里。** 上面是全景，但你现在只需要做：

1. **阶段 0.2**：网页版部署 GitHub Pages（0.1 已验证通过，可以部署了）
2. 然后 **0.3** 零触发规则清理
3. 阶段 0 清空后，进 **1A.1**（Incident Schema）——这是兼容图的地基

每完成一步，把对应 `[ ]` 改 `[x]`，并在 CHANGELOG 记一笔。

---

*整理：Hermes Agent（qwen3.8-max-0902），2026-09-23。
愿景主体见 VISION.md（用户规划）；本文档是执行层排序，含工程判断。*
