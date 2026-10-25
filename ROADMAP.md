# ROADMAP — 可执行步骤

> `VISION.md` 回答"要变成什么"；本文档回答"**现在做什么、按什么顺序、
> 怎么算做完**"。每一步都有验收标准（acceptance），做完打勾。
>
> 原则（来自 VISION 的工程意见）：
> 1. **先固化边界，再扩功能**——不拆包，但让模块职责单一、接口稳定。
> 2. **数据模型先行**——兼容图两年后才做，但它吃的结构化数据现在就要开始落盘。
> 3. **每步都要可验证、可回滚**——门禁 756 绿是底线，不许删测试凑绿。
> 4. **出活优先于脚手架**——拒绝"永远在重构"。

状态图例：`[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成 · `[!]` 阻塞

---

## 阶段 0：收尾现有半成品（本周，最高优先）

> 理由：网页版骨架曾以"未验证"状态提交，这是"说了没做"的债务，先清掉。
> 0.1 / 0.3 / 0.4 / 0.5 均已完成（真实浏览器验证、死规则清理、P0 交互重排、
> 界面中文化）；阶段 0 只剩 **0.2 部署**，卡在仓库设置里一次性启用 Pages。

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
- [x] **0.2 网页版部署 GitHub Pages**（2026-10-25 完成）
  - 做：`.github/workflows/pages.yml` 已提交（`build_web.py` → PII 守卫 →
    `configure-pages(enablement:true)` → `upload-pages-artifact` → `deploy-pages`）。
  - **原先阻塞**：workflow 首跑在 `Configure Pages` 步骤失败——
    `Create Pages site failed: Resource not accessible by integration`。
    这是 GitHub 硬限制：GITHUB_TOKEN 即使有 `pages:write`（已确认日志里授予了），
    也**无法首次创建** Pages 站点；owner 的 fine-grained PAT 缺 Pages scope，
    `POST /pages` 也 403。两者都绕不过首次创建。
  - **解法（用户一次性操作，30 秒）**：仓库 Settings → Pages →
    Build and deployment → Source 选 **"GitHub Actions"**。**已于 2026-10-25 操作。**
    顺带修掉 `pages.yml` 里那句相反的注释——它写着"`enablement: true` 不需要
    手动点 Settings"，与上面的实测矛盾，属于注释在骗人。
  - 验收（**已读回验证，非用户转述**）：`https://pop1022.github.io/mc-crash-doctor/`
    返回真实页面（标题 `mc-crash-doctor — 在浏览器里诊断 Minecraft 崩溃`，
    含「崩溃报告或日志」输入框、「用示例试试」、「选择文件…」、分阶段启动提示），
    不是 404 或 Pages 错误页。
- [x] **0.3 零触发规则清理**（2026-09-23 完成）
  - 取证：审计 41 条规则 × 661 文件语料，零触发实为 **4 条**（非旧记的 11）：
    `oom.save-time`、`oom.gc-overhead`、`disk.space`、`native.gl`——全是合法
    失败模式，只是语料恰好无样本（情况 b，非死规则）。
  - 做：4 份合成 fixture（`tests/fixtures/synthetic/`，明确标 SYNTHETIC，
    仿真实报告格式）+ `tests/test_rule_fixtures.py`（7 测试）逐条证明触发。
  - **顺带修真 bug**：`native.gl` 的 `exception` 误含 `mixin.InjectionError`
    （复制粘贴），会把 mixin 注入失败误判成显卡驱动问题。已删，并加反向断言
    `test_native_gl_does_not_fire_on_mixin_injection` 钉死。
  - 验收：7/7 测试过；零触发规则数 4 → 0（每条要么语料命中、要么 fixture 证明）。
- [x] **0.4 网页版交互重排（P0 UX，2026-10-22 完成）**
  - 问题：结果区按"发现顺序"堆卡片，用户最需要的"什么坏了 + 怎么办"被环境
    块压在最下面；输入只支持粘贴；加载期是空白等待；状态与错误无声。
  - 做（`web/index.html` + `web/app.js`，引擎/CLI/Action 零改动）：
    ① **verdict 优先**——根因做标题、suspect 芯片+置信度、why 依据、前两条
    修复、动作行（复制修复/复制诊断/去开 issue），环境折叠进 `<details>`；
    ② **三入口**——粘贴 / 文件选择（`.txt/.log/.text`，8 MB 上限）/ 拖放；
    ③ **分阶段启动**（runtime → engine → ready）带逐步状态与失败重试；
    ④ **live status + 焦点交接**（诊断落定时焦点落到 verdict 标题）；
    ⑤ **复制有回执**（clipboard → execCommand 兜底 → `.sr-only` 播报）；
    ⑥ **无障碍**：真 `<label for>`、`:focus-visible` 2px 环、44px 触控、
    证据行 `overflow-wrap:anywhere`、`prefers-reduced-motion` 分流。
  - 守门：空输入/裸链接拦截并说明，散文只警告不拦截（乱粘贴也不该被无声吞掉）；
    运行中禁用全部输入。诊断文档不变——同一 `build_incident()`，浏览器与 CLI
    仍产出逐字节一致的 `schema_version 1.0`。
  - 验收：`tools/verify_web_e2e.py` 从 7 条扩到 **19/19 PASS**，
    `RESULT: VERIFIED`，**页面错误 0**（顺带修掉每次加载都 404 的 favicon）。
- [x] **0.5 网页版中文化 + 双语切换（2026-10-21 完成）**
  - 目标：界面默认中文（面向中文 MC 服主/玩家），英文一键可切，引擎与输出不变。
  - 做：`web/app.js` 建 `I18N` 字典（zh/en 各 80 键、键集一致），
    `web/index.html` 内联中文并用 `data-i18n` / `data-i18n-html` /
    `data-i18n-placeholder` 挂钩——脚本还没跑就已经是中文（首屏不闪英文）；
    切换写入 `localStorage`，同步 `<html lang>` / `<title>` / meta description。
  - 两个容易做错的地方：**切换要能重绘已经渲染出来的结果**（标签、按钮、
    环境块都用同一份 `LAST` 文档重渲染，不重新诊断、不丢数据）；**已弹出的提示
    要能在新语言下重绘**（提示只存翻译 key + 变量，绝不存渲染后的 HTML）。
    切换时刻意不移动焦点，避免把用户从开关上拽走。
  - 排版：字体栈补 PingFang SC / 微软雅黑 / Noto Sans CJK，正文行高 1.55→1.62；
    全大写与字距只对 `html[lang="en"]` 生效（中文全大写无意义，字距只会发虚）。
  - 严重级别徽章也本地化（致命/错误/警告/提示/信息），因此 E2E 两种写法都接受。
  - 验收：`tools/verify_web_e2e.py` 19 → **30/30 PASS**，`RESULT: VERIFIED`，
    **页面错误 0**；含「默认 zh-CN」「切 EN 后提示与状态行就地变英文」
    「切回中文重绘同一份诊断」「无未翻译节点」「两套字典键集相同」。
  - **截图复核顺带揪出 0.4 的一个假绿**：`hidden` 属性从来没真的隐藏过元素
    （`.progress{display:flex}`、`button{display:inline-flex}` 覆盖了 UA 的
    `[hidden]{display:none}`），启动进度条一直留在页面上、空输入时「清空」
    是个点了没反应的可见控件。0.4 的断言查的是 `el.hidden` 属性，所以是绿的。
    已加 `[hidden]{display:none!important}`，断言改为查
    `getComputedStyle(...).display`，并补了「空 prompt 时清空按钮不可见」
    三条 → 现 **34/34 PASS**。教训：**验收要查渲染结果，不要查状态标记**。
  - 明确不做的：引擎产出的**发现标题/修复步骤**仍是英文——它们是 YAML 规则
    数据，被 `tests/test_e2e.py` 与 Incident schema 钉住，翻译需要 schema 级
    改动（候选：给规则加 `title_zh`/`fixes_zh` 可选字段，schema 升 1.1）。
- [x] **0.6 代码库审计与清理（2026-10-21 完成）**
  - 方法：pyflakes（未使用导入/未定义名）+ vulture（死符号，80% 置信度）
    + 自写 AST 近似重复检测（118 个函数两两比对，阈值 82%，结果 0 对——
    说明跨模块没有复制粘贴，重复都在函数内部）+ 全仓 grep 逐个确认引用。
    静态工具只作线索，**每条都 grep 确认零引用后才删**。
  - 删文件：`build/lib/mcd/**`（15 个模块的第二份过期副本）、
    `mc_crash_doctor.egg-info/`、全部 `__pycache__/`、
    `docs/demo-*.txt`（无引用且内容已过期的 CLI 转储）。
  - 删死符号：`NEOFORGE_RE`、`LOC_RE`、`MODLAUNCHER_RE`、`_unit_to_bytes`、
    `n_stackframes`、`_fetch_url`、`MemoryInfo.is_complete`/`utilisation`、
    `CrashReport.find_section`/`to_dict`/`to_json`、
    `_best()` 的 `order` 参数与 `_ORDER_*`（废弃设计的残留）。
  - 消重：`extract.py` 三个抓取循环 → `_PASTE_HOSTS` 表驱动；
    `_fetch`/`fetch_log` 共用 `_http_get`；编码回退抽 `read_report_text`；
    `render.py` 三处平台串 → `_fmt_platform`；`cli.py` 两处 `--exit-code` →
    `_worst`/`_exit`；版本号三处 → `VERSION = __version__`。
  - 修 bug（清理过程中暴露的）：**提交的 web wheel 已与源码脱节**（缺
    `mcd/action.py`，浏览器跑的是旧代码，而所有测试仍绿）→ 重建 + 新增
    `tests/test_web_bundle.py` 漂移守卫；**Action 与 CLI 的编码回退不一致**
    （cp1252 报告在 Action 侧被 `errors="replace"` 换成 U+FFFD，导致规则失配）；
    `license = {text="MIT"}` 弃用（2027-02-18 后构建失败）→ 改 PEP 639 写法。
  - 验收：pyflakes **0 项**，vulture(80%) **0 项**，pytest **567 passed**
    （563 + 4 条 bundle 守卫），浏览器端到端 **34/34 PASS**，五道门禁全绿。

---

## 阶段 1：基础引擎可信化（2026-09 ~ 2027-03）

> 对应 VISION 第一阶段。核心成果：**别人可以依赖诊断结果**。
> 不是加功能，是把"能用"变成"可信赖"。

### 1A. 数据模型固化（最优先，因为兼容图依赖它）

- [x] **1A.1 Incident JSON Schema 定版**（2026-09-23 完成）
  - 做：`mcd/report/render.py` 抽出 `build_incident()` 单一事实来源 +
    `SCHEMA_VERSION="1.0"`；schema 写 `data/schemas/incident.v1.json`
    （draft 2020-12，严格模式 `additionalProperties:false` 顶层）。
    **顺手消灭了一个真 drift**：web/app.js 曾内联拼 doc（已缺
    `schema_version`），现改为共用 `build_incident`，浏览器输出与 CLI
    逐字节同源，并重跑浏览器 e2e 验证（7/7 过，含 schema_version 检查）。
  - 验收：`tests/test_schema.py`（78 测试：地面真值+合成 fixture 全量、
    aternos 抽样 25、harvested 抽样 40、空输入边界）全过；
    jsonschema 进 `[test]` extra + CI。门禁 530 passed。
- [x] **1A.2 兼容边落盘**（2026-09-23 完成，方案 A：离线批量）
  - 做：`tools/build_compat_edges.py` 扫 454 份 harvested 语料，聚合为
    VISION §4.3 CompatibilityClaim 形状（按 subject/object/relation/loader/
    mc_version 去重），写 `corpus/compat-edges.jsonl` + 格式文档
    `corpus/COMPAT_EDGES.md`。**没有**照搬"每模组每报告一行"的天真方案
    （那会产生 1.1 万行低信号原始边且无聚合）——聚合后 9895 条声明：
    caused 82 / suspected 92 / co_occurred 9721，3531 条带维护者 verdict
    （弱监督标注 join 自 index.jsonl）。诊断保持纯函数，边由离线工具生成。
  - 验收：键唯一性校验过；caused 样例可解释（fabric-registry-sync-v0 x9、
    curios x7、jade x5）；co_occurred 明确标注为 presence≠guilt 弱信号。
- [x] **1A.3 规则元数据内联钉桩**（2026-09-23 完成）
  - 做：`Rule` 加 `provenance`（fixtures + expect_suspects + notes）和
    `lifecycle_status`（draft→experimental→verified→stable→deprecated→retired，
    `from_dict` 拒非法值）。`tools/stamp_provenance.py` 扫全语料（67s）把
    每条规则的真实触发证据 + 手写钉桩盖进 YAML（文本级插入，保留全部注释；
    幂等可重跑）。`test_gaps.py` 改为**从 YAML provenance 读钉桩**（删掉硬编码
    PINS dict，24 条钉桩单一来源），加"空钉桩=假绿"守卫。
  - 结果：41 条全部有 fixtures；**37 verified（真实语料证据）+ 4 experimental**
    （oom.save-time/gc-overhead/disk.space/native.gl——仅合成 fixture 证明，
    等真实报告触发自动升级）。
  - 验收：新增 `tests/test_rule_metadata.py`（9 测试：每条有 fixtures、
    lifecycle 合法、verified 必有真实证据、expect_suspects 键自洽、
    from_dict 拒坏值）；CONTRIBUTING "Adding a rule" 更新为 provenance 流程。

### 1B. 诊断可信度

- [x] **1B.1 盲测系统**（2026-09-24 完成）
  - 做：`tools/blind_eval.py`——确定性 dev/blind 划分（规则 provenance 钉桩
    强制进 dev 集，"规则不能在自己催生它的报告上算盲测"；其余按
    sha256(repo/issue) 哈希对半分）。盲集 218 份：**诊断率 65%**、
    root cause 提取 100%、零解析错误；dev 集 69%——两者在噪声范围内，
    **无显著过拟合**。结果报告 `corpus/BLIND_EVAL.md` + 机读
    `corpus/blind-eval.json`（脱敏检查过，可提交）。
  - 验收：`tests/test_blind_eval.py` 4 测试（划分确定性/无重叠/无丢失、
    钉桩不漏进盲集、verdict 方向常量自洽、真实样本方向感知评分）。
- [x] **1B.2 错误甩锅率**（2026-09-24 完成，与 1B.1 同工具）
  - 做：**方向感知评分**（第一版单桶评分把 root_cause_elsewhere 的正确
    外部归因误判为甩锅——已修正）：`bug_in_this_mod` 应命中仓库模组、
    `root_cause_elsewhere` 应命中**其他**模组、known_issue/outdated 方向
    不明只报告不计分。结果：**甩锅率 1/7 = 14%**。
  - 唯一甩锅案例 Mekanism/8455 已手工取证并写成文档化边界：栈帧全是
    mekanism.api（归因无过错），但维护者标签 `Not Mekanism`+`interaction`
    ——真因是 Sinytra Connector 兼容层。**栈帧归因看不见字节码级模组交互**，
    这是方法固有极限，如实记录于 BLIND_EVAL.md，并钉进测试
    （未来若学会识别 Connector，改动必须是显式的）。
  - 诚实标注：可计分样本仅 7 份，14% 置信区间很宽——是"找到并记录了
    恰好一种失败模式"，不是稳定统计量。

### 1C. 分发形态

- [x] **1C.1 GitHub Action**（2026-10-25 dogfood 通过）
  - 做：仓库根 `action.yml`（composite：装包 → 跑 `python -m mcd.action`），
    glue 层 `mcd/action.py`（stdlib only），dogfood workflow
    `.github/workflows/diagnose-issue.yml`（issue opened/edited/labeled 触发）。
  - 关键设计：**幂等评论**（正文含隐藏 marker，重跑 PATCH 同一条而不是再发一条，
    否则每个 typo 编辑都刷一条旧诊断）；**闲聊不回复**（抽不出报告就
    `found=false` 静默退出）；**评论失败不影响诊断**（markdown 已进日志与
    step summary，token 缺 `issues: write` 只告警不红）。
  - 输入优先级：`path` > `url` > issue（event payload 优先，必要时回 API 取 body）；
    复用既有 `mcd/extract.py` 抽文本，`cli.diagnose()` 同一套管线，
    `fetch_log()` 从 CLI 提出到 `extract.py` 共用。
  - 验收：`tests/test_action.py`（20 测试）——本地假 GitHub API 跑通
    "event → 诊断 → 建评论 → 重跑更新同一条 → outputs"，夹具为真实
    watchdog 报告（2 findings，top suspect `lithium` 97%）。
  - **顺带修真 bug**：`MCLOGS_RE` 要求两段路径，README 里的
    `--url https://mclo.gs/<id>` 实际取到的是 HTML 页而不是日志；已改为
    `mclogs_id()` 同时接受单段分享链接 / 旧两段式 / raw API 形式，并用
    4 种链接形态的用例钉死。
  - **dogfood 第一轮（2026-10-25，issue #1）**：贴了一份真实 1.20.1 Forge 服务端
    OOM 报告（26.6 万字符里截出的 62,294 字符版本）。工作流 13 秒后自动回帖，
    评论来自 `github-actions[bot]`，首行是隐藏 marker `<!-- mc-crash-doctor:diagnosis -->`。
    内容含环境表（forge 47.4.16 / MC 1.20.1 / Java 21 / heap 826 of 2048 MiB /
    266 模组）、2 条发现（worst: fatal）、top suspect `harium` 54%。
    **归因链在真实 issue 上跑通了**：第二 suspect `usefastercollection` 39% 的证据
    是 `frame #2 method modify$bah000$useFasterCollection is generated by
    'usefastercollection'`——正是 1E.4 新增的 mixin 方法名信号。
  - dogfood **同时暴露出一个真缺陷**（语料永远测不出来的那种）：
    `crash.runtime-mod` 对 OOM 报告也触发，于是给出一条"Harium crashed at runtime"
    + "runtime NPEs/ISEs like this are usually fixed quickly" 的建议，而该报告
    里既没有 NPE 也没有 ISE。实测：harvested 454 份 **OOM=0**（与 1D.4 的
    `oom` 空桶独立吻合）→ 语料上 BOTH=0；ground-truth 6 份 OOM=4、
    `crash.runtime-mod`=4、**BOTH=2**。根因是 `when.exception` 的
    `java\.lang\.[\w.]*(?:Exception|Error)` 把 `OutOfMemoryError` 一并收进来，
    而引擎目前**没有取反条件**（只有 `not_has_mod`）。
    → **已修**：引擎新增 `not_exception`（与 `not_has_mod` 对称），
    `crash.runtime-mod` 加 `not_exception: ["java\\.lang\\.OutOfMemoryError"]`。
    代价实测为零：harvested `crash.runtime-mod` 188 → **188**（不变），
    ground-truth 4 → 2，OOM 误判 2 → **0**。顺带把引擎真正认识的 `when` 键
    收成 `WHEN_KEYS`，并加 `test_every_when_key_is_honoured_by_the_engine`
    ——此前写错键名会让规则静默失效且不报错，属于 1E.5 同型的"不抛异常的缺陷"。
    web wheel 被 `source_digest` 守卫抓到陈旧并重建（守卫起作用了）。
  - **幂等复验通过（2026-10-25 17:31）**：编辑 issue #1 正文保存后，工作流在
    `issues: edited` 上重跑。读回 API：评论总数仍是 **1**，comment id 仍是
    `6395940395`，`created_at` 未变，`updated_at` 由 `09:27:14Z` 变为
    `09:31:27Z`——即 PATCH 了同一条，没有新增第二条。这是"每个 typo 编辑都刷
    一条旧诊断"的反面，也是本项最后一条验收。
- [ ] **1C.2 PyPI 发布**（**前置：1E 完成**）
  - 做：`mc-crash-doctor` 上 PyPI（已有 wheel 构建）。
  - 验收：`pip install mc-crash-doctor` 可用。
  - **为什么前置 1E**：发布意味着外部用户开始引用我们的结论。没有区间估计就
    对外说"甩锅率 14%"，等于承诺一个统计上站不住的数字（见 `docs/RESEARCH.md`
    J4 与 §3.4）。
  - 状态（2026-10-25）：**代码侧已就绪，只差 PyPI 网页端一次性配置**。
    `.github/workflows/publish.yml` 已写好并通过 YAML 解析校验：tag `v*` 触发、
    OIDC Trusted Publishing（仓库里没有任何 token）、发布前跑与 tests.yml 相同的
    四道门禁、校验 `tag == mcd.__version__`（本地已验证 v0.1.0 通过 / v0.2.0
    失败）、校验产物含 3 个规则包且无字节码。
    还缺的一步（只有你能做，约 5 分钟）：PyPI → Your projects → Publishing →
    Add a pending publisher，五个字段必须与 `publish.yml` 顶部注释里的完全一致
    （`mc-crash-doctor` / `pop1022` / `mc-crash-doctor` / `publish.yml` / `pypi`）。
    然后 `git tag v0.1.0 && git push origin v0.1.0` 即发布。
    **诚实标注：这个 workflow 从未运行过**（还没有 tag），`workflow_dispatch`
    默认 `dry_run=true`，所以误触也不会传包。

### 1D. 证据分级与声明式兼容边（依据：RESEARCH J1 / C5）

> 为什么提前：`docs/RESEARCH.md` §3.5A 证实生态里有**机器可读的声明式负向边**
> （`fabric.mod.json` 的 `conflicts`/`breaks`、`mods.toml` 的
> `type=incompatible`、Modrinth 的 `dependency_type=incompatible`）。
> 这是作者本人的先验声明，比 9721 条共现边可靠一个量级。原 2.1 把它当
> "Pack Doctor 的下游"，方向反了——它是边的**上游来源**。

- [x] **1D.0 现状量化**（2026-10-21 完成）
  - 做：`tools/audit_modrinth_mapping.py`——从 `corpus/index.jsonl` 抽 765 个
    去重模组标识（`jars` + `mixin_configs`），按 sha256 序确定性抽 120 个，
    保守匹配（只接受精确 slug 或归一化后完全相等的标题，**不做模糊接受**）
    到 Modrinth；另抽 25 个项目探版本级依赖声明。~300 请求，全部落盘缓存
    （`data/modrinth-cache/`，gitignored）。
  - 结果（`corpus/MODRINTH_MAPPING.md`）：匹配率 **45.8%**（55/120）；
    `incompatible` 仅占声明依赖 **5/71 = 7%**；25 个项目里只 3 个声明过
    不兼容；因果边 subject 可解析 28/60。
  - **两个口径修正（都保留原始数字）**：① 分母剔除 25 个运行时库
    （guava/bus/mixin）与加载器产物（fmlloader，单它出现在 60 份报告）——
    它们不是模组，永远不会解析；剔除前 36.7%，剔除后 45.8%，
    `--no-exclude-libs` 可复现前者。② 发现 `JAR_RE` 抓的是**栈帧后缀**
    （`~[guava-32.1.2-jre.jar:?]`），而 1.20+ 报告已无 `-- Mod List --` 段，
    模组与库同通道——这是采集缺陷，不是生态事实。
  - **门槛判定：数字过线（45.8% ≥ 40%），但 95% 区间约 37%–55% 跨过门槛，
    所以这个"通过"不能单独支撑决策。** 结论见 1D.2。
- [x] **1D.1 jar 清单解析器**（2026-10-21 完成）
  - 做：`mcd/metadata/manifest.py`——读 `fabric.mod.json` / `quilt.mod.json` /
    `META-INF/mods.toml` / `META-INF/neoforge.mods.toml` → 统一 `ModManifest`。
    四种加载器三套词汇归一到 `required` / `optional` / `incompatible`，
    并用 `hard` 区分 Fabric 的 `conflicts`（警告）与 `breaks`（拒绝启动）。
    纯标准库；Python 3.9/3.10 无 `tomllib`，自带受限 TOML 子集解析器。
  - 不做：不解压 class、不跑字节码、不验签名、不处理嵌套 jar、不判版本区间
    是否满足（区间原样保留，语义归 2.2）。
  - 验收：`tests/test_manifest.py` **28 测试**，覆盖四种格式、多 mod jar、
    畸形 jar、非 zip、BOM、`#` 在字符串内、多行数组、以及
    **子集解析器与 `tomllib` 逐结构相等**（不是假定，是断言）。
  - 已知缺口（如实记）：夹具是按文档转写的，不是 20 个真实 jar。下载第三方
    二进制不在自动测试范围内，真实 `mods/` 目录验证等有人指路径时再做。
  - 顺带：新增模块触发 `tests/test_web_bundle.py` 的漂移守卫（如预期变红），
    已重建 web wheel 并清理 `build/`、`egg-info` 残留。
- [ ] **1D.2 Modrinth 元数据抓取（已重新定义，不再是阶段 1 优先项）**
  - **原计划作废**：原本假设"声明式负向边可作兼容图骨架"。实测 `incompatible`
    只占声明依赖 7%（5/71），25 个项目里 3 个声明过——**撑不起骨架**。
  - **新用途**：① Pack Doctor（2.2）的**正向依赖图 + 版本区间**来源
    （`required`/`optional` 占 64/71）② 兼容图的**确认层**
    （co-occurrence 出候选 → 声明式边确认或否决），不是发现层。
  - **为什么降级**：匹配率 45.8% 意味着**半个整合包不可见**。对 Pack Doctor
    这是硬约束——依赖检查会对一半模组静默跳过，而**静默跳过比报错更危险**。
    先解决"认不出"的可观测性（1D.3 的 tier + 显式 unknown），再谈抓取。
- [x] **1D.2b 模组名→项目 ID 的剩余鸿沟（2026-10-21 完成，结论：机械方案到此为止）**
  - 先诊断再动手：直接探已知案例，确认失败模式不是"没排进前 5"，而是
    **查询词召不回**。`notenoughanimations` / `justzoom` 用压缩写法查询
    返回**零命中**，换成带空格写法则**一次命中**
    （`/v2/project/not-enough-animations` 返回 200）。
  - 做了唯一安全的那一步：命中失败后按**驼峰 / 字母-数字边界**再问一次。
    接受的规则**不变**（命中项仍须归一化后与候选完全相等），所以它只能
    找到正确项目，不可能编出名字不对的匹配。
  - 结果：**45.8% → 50.8%**（55→61/120，+5pp）。捞回的 6 个全是驼峰名
    （`XaerosWorldMap`→`xaeros-world-map`、`MekanismGenerators`、
    `CustomMachinery`、`AirHop`、`HostileNeuralNetworks`、
    `MekanismAdditions`）。已设为默认，`--no-variant-retry` 可关。
  - **明确停在这里的理由**：剩下的 59 个失败分两类，都不是调参能解决的——
    ① 全小写连写（`justzoom`、`rarcompat`）**没有机械切分点**，
    要切就得引入词典/分词器；② 真别名/改名（`appliedenergistics2`→`ae2`、
    `TConstruct`→`tinkers-construct`）要人工别名表，且成本随模组数线性增长。
    这两条都是**需要决策的取舍**，不适合我替用户默认开启。
  - 副作用：`--variant-retry` 仍可能在一组同名项目（本体/移植/续作）里挑错，
    字符串规则消不掉，已在报告方法说明里写明。
- [x] **1D.3 边分级重构（2026-10-21 完成）**
  - 做：每条边加 `evidence_tier`：`declared` / `maintainer_verdict` /
    `inferred` / `cooccurrence`。**与 `relation` 正交**——`relation` 说"断言
    什么"，`evidence_tier` 说"凭什么"。
  - 关键设计：tier 是 `(relation, maintainer_verdict)` 的**纯函数**
    （`derive_evidence_tier()`），生成器与存量迁移走同一段逻辑，不存在
    第二份规则。`declared` 从报告输入**不可达**——本工具从没读过清单；
    该档位是为 1D.2 预留的，测试会"绊线"式拦住第一条未经思考的 declared。
  - 迁移：新增 `--rederive-tier`（幂等，不重扫语料）。存量 9895 行已补字段，
    并用 git 基线验证**除新字段外 0 行变化**。分布：
    `cooccurrence 9721` / `inferred 163` / `maintainer_verdict 11` /
    `declared 0`。
  - **补上了原本完全缺失的东西**：`compat-edges.jsonl` 之前**没有任何测试**。
    新增 `tests/test_compat_edges.py` 14 测试：tier 合法性、与推导规则一致
    （手改会被抓）、共现不得声称因果、因果不得被降级、自环/成对语义、
    迁移幂等、坏 relation 拒绝、以及**诊断文档不得泄漏边词汇**。
  - 测试有效性已验证：篡改一行把 `co_occurred` 的 tier 改成 `inferred`，
    2 条测试立刻变红；恢复后回到 14 绿。
  - 修的真实缺陷（1D.0 实测新增两条）：
    ① 9721 条 `co_occurred` 与 82 条 `caused` 共用一个 `relation` 字段，
    schema 上无区分，**下游迟早误用**——本步解决；
    ② **`mod_ids` 是死字段**（0/488 有值）——已在 1D.4 修复（0 → 106 份）；
    ③ `jars` 混入 classpath 库，**任何把它当"已装模组集"的下游都是错的**
    ——已在 1D.4 给出唯一分类定义 `mcd/metadata/jars.py`。
- [x] **1D.4 覆盖率仪表盘 + 采集字段收尾（2026-10-21 完成）**
  - 做：`tools/coverage_report.py` 按失败模式统计诊断率与未覆盖样本 →
    `corpus/COVERAGE.md` + `corpus/coverage.json`。全量 454 份 / 224s。
  - 结果：诊断率 **67.2%**（305/454），0 解析失败。分桶（样本数 / 诊断率）：
    `mixin` 64 / 89%、`mod-loading` 82 / 83%、`world-data` 21 / 90%、
    `watchdog` 14 / 86%、`native` 7 / 43%、`mod-bug` 153 / 63%、
    `other` 113 / 43%，`oom` 与 `plugin` 为 0（见下）。
    **以上是 2026-10-21 的历史口径，不要引用。** 1E.5 修掉 `TRANSFORMER/` 与
    JPMS 前缀后，`_is_platform_frame` 才真正认得出原版帧，62 份报告从
    `mod-bug` 移进 `other`；当前值见 `corpus/COVERAGE.md`（**74.2%**，
    337/454，未覆盖 117）。两个数字的差不是矛盾，是解析器修好之后的重分类。
  - **桶定义被自己的实测推翻两次**，这是本步最有价值的部分：
    ① `world-data` 原先匹配裸词 `chunk `/`anvil`/`corrupt`，而 `anvil` 在 114 份、
    `chunk ` 在 138 份报告里出现，**绝大多数是类名**（`AnvilChunkLoader`、
    `LevelChunk`）。它声称 140 份"世界数据"失败，真实值不到 20。改用失败短语后
    剩 21 份，且诊断率 90%——旧的 72% 是被稀释出来的假象；
    ② 新增 `mod-bug`（最深一层 `Caused by:` 的首帧不在平台命名空间）覆盖
    153 份（34%），把原 `other` 里最大的一块变成了可行动类别。
  - **空桶必须显式出现**：`oom` 实测 0/454（`OutOfMemoryError` 与
    `java heap space` 都零命中），`plugin` 为 0（语料只有 mohist/arclight
    这类混合端，没有纯 Bukkit 系）。报告里写清"是语料没有，不是规则缺陷"，
    并附加载器分布作依据——省略一行会让读者以为"不存在"，写 0 不解释会让
    读者以为"已覆盖"。
  - 收尾三个采集缺陷，全部**离线**完成（正文已在 `corpus/github/`）：
    ① `mod_ids` 死字段 → 改为读 `-- Mod List --`（`MODID_RE` 找的
    `from mod (x)` 在语料里出现 480 次且**全部是 `unknown`**）。0 → **106 份 /
    3,080 个 id**，平台行（`minecraft`/`forge`）剔除 125 个；
    ② `jars` 混入库 → 新增 `mcd/metadata/jars.py`，把"库/模组/加载器/未知"
    做成一个可审计定义（`LOADER_ARTIFACTS` + `RUNTIME_LIBS` 两张表即全部输入），
    audit 工具改为引用它，删除私有副本；
    ③ **发现索引有 34 行重复**（488 行 / 454 个不同 issue）。根因是
    `load_index()` 定义了却**从未被调用**，采集重跑就重复追加。已修采集端
    （守卫进写入循环）+ 迁移数据（`tools/rederive_index.py --dedupe`）。
  - 顺带修的两个真实 bug：`is_runtime_lib` 拿归一化后的名字去比**未归一化**的
    集合，`commons-lang3` 这类带连字符的条目**从来匹配不上**；`jar_stem` 遇到
    栈帧原始写法 `~[x.jar:?]` 返回空串（`]` 在末尾时 `rsplit` 得空）。
  - **收尾 1D.3 的派生数据一致性**：本步曾判定 `compat-edges.jsonl` 因索引
    变更而变旧，**重建实测为逐字节相同**（9,895 行、tier 分布不变）。错因是
    把 `build_compat_edges.py`（共现来自 `rep.mods`，报告里的 Mod List）与
    `audit_modrinth_mapping.py`（候选来自 `mixin_configs + jars`）搞混。
    散文式警告已换成断言
    （`test_every_cited_report_still_exists_in_the_index`，双向验证过）。
  - 测试：新增 `tests/test_jar_kinds.py`（33）、`tests/test_coverage_buckets.py`
    （24）、`tests/test_index.py`（7），`test_compat_edges.py` 14 → 15。
    门禁 **675 passed**。
  - 验收：能回答"下一条规则该写什么"（Top-20 未覆盖签名 + 分桶缺口）；
    `mod_ids`/`jars` 语义写死在文档里。

### 1E. 评测强化（1C.2 发布前置，依据：RESEARCH J4 / §3.4）

- [ ] **1E.1 可计分样本扩容 7 → ≥40**
  - 为什么：7 份样本的 Wilson 95% CI 实测 **[2.6%, 51.3%]**（不是 39.9%——
    正态近似下界为负、被截成 0%，见 1E.2①），宽到没有信息量。
  - 做：继续 harvest 带明确 verdict 的仓库；对现有 7 份双人标注算 Cohen's kappa。
  - **失败判据**：kappa < 0.6 → 先修标注规范再扩样本。
  - 状态：**受阻于 GitHub API 配额**（已两次询问 PAT，未获答复）。
    离线能做的部分已做成 **1E.4**（不同度量，不能替代本条）。
- [x] **1E.4 归因消融：没有游戏提示时我们还剩什么（2026-10-25 完成）**
  - 为什么：`triage()` 给报告自带的 `Suspected Mods:` 行权重 12（最高）。
    因此"top-1 落在游戏列表里"**有循环成分**——我们部分在复述输入。看起来
    漂亮，什么也证明不了。
  - 做：`tools/attribution_ablation.py` 删除该行后重跑归因，问独立证据
    （mixin 归属 / 模组栈帧 / jar / 消息类名）是否还能落到一个 mod id。
    裁判仍是游戏那行（离线唯一可得的独立归因），所以它测的是**一致性**，
    不是正确性；`minecraft`/`fabricloader` 这类平台伪模组已剔除。
  - 结果（n=35，报告见 `corpus/ATTRIBUTION_ABLATION.md`）：
    **改动前 20/35（57%）完全哑火**，能作答的 15 份里 7 份与游戏一致；
    改动后哑火 4/35（11%），31 份能作答、23 份一致（74%）。
    带提示的一致率 28/35 → 32/35。
  - 找到的病根：20 份哑火里 17 份是 Fabric API——归属信息只写在
    **mixin 生成的方法名**里（`wrapOperation$cdi000$fabric-registry-sync-v0$…`），
    而我们从没读过方法名。新增信号 `W_MIXIN_METHOD=6`，三条判据都是实测定的：
    ① **必须锚定种子段**——裸 `$…$` 扫出来的是 `bridge`/`new`/`static` 这些
    Mixin 术语；② **只看 top-5 帧**——扫 25 帧时前三个"命中"有两个来自
    frame #12/#14，其中一个是 Not Enough Crashes 的崩溃报告装饰器
    （名字就叫 `atTheEndOfSecondCatchBeforePrintingCrashReport`，凡是它装饰过的
    报告里都有，证明"报告被处理过"，不证明原因）；③ **每模组每信号只计一次**
    ——按帧累加会到 6×N 并开始压过游戏提示（带提示一致率 28→25 就是证据）。
  - 一个**度量后删掉**的改进：`TRANSFORMER/<modid>@<ver>/` 帧前缀。它只多给了
    1 个答案，而那 1 个是错的（twilightforest vs 游戏说的 accessories），还顺手
    压掉了同一份报告自己的提示。删掉而不是调参。
  - 指标联动：盲测诊断率 141→**148**（65%→68%），blame-error 仍是 **1/7**
    ——新命中的 7 份都不在计分集里。`corpus/BLIND_EVAL.md` 已同步并写明原因。
  - 测试：`tests/test_attribution_signals.py`（17 项，含"装饰器不许被冤枉"
    与"消融只能削弱、不能换人"两条真实报告回归）。
  - 留下的已知缺陷（故意不顺手做）：`_parse_frame` 的方法名字符类不含 `-`，
    于是 `fabric-*-v0` 这类方法名被粘进 `f.cls`（43 份报告 83 帧）。新信号
    两个字段都读，归因不受影响；但**对其它消费方 `cls` 是错的**，修它要改全语料
    的 `cls`，得单独做 before/after 快照（`tools/parser_snapshot.py`）+ 门禁。
    → 已作为 **1E.5** 单独做完。
  - 门禁 698 → **715 passed**。
  - 上面这些数字是 1E.4 完成时的状态。1E.5 的帧修复之后重测为：哑火 **3/35**、
    独立可作答 **32/35**、其中一致 **23/32**、带提示一致 **31/35**（少的那 1 份
    就是 1E.5 里说的 `twilightforest#2543`）。差异与原因见
    `corpus/ATTRIBUTION_ABLATION.md`「What the frame-parser repair changed」。
- [x] **1E.5 帧解析归一化：一半的栈帧本来是被丢掉的（2026-10-25 完成）**
  - 为什么：1E.4 只发现了这个缺陷里最小的一条（`-` 进方法名，79 帧）。真去量
    一遍才发现是三件事，而且最大的一件不是它：
    | 缺陷 | 帧数 | 报告数 |
    |---|---|---|
    | 尾部 `[jar]` 没剥（旧代码只剥 `~[jar]`） | 5,432 | 148 |
    | `TRANSFORMER/<层>/` 或 JPMS `module/` 前缀留在 `cls` | 16,286 | — |
    | `-` 方法名粘进 `cls` | 79 | 43 |
    失败方式全都一样：正则不匹配 → 兜底 `f.cls = head` → 方法和行号消失。
    不抛异常、不留空字段、门禁全绿。
  - 做：`_frame_head()` 先循环剥 `{}` / `~[…]` / `[…]`（两种顺序都出现），
    再在 `(` 之前丢掉最后一个 `/` 左边的一切——Java 类名不含 `/`，所以那
    之前的东西不可能是类名的一部分，这样一次覆盖 TRANSFORMER 层与三种 JPMS
    写法；方法名字符类补 `-`。另修 `is_minecraft` 用 `startswith("net.minecraft")`
    把 `net.minecraftforge.*` 也判成原版（`elif` 永远进不去）。
  - 结果：`cls`+`method` 解析成功 **48,728 → 57,158 / 57,282**；454 份报告的
    `mods`/异常数/预期模组/加载器/报告类型**全部不变**（快照比对，0 处差异；
    帧数 57,282 前后一致）。剩下的 124 帧：8 帧是源文件换行被吃掉导致两帧粘成
    一行（3 份报告，语料本身的缺陷），1 帧是 Groovy 生成的 `#transformer-5`
    名字，其余是没有 `(...)` 的行。
  - 下游（全部指向可修的方向）：分桶 `mod-bug` 153 → **91**、`other` 113 →
    **175**（62 份原版抛出点被算成"模组 bug"）；有命中的报告 **318 → 337**
    （+19，**零份丢失**）；盲测诊断率 148 → **155**/218，mod 仓库 105 → **112**/143，
    blame-error 仍 **1/7**；消融哑火 4/35 → **3/35**。
  - 唯一反向的一处，写进文档而不是抹掉：`twilightforest#2543` 现在把
    `twilightforest` 排在 `accessories` 前面（维护者标签是 `other mod`）。
    它不在计分集里，但它说明"证据变多"也会**推翻一个本来对的提示**。
  - 仪器：`tools/parser_snapshot.py` 增加 `frames_sig` 与 `frame_defects`——
    旧的快照只数帧数，而这次帧数前后完全一样，靠它根本发现不了。
    `tests/test_frame_parse.py`（18 项）逐条钉住上表。
  - 门禁 715 → **733 passed**。
- [x] **1E.2 区间估计 + 稳定性 + 蜕变测试**
  - 做：① `blind_eval.py` 输出 Wilson 区间，废止无区间点估计；
    ② top-1/top-2 交换稳定性测试（构造近分候选，交换顺序断言不翻转——
    这是 Berkeley judge 审计里"位置偏差"给排序系统的通用教训）；
    ③ 蜕变测试：改写时间戳/玩家名/路径，诊断结论必须不变（借 MetaQA 思路）。
  - 验收：`corpus/BLIND_EVAL.md` 无裸点估计；三个新测试全绿。
  - 落地（2026-10-23）：
    ① `wilson()`/`_ci()`/`_ci_str()` 进 `tools/blind_eval.py`，stdout 与
    `blind-eval.json` 的 `ci95` 块都带区间；`quotable_as_rate` 标志把
    "n<30 不许当比率引用"写进数据本身。`corpus/BLIND_EVAL.md` 全部重算，
    并**撤回**上一版"no significant overfitting"的结论（两条区间几乎完全
    重叠 = 这项比较没有检出力，既不能确认也不能排除过拟合）。
    ② **位置偏差是真 bug，不是假想**：`ranked = sorted(scores.items(),
    key=lambda kv: -kv[1])` 在 `defaultdict` 上平分时按插入顺序决胜，即按
    报告里栈帧 / Mod List 的书写顺序。改为 `(-score, modid.lower())`。
    `tests/test_invariance.py` 用一对顺序相反的合成报告 + 6 份真实报告
    反转 Mod List 行序做回归。
    ③ 蜕变测试：时间戳/日期/玩家名/世界名/安装路径/UUID 全部改写后，
    规则集合与 top-1 必须不变（`test_invariance.py`，另附一个"scrubber 真的
    改了东西"的守卫，防止空转变绿）。
  - 顺带发现并修掉一个真实的性能 bug：`_parse_forge_modlist` 的六段惰性
    正则在**畸形表格行**（4 个 `|`、大量对齐空格）上灾难性回溯，
    242 字符行 321 ms/行；Mekanism#2697 与 Placebo#8291 各含约 350 行，
    单文件 9.4 s。全语料遍历 **250.8 s → 30.7 s**（8.1×），
    454 份报告的解析输出**逐字节不变**（快照比对，mods 总数 11,583 不变）。
    换成 `split("|")` 后配 `tests/test_forge_modlist.py`（13 项契约 +
    成本守卫）。
  - 门禁 675 → **698 passed**（耗时 4m42s → **1m13s**，主要来自上面那条
    解析提速）。
  - 顺带补的两个守卫盲区（都属于"散文不可检验"）：
    `tests/test_web_bundle.py` 只比模块名，查不出 wheel **内容**陈旧——
    这次改 `parser/report.py` 一个文件名都没变，站点还带着 9 秒解析器而全绿；
    已加 `source_digest` 进 `wheel-manifest.json` + 断言。
    "逐字节不变"原先只写在提交信息里，已提升为
    `tools/parser_snapshot.py --write/--check`。两条都双向验证过。
- [x] **1E.3 离线 LLM 辅助规则候选（人在环，可选）——2026-10-25 完成，
  但结论是"停手"而不是"多写规则"**
  - 做：`tools/suggest_rules.py` 对未覆盖语料聚类，产出**候选清单**并把
    每条的"一条规则能买到几份报告"摆在最前面；`--ingest` 是草稿进入
    `corpus/rule-drafts/` 的唯一入口，逐条验证后才落盘。
  - 硬约束（全部做成可执行断言，不是注释）：LLM 输出**永不直接进**
    `builtin/`（`test_no_draft_rule_is_in_builtin`）；草稿必须过
    `test_rule_metadata.py` 全部守卫；每条草稿带 `generated_by: {model, date}`；
    `id` 必须以 `candidate.` 开头；`lifecycle_status` 必须是 `draft`；
    fixture 必须真实存在；**在语料上一份报告都不命中的草稿直接拒收**。
  - **先量后写，于是写不动了**：117 份未覆盖 / 107 个签名聚类 / 100 个是单例
    / 平均一条规则 **1.09 份**报告 / top-10 只占 **17%**。R4 的停手判据是
    top-10 < 30%，**判据触发**：写规则不再是瓶颈，再写 100 条窄规则也买不到
    100 份报告的信任。
  - 只写了 1 条，且是唯一诚实的那条：`candidate.debug-crash.manual`
    （5 份报告，`Description: Manually triggered debug crash`，即用户按 F3+C
    故意生成的报告；这 5 份分别是屏幕闪烁、纹理渗透、FPS 掉帧、卡死、视频设置
    打不开——崩溃报告里根本没有它们要报的症状）。实测把未覆盖从 117 降到 112、
    诊断率 74.2% → **75.3%**（`MCD_RULES_PATH=corpus/rule-drafts` 跑出来的，
    不是估算）。另外 116 份的结论是**给结构化输出、交给人**，不是继续堆规则。
  - 产出：`corpus/RULE_CANDIDATES.md`（107 个聚类的清单 + 建议 `when` 骨架 +
    单例标注）、`corpus/rule-candidates.json`、`corpus/rule-drafts/`、
    `tests/test_rule_drafts.py`（9 项）。
  - 事后补的**漂移守卫**（本轮）：这份清单里的数字是"写规则还值不值得"的唯一
    依据，而 `uncovered` 是 `coverage_report.py` 和 `suggest_rules.py` **两个工具
    各自从同一语料、同一规则集算出来的量**。加一条规则、只重算 `coverage.json`、
    忘了重算本清单，仓库就会带着一份"标题数字与自己的覆盖率报告互相矛盾"的文档
    发布——陈旧数字和新数字长得一模一样，没人会发现。
    新增 `tests/test_rule_candidates.py`（14 项，**0.07 s**）分两层：
    常驻层只做①产物内部算术②MD 与 JSON 一致③与 `coverage.json` 交叉比对，
    不碰语料；全量重算（实测 **35 s**）放在 `MCD_DRIFT_FULL=1` 后面，
    与 `blind_eval` 同一策略（贵的东西当报告，不当门禁）。
  - 守卫的**反向验证**（三条都实测变红再恢复）：植入 `uncovered=118` → 5 项变红
    （含交叉比对，报错直接说"重算哪个文件"）；把 `R4_MIN_SHARE` 偷偷从 0.30
    降到 0.10 → R4 判据那项变红（停手判据必须能在事后被核对，否则它只是
    事后合理化）；在首个 `when` 块里植入未闭合引号 → YAML 回环那项变红。
    `MCD_DRIFT_FULL=1` 实测通过：提交版与重新生成**逐字节一致**。
  - 顺带修两处同类隐患：`suggest_rules.py` 的语料枚举改成递归
    （与 `coverage_report.py` 完全一致，否则两个工具会从"文件集不同"开始分叉），
    单个坏文件从"让 `--report` 崩掉"改成"跳过并告警"（`coverage_report` 早就是
    这么处理的）。两处都是纯健壮性：产物重算前后逐字节不变。
  - 门禁 733 → **743 passed**；加上漂移守卫后 **756 passed**
    （72.58 s → **72.78 s**，即守卫本身只花了 0.2 s）。

---

## 阶段 2：整合包与模组质量（2027-04 ~ 2027-12）

> 对应 VISION 第二阶段。从工具变工具链。**进入条件**：阶段 1 的 Schema
> 和兼容边管道稳定运行 ≥3 个月，有真实数据积累。
>
> **2026-10-25 修订：这个"进入条件"不该整段套用。** 它防的是"在没有稳定
> 数据时下结论"，但 2.2 的检查器**完全不依赖任何外部数据**——它只读你本机
> `mods/` 里 jar 自己写的声明。所以 2.2 的离线部分已经做了（见下），
> 而不是等到 2027。
>
> 真正需要"3 个月数据积累"的是 **2.1 / 2.3 / 2.4**：前两个要网络元数据与
> 持续采集，2.4 要**边本身可信**——实测 `compat-edges.jsonl` 的 9,895 条里
> 9,721 条是裸共现（`evidence_count=1`、无 confidence），在这个数据上做
> "A 和 B 兼容吗"等于用噪声回答。**2.4 卡的不是工期，是证据质量。**
>
> 结论：阶段 2 不再是一个日期，而是三条不同性质的线——**已可做（2.2 离线）/
> 卡数据（2.4）/ 卡网络与决策（2.1、2.3）/ 卡 1C.2（2.5）**。

- [ ] **2.1 Modrinth/CurseForge 元数据接入**（**与 2.2 同期，不提前**）→
  1D.2 已重新定义为"正向依赖图 + 确认层"。此处补 CurseForge
  （需 `x-api-key` + 审批 + 商用协议，门槛高故延后）。
  **前提**：先把 1D.2b 的匹配率拉起来——当前 45.8% 意味着半个整合包不可见。
- [ ] **2.2 Pack Doctor MVP**：扫描 `mods/` + `manifest.json`，输出**具体
  findings**（重复/缺前置/混用/版本不匹配/客户端模组误装）。
  **不做健康分数**（见 VISION §2.2 工程意见），只做可追溯条目。
  直接消费 **1D.1 的本地 jar 清单**（已完成，无需网络）+ 1D.2 的版本约束，
  **必须实现 Maven 区间语义**（`[1.20,1.21)` 含端点区分、裸 `1.20` 是软下限
  而非精确锁定、`[1.20]` 才是恰好——见 RESEARCH §3.5A）。
  **硬要求**：认不出清单的 jar 必须显式列出，不许静默跳过。
  - **状态（2026-10-25）：五类 findings 已实现四类，且完全离线。**
    `mcd/pack/`（`version.py` + `doctor.py` + `render.py`）+ `--pack DIR`。
    已实现：`pack.duplicate-mod` / `pack.missing-dependency` /
    `pack.mixed-loaders` / `pack.version-mismatch` / `pack.declared-conflict`
    （`breaks` 判 ERROR、`conflicts` 判 WARNING）。Maven 语义按本条要求实现
    并在测试里逐条钉死（`[1.20,1.21)`、`[1.20]`、裸 `1.20`=最小、Fabric 的
    `~`/`^`/`x`/空格合取）。**认不出的区间返回 `None` 并作为 `undecided`
    逐条打印，认不出的 jar 作为 `unreadable` 逐条打印**——这两条是硬要求，
    不是附加功能。
  - **还剩一项：客户端模组误装。** `mcd/metadata/manifest.py` 目前不读
    Fabric 的 `environment` 字段，所以检查不了；报告里明写"NOT CHECKED"
    而不是猜。补这一步要动 reader + 它那 28 个测试，留作下一步。
  - 未做且本条不要求：嵌套 jar、版本是否存在/是否最新（需要 2.1）。
- [ ] **2.3 Mod Doctor**：把 `harvest_corpus.py` 升级为持续监控 + 版本回归
  对比（"1.8.2 相比 1.8.1 新增/消失哪些崩溃"）。
  **版本回归对比不是独立功能而是必需品**：文献里的跨数据集漂移，在 MC 里
  表现为跨版本漂移（RESEARCH §3.1），这是规则失效的主要机制。
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

1. **阶段 0 已全部完成（6/6）**：0.2 网页版已上线
   `https://pop1022.github.io/mc-crash-doctor/`（读回验证过页面标题与输入框在
   真实 HTML 里，不是 404）。Phase 0 不再是阻塞项。
2. **1D.4 已完成**：`corpus/COVERAGE.md` 回答"下一条规则写什么"。全语料
   454 份诊断率 **74.2%**（337/454），未覆盖 **117** 份——且集中处已经变了：
   `other` 独占 78 份（67%），`mod-bug` 只剩 16 份（1E.5 修好帧解析后，
   62 份从 `mod-bug` 移进了 `other`，因为原版帧终于认得出来了）。
   下一个规则的靶子是 `other`，不是 `mod-bug`。顺带修掉三个采集缺陷：
   34 行重复记录、`mod_ids` 死字段（0 → 106 份 / 3,080 个 id）、`jars` 无分类。
   **2026-10-25 追加：`corpus/VERSION_STRATA.md` 补了"按版本"这一维**——
   四条可引用层（1.16/1.19/1.20/1.21，n≥30）两两相邻差 5–18pp 且区间全部
   重叠，20pp 失败判据**没有触发**；同时暴露一个混淆项：196 份（30%）根本
   没有 `Minecraft Version:` 行（Bedrock 日志、非崩溃报告的 issue 正文），
   它们诊断率 49.5%，是"报告形态"层而不是版本层。
3. **1D.2 仍待你定夺**：匹配率 50.8%，剩下的失败是**全小写连写**（要词典）
   与**真别名**（要人工表）。1D.4 已把"认不出"做成显式可见的错误，所以
   现在可以安全地维持 50.8% 而不掩盖问题。
4. **`compat-edges.jsonl` 已用修好的索引重建验证：逐字节不变。** 我上一轮
   曾判定它"比索引旧"，**那是错的**——重建实测 `cmp` 干净（9,895 行、tier
   分布不变）。错因是把两个工具的模组名来源搞混：边构建用 `rep.mods`
   （报告里的 Mod List），audit 用 `mixin_configs + jars`。这类"散文式警告"
   没法被检验，所以已换成可执行的断言
   （`tests/test_compat_edges.py::test_every_cited_report_still_exists_in_the_index`，
   已双向验证：删一条被引用的索引记录 → 精确报出该条 → 恢复后转绿）。
5. **1D.2b 已量完，机械方案到此为止**：词边界重试把匹配率从 45.8% 提到
   **50.8%**（已设为默认，安全）。
6. **1D.1 已完成**（`mcd/metadata/`，61 测试）。纯本地能力，不依赖网络，
   可直接被 2.2 Pack Doctor 消费。新增的 `mcd/metadata/jars.py` 让"库/模组/
   加载器/未知"只有一个定义，`tools/audit_modrinth_mapping.py` 已改为引用它。
7. **1C.1 GitHub Action 已实现并 dogfood 过（已打勾）**（20 个测试含假 API
   的端到端）。在仓库真实 issue #1 上跑通，**并且抓到一个测试套件抓不到的
   缺陷**：`crash.runtime-mod` 对 OOM 报告也触发，评论里让用户"更新模组、
   检查运行时 NPE/ISE"，而报告里既无 NPE 也无 ISE。语料永远抓不到它——
   harvested 454 与 aternos 201 里 OOM 报告数都是 0。
8. **1C.2 PyPI 发布前置 1E**：别在指标只有点估计时对外发布。**1E.2 已完成**
   ——现在每个比率都自带 Wilson 区间，`blind-eval.json` 里的
   `quotable_as_rate` 会明说 1/7 不是比率。**1E.4 也已完成**——补了一个不依赖
   API 的度量，顺带证明"top-1 在游戏列表里"本是循环论证。剩下的只有 1E.1
   扩样本，而它卡在 GitHub API 配额上（需要你给 PAT，或明确说"就用 7 份"）。
9. **1E.4 的结论值得记住**：52% 的提升不来自权重调参，而来自**读了一个
   我们从没读过的字段**（mixin 生成的方法名）。同时它是本轮唯一一个"改完
   反而更差、于是删掉"的改动（`TRANSFORMER/` 帧前缀）。两件事合起来是这条
   经验：**先量，再改；量不出变好就回滚，不要留着调参。**
10. **解析器提速 8.1×（1E.2 顺带）**：`_parse_forge_modlist` 的六段惰性正则
    在畸形表格行上灾难性回溯，单文件最坏 9.4 s。换 `split("|")` 后全语料
    遍历 250.8 s → 30.7 s，454 份报告输出逐字节不变。门禁耗时也跟着
    4m42s → 1m13s。**这条不是纯性能优化**：真实用户粘贴 276 KB 报告时
    会等 9 秒。
11. **帧解析那个已知错误已修**（1E.4 发现 → 1E.5 修完，2026-10-25）：不是一条
    而是三条，最大的一条和 `-` 无关——`[jar]` 尾部没剥、`TRANSFORMER/` 与
    JPMS 前缀留在 `cls`。57,282 帧里解析成功的从 48,728 涨到 57,158，454 份
    报告除帧字段外**零差异**。教训：旧的快照只数帧数，而帧数前后完全一样；
    仪器不记住"形状"，就发现不了形状被改了。
    **同日晚些时候收尾：剩下 8 帧也只差三类**（4 行里塞了 2–11 帧、行尾
    markdown 反引号、`~[jar]` 被截断未闭合）。修法不是"标注为已知噪声"——
    粘连行原来会把**最后一帧**的方法名配上前面所有帧的 `cls`，看着像正常帧。
    修完 `frame_defects` 8 → 0，帧数 57,282 → 57,308，3/454 份变化、其余
    逐字节不变；规则引擎全语料 524 条结论前后一致（零代价）。
12. 设计依据见 **`docs/RESEARCH.md`**（§3.6 是实测，J1 已被它改写）；
    本文档只回答"做什么、怎么算做完"。
13. **两条"没人会记得去做"的生命周期补上了**（2026-10-25）：
    - `web/` 体积预算（`tools/build_web.py` 的 `SIZE_BUDGET`）——此前
      `web/` 229 KB 无任何阈值断言。预算按"结构性跳变"设（wheel 多一个
      运行时依赖、语料泄进 `sample.js`），≈30% 余量；已用"人为撑大 30 KB
      → 精确报出 `app.js 65,382 > 60,000` → 还原转绿"验证会咬人。
    - 规则生命周期快照（`corpus/rule-lifecycle.json` + `tools/rule_lifecycle.py`）
      ——4 条 `experimental` 靠人记得才可能升级。现在状态绑定到语料版本
      （661 份文件、56.5 MB 的 digest），语料一变门禁就红；全量重算 40 s
      只在手动跑。实测 4×661 = **0** 次真实命中，所以"今天不该升级"是一个
      测出来的结论，而不是一句注释。
14. **阶段 2 已经开始了，不是 2027 才开始**（2026-10-25）：2.2 Pack Doctor 的
    离线部分已落地（`mcd/pack/` + `--pack DIR`），五类 findings 实现四类，
    完全不需要网络、不需要 1D.2、也不需要你决策。**这是"从诊断单次崩溃"变成
    "预防崩溃"的第一步**，而且它是唯一一步不依赖任何外部数据的工作。
    剩下三条线的真实前置见阶段 2 开头那段修订说明——2.4 卡证据质量（98% 的边
    是裸共现），2.1/2.3 卡网络与采集，2.5 卡 1C.2。
15. 已完成：0.1 / 0.3 / 0.4 / 0.5 / 0.6 · 1A.1 / 1A.2 / 1A.3 ·
    1B.1 / 1B.2 · **1D.0 / 1D.1 / 1D.2b / 1D.3 / 1D.4** · **1E.2 / 1E.3 / 1E.4 / 1E.5**。

每完成一步，把对应 `[ ]` 改 `[x]`，并在 CHANGELOG 记一笔。

---

*整理：Hermes Agent（qwen3.8-max-0902），2026-09-23。
愿景主体见 VISION.md（用户规划）；本文档是执行层排序，含工程判断。*
