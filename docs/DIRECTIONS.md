# 开发方向 · 方案清单（2026-11-17）

> 不排时间表。这里只回答三件事：**有哪些可做的事**、**每件的成本和验收**、**谁卡着谁**。
> 现状实测：1000 项测试绿（46.7 s）、46 条规则、诊断率 75.8%（344/454）、单份 224 ms、未上 PyPI。

---

## 一、方案总表

成本口径：**S** ≤ 半天、**M** 1–3 天、**L** 1–2 周、**XL** 2 周以上。
阻塞口径：**无** = 现在就能做；**凭证** = 需要 PyPI/GitHub token；**外部** = 需要审批或第三方数据。

### A. 分发（决定有没有人用得上）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| A1 | **发布 PyPI** | 填 pending publisher 五字段 → dry_run → tag → 真发 | S | 干净容器 `pip install` 成功 | 凭证 |
| A2 | **版本化 Action** | 打 tag 后把 `@main` 换成 `@v0.1` | S | 一个用 tag 的示例仓库跑通 | A1 |
| A3 | **Docker 镜像** | python:3.12-slim + 非 root + 只装 wheel | S | `docker run -v $PWD:/w mcd /w/crash.txt` 输出结论 | 无 |
| A4 | **uvx / pipx 一行装** | 依赖 A1，补文档与示例 | S | 文档三行内能跑通 | A1 |
| A5 | **GitHub Release 产物** | 源码包 + wheel + 校验和 + 变更摘要 | S | Release 页有可下载 wheel 与 sha256 | 无 |
| A6 | **编辑器扩展（VS Code）** | 打开 .txt/.log 右键诊断，调用 CLI JSON | L | 扩展市场外可侧载安装 | 无 |

### B. 本地化（决定中文用户能不能读）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| B1 | **规则正文中文化（机制）** | YAML 加 `title_zh/explanation_zh/fixes_zh`；渲染按 lang 选择，缺翻译回退英文 | M | `--lang zh` 输出中文；英文输出逐字节不变 | 无 |
| B2 | **高频规则翻译** | 覆盖全部诊断量 70% 的 6–8 条优先 | M | `tools/i18n_status.py` 报告覆盖率 | B1 |
| B3 | **全量 44 条翻译** | 剩余规则逐条翻译 | L | 覆盖率 100%，测试校验每条都有 zh | B2 |
| B4 | **网页跟随 UI 语言** | 诊断时把 lang 传进引擎；切换语言重跑一次 | S | 切 EN/中文，结论正文同步切换 | B1 |
| B5 | **英文正文润色** | 现有 explanation 偏长，统一句长与动词开头 | M | 抽样 10 条人工确认 | 无 |

### C. 反馈闭环（决定数据会不会增长）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| C1 | **CLI `--feedback`** | 生成脱敏摘要 + 预填 issue URL，打印到终端 | S | 一条命令产出可直接点开的链接 | 无 |
| C2 | **网页"结论不对？"** | 结论卡加按钮，复用同一套脱敏逻辑（Pyodide 内） | M | 点按钮生成 issue 草稿，含报告与更正 | C1 |
| C3 | **误判标签体系** | issue 模板加 `wrong-mod` / `wrong-root` / `missed` 三分类 | S | 新 issue 自动带标签 | 无 |
| C4 | **反馈入库管道** | 人工确认后的反馈进 `corpus/`，走脱敏与钉桩 | M | 新增一条反馈 → 生成一条规则候选 | C3 |
| C5 | **匿名使用统计（可选）** | 本地计数、默认关闭、仅聚合 | M | 文档写明开关与数据形状 | 无 |

### D. 归因（唯一低于 70% 的核心指标）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| D1 | **加载器仓归因补强** | 32 份未归因逐份看，补 loader 专属堆栈规则 | L | 44/73 → ≥55/73，误报不升 | 无 |
| D2 | **class → modid 映射表** | 从 jar 索引构建（已有 metadata 模块） | M | 命中率提升可在盲测复算 | 无 |
| D3 | **mixin 配置反查** | 从 mixins.json 名字反推 owner，现有逻辑延伸 | M | 新增命中样本入语料 | 无 |
| D4 | **并列候选提示** | 两模组分数差 <20% 时明说"可能是交互问题" | S | 已有实现，补测试与文案 | 无 |

### E. 规则工程（决定维护成本）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| E1 | **DSL v2：版本范围** | `mc_version: ">=1.20 <1.21"` | M | 新规则可用；旧规则不改也通过 | 无 |
| E2 | **DSL v2：条件与/或** | `when_any` 列表 | M | 至少一条真实规则迁移过来 | 无 |
| E3 | **规则内联断言** | YAML 里写 `expect: {fires: true, on: fixture}` | M | `mcd rules test` 可跑单文件 | 无 |
| E4 | **第三方规则包** | `--rules-dir` 已有，补校验与版本声明 | M | 坏规则给出可读错误而非栈 | 无 |
| E5 | **生命周期自动化** | 现状靠人记得升级 experimental | S | 每次 `build_web` 自动重算 | 无 |

### F. 持续诊断（从"一次"到"一直"）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| F1 | **`mcd watch`** | tail latest.log，崩溃前 60 s 出结论 | L | 常驻内存 <80 MB，CPU 空闲 <2% | 无 |
| F2 | **Server Doctor MVP** | 日志 + `/tps` 快照 → 风险清单 | L | 只读、不假装实时 | 无 |
| F3 | **崩溃前兆检测** | tick 超时、GC 抖动、内存爬升三条曲线 | L | 在真实语料上回放可提前 ≥30 s 报警 | F1 |

### G. 预防（唯一不依赖网络的扩展）

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| G1 | **Pack Doctor 2.0** | 读真实 jar 依赖图 + mixins 冲突预检 | L | 对 4 个真实包给出可解释结论 | 无 |
| G2 | **侧别检查边界说明** | Forge 无 per-mod side 时输出"无法判断" | S | 不再显示为绿灯 | 无 |
| G3 | **CI 模板** | 给整合包仓库一个即用的 workflow | S | 复制即可在 PR 里拦截 | A2 |

### H. 数据与可复现

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| H1 | **语料可复现包** | 脱敏采样 200 份 + sha256 + 一键复算 | M | 外部能复算 75.8% | 无 |
| H2 | **兼容边分级** | 裸共现降级为"提及"，只保留有证据的边 | L | 每条边带 evidence tier | 无 |
| H3 | **Modrinth 元数据** | 版本 → 已知 issue 映射 | XL | 无网络时优雅降级 | 外部 |
| H4 | **指纹聚类人工复核** | 7 个混合簇逐簇看 | M | 给出"能不能自动合并"的结论 | 无 |

### I. 工程质量

| # | 方案 | 做法 | 成本 | 验收 | 阻塞 |
|---|---|---|---|---|---|
| I1 | **覆盖率门禁** | coverage.py 接入 CI，白名单说明 | M | 核心模块 ≥85% | 无 |
| I2 | **fuzz 测试** | hypothesis 对解析器做属性测试 | M | 1 万次随机输入不崩 | 无 |
| I3 | **CHANGELOG 归档** | 按版本拆文件，保留近两版 | S | 根目录只留摘要 | 无 |
| I4 | **前端拆分** | app.js 54 KB 拆 i18n / render / boot | M | 每块 < 15 KB，构建期检查 | 无 |
| I5 | **体积预算覆盖子目录** | 已完成：`ASSET_BUDGET`（img 700 KB / fonts 90 KB） | — | 门禁可咬人 | 已做 |

---

## 二、优先级矩阵（ROI × 成本）

| | **低成本** | **高成本** |
|---|---|---|
| **高回报** | A1 A2 A3 B1 B4 C1 C3 D4 G2 I5 | D1 G1 F1 |
| **低回报** | B5 I3 | H3 H4 A6 C5 |

判断依据：**"有没有人用得上" > "算得准不准" > "看起来完整"**。当前诊断率 75.8%，再写规则是 0.44pp/条；而 A1 一项就能把安装门槛从"会 pip install ."降到"会 pip install"。

---

## 三、依赖关系

```
A1 (PyPI) ──→ A2 (版本化 Action) ──→ G3 (CI 模板)
          └─→ A4 (uvx)

B1 (i18n 机制) ──→ B2 (高频翻译) ──→ B3 (全量翻译)
                └─→ B4 (网页跟随语言)

C1 (--feedback) ──→ C2 (网页按钮)
               └─→ C3 (标签) ──→ C4 (入库)

E1/E2 (DSL v2) ──→ D1 (归因补强，需要更细的条件表达)

F1 (watch) ──→ F2 (Server Doctor) ──→ F3 (前兆检测)
```

**关键路径**：A1 是所有分发方案的前置；B1 是所有中文工作的前置；C1 是闭环的前置。
这三件都不依赖外部，可以立刻做。

---

## 四、本轮已实施（2026-11-17）

| 方案 | 落地内容 | 验证 |
|---|---|---|
| **B1** 本地化机制 | `Rule` 新增 `title_zh / explanation_zh / fixes_zh`；`run_rules(..., lang=)` 在构建 Finding 之前选文案，缺翻译逐字段回退英文；`RULE_KEYS` 白名单同步 | `tests/test_rule_i18n.py` 5 项 |
| **B2** 规则翻译 | **46/46 全部中文化**（三包：memory-performance 16、mod-loading 17、runtime-crashes 11），按规则逐字段回退 | 6 份地面真值报告全部输出中文，占位符（120.00 秒 / 2048 MiB）正确替换；`i18n_status.py` 报 100% |
| **B4** 网页跟随语言 | `mcd_diagnose(text, lang)`；切换语言时用同一份输入**重跑引擎**（不是只换外壳文案） | `app.js` 语法检查 + 打包重建 |
| **C1** 反馈通道 | `--feedback` 生成预填 issue 链接：只含摘要（路径/IP 已脱敏），不含日志正文 | 实跑输出链接 |
| **C2** 网页反馈按钮 | 结论卡加"结论不对？"，复用 Python 的 `feedback_url()`（不重写脱敏逻辑） | `mcd_feedback()` 桥接 + 语法检查 |
| **C3** 误判标签体系 | 新增 `wrong-diagnosis.md` 模板（labels: triage, feedback），反馈链接指向它 | 模板与链接一致 |
| **A5** Release 产物 | `release.yml`：打 `v*` tag 时构建 sdist/wheel、验证能装、附到 Release | 工作流文件（触发需打 tag） |
| **G3** 整合包 CI 模板 | `examples/pack-check.yml`：PR 改 `mods/` 即静态检查 | 复制即用 |
| **A3** 容器分发 | `Dockerfile`（多阶段、非 root、无网络依赖）+ `.dockerignore` | `pip install .` + 入口点已验证；**本机无 Docker，镜像未构建** |
| **I5** 体积预算 | `ASSET_BUDGET`（img 700 KB / fonts 90 KB）+ `asset_sizes()`；wheel 预算 125 → 145 KB（中文规则文案入包） | `test_web_bundle.py` 7 项 |
| **I2** fuzz | `tests/test_parser_fuzz.py`：真实报告随机截断/拼接/插字符，断言只有 ValueError 可接受，IndexError/KeyError 等一律算 bug | 120 次变异 3.5 s 通过 |
| 已存在，无需改 | **G2** 侧别边界（`not_checked(side)` 已打印"无法判断"）、**D4** 并列候选提示（"score almost equally" 已实现） | 代码核对 |
| **E1** 版本范围 DSL | `when.mc_version` 支持 `>=1.20 <1.21`、`=1.20.1`、前缀 `1.20`；没有版本行的报告**不命中**（不猜） | `tests/test_rule_mc_version.py` 5 项 |
| **F1** `mcd watch` | 字节偏移 tail + 环形窗口（默认 2000 行），崩溃标记触发一次诊断；不写日志、不依赖 watchdog | `tests/test_watch.py` 5 项 |
| **G1**（第一刀） | Pack Doctor 新增 `pack.mixin-config-collision`：两个 jar 带同名 `*.mixins.json` 会互相顶掉 | `tests/test_pack_mixin_collision.py` 4 项 |
| **G1**（第二刀，完整版） | 新模块 `mcd/pack/mixins.py` 读 jar 里的 refmap（Forge 的 `mappings` 与 Fabric 的 `data` 两种形状都支持，配置里点名的 refmap 也能跟随），得到"哪个 mixin 改哪个目标类/成员"。报告新增 `overlaps` 桶：同目标成员 / 同目标类两种粒度，**不计入 findings**，并打印 `mixin_coverage`（读了几 jar、几个目标、几个重叠），让"没有重叠"和"没有 jar 带 refmap"不会看起来一样 | `tests/test_pack_mixin_targets.py` 11 项 |
| **G1**（依赖链） | 缺失依赖现在给出传递链：`chain: flywheel <- create <- immersive_aircraft`（深度封顶 3，环安全，单跳不重复打印） | `tests/test_pack_dependency_chain.py` 5 项 |
| **F2** Server Doctor MVP | `mcd --server DIR`：只读扫描 `logs/latest.log`(`.gz` 也读)、`crash-reports/*.txt`（最多 20 份）、`mods/`，输出风险清单：**同一规则重复出现**（≥2 份，最高优先级）、持续掉 tick（≥20 条 lag 警告）、堆上限相对模组数过小（≤2048M 且 >100 模组）、整合包自相矛盾（ERROR/FATAL 提升为风险）。有 ERROR 才退出 1；输出首行写明"read-only snapshot, not a live monitor"，未测项（TPS、运行状态、轮转日志）逐条列出 | `tests/test_server_doctor.py` 12 项（含"扫描后 mtime 不变"） |
| **I4** 前端拆分 | `web/app.js`（1,281 行 / 55 KB）拆成 `web/src/` 五个源文件（config / i18n / engine / render / wire），`build_web.py` 按文件名顺序拼回 `app.js`。**运行时仍是单个 classic script**（Pyodide 用 script 标签加载，file:// 也要能跑）；测试断言"拼接结果 == 提交的 app.js"，所以直接改 app.js 会失败并提示改 src。逻辑部分各 ≤16 KB（i18n 是数据，单列） | `tests/test_web_app_split.py` 5 项 |
| **E3** 规则内联断言 | 规则可写 `expect: {fires: [夹具], quiet: [夹具]}`，`mcd --validate-rules` 逐条**单规则**跑（不会被别的规则掩盖），缺夹具算问题而不是跳过，形状错误在加载期点名；`--no-fixtures` 供夹具在别处的包跳过。已给 3 条内置规则加 6 条断言（oom.heap / hang.watchdog / crash.runtime-mod 各自的 fires + quiet，其中 quiet 钉的是"OOM 报告不能被甩锅规则命中"） | `tests/test_rule_expect.py` 14 项；`--validate-rules` 实跑 6 条全过 |
| **E2** `when_any` 析取 | `when` 新增 `when_any: [块, 块]`：块之间是 OR，块外的键仍然 AND（"必须 forge，且 frame 或 description 命中"）；捕获取自命中的那个块，模板可混用；嵌套、空列表、非块、空条件块在加载期逐条点名。**没有迁移内置规则**：内置包按长尾冻结政策不再加规则，这个能力是给第三方规则包的，测试用构造规则走完整 `run_rules` 管线 | `tests/test_rule_when_any.py` 10 项 |
| **E4** 第三方规则包校验 | `mcd --validate-rules [--rules-dir D]`：不需要崩溃报告，把加载期的每个警告（坏 YAML、未知键、被丢弃的非只读命令、重复/遮蔽的 id）都当失败，打印"载入 N 条（内置/外部）"与逐条问题，退出码 1；`RuleSet.load(report=False)` 让校验器成为唯一打印者，避免同一警告出现两次 | `tests/test_rules_validate.py` 6 项；已并入 `run_tests.sh` 第 5 道门禁 |
| **H2** 兼容边分级 | `tools/grade_compat_edges.py` 把语料拆成两张表：**pair 图**（9,721 行 → 8,731 条，**全部 C，0 条 A/B**）与**模组级断言**（174 行 → 87 条：A 8 / B 54 / C 14 / rejected 11）。重复行合并后按**不同 issue** 计数（同一对最多出现 14 次），反向 pair 归一；判级复用 `build_compat_edges.derive_evidence_tier`，不再写第二份规则 | `tests/test_compat_edge_grades.py` 14 项；摘要 `corpus/compat-edge-grades.json` 已提交并被测试复算 |
| **I1** 覆盖率门禁 | `tools/coverage_gate.py`：按**包**设下限（parser 93 / triage 92 / rules 86 / pack 90 / report 91 / metadata 83，总 85），与**实测值**（96.6 / 94.4 / 88.2 / 91.8 / 92.9 / 84.9，总 88.5）留 1–2pp 余量；四个入口文件列为例外并逐条给理由；接入 `run_tests.sh` 作第 8 道门禁，`coverage` 进 `.[test]` | `tests/test_coverage_gate.py` 6 项；门禁实跑 all floors met |
| 顺带补的测试 | `render_terminal` 的 rich 分支此前只测过 `color=False` 的降级路径，两个新测试覆盖面板/结论表与"没有规则命中"分支；report 覆盖率 74% → 93% | `test_rule_commands.py` +2 |
| **H1** 语料可复现 | `tools/export_corpus_sample.py`：按种子抽样、双重脱敏、逐份 sha256、manifest 可复算 | `tests/test_corpus_export.py` 3 项 |
| **C4** 反馈入库 | `tools/ingest_feedback.py`：从 issue 正文提取代码块/报告段，脱敏后落 `corpus/inbox/`，**不自动进索引** | `tests/test_feedback_ingest.py` 3 项 |
| 顺带修的 bug | `_REDACTORS` 的 `.minecraft[\\/]` 规则会跨行吞掉路径后面的内容（导出时整行 OOM 消失） | 回归测试 + 全量绿 |
| **D1**（第一刀） | 两条 mixin 加载期规则：`mixin.config-broken`（无法创建 mixin 配置）、`mixin.config-duplicate`（两模组同名配置），各有真实语料夹具 | 加载器仓盲测 44/73 → **47/73 = 64.4%**（同一批 73 份上测） |
| **指标口径修正** | 旧文档把 44/73 写成"归因 60.3%"；eval 从不为加载器仓算 top-1，那是**诊断率**。已改 ASSESSMENT / HANDOFF / BLIND_EVAL.md | `test_doc_numbers` 15 项通过 |
| **API 修复** | `diagnose("file.txt")` 与 `mcd/__init__` 的示例一致（`text` 现在有默认值），此前会 TypeError | 冒烟 |
| 配套 | `tools/i18n_status.py` 报告翻译覆盖率（现 **46/46 = 100%**，无半译规则）；wheel 预算 135 → 145 KB（中文文案入包） | `python tools/i18n_status.py` |

全量测试：**1005 passed, 1 skipped, 46.1 s**（新增 5 项 i18n 测试）。

## 五、剩余项（都不需要凭证，但都 ≥M）

| 项 | 为什么还没做 |
|---|---|
| **D1 余下 26 份** | 逐份看完后确认：多数是 gradle 构建失败、`java.home` 配置、文件权限这类**开发环境问题**，不是玩家向工具该诊断的对象；按长尾冻结政策不逐条写规则（每条约 +1.4pp，但会把"环境问题"混进崩溃诊断） |
| **E1–E4** 规则 DSL v2 | 动 `engine.py` 的匹配层，46 条规则全部要回归；建议一次只加"版本范围"一项并迁移一条规则做样板 |
| **F1–F3** watch / Server Doctor / 前兆检测 | 新产品面，不是补丁；要先定"只读、不假装实时"的边界 |
| ~~**G1** Pack Doctor 2.0~~ | 已完成：refmap 读目标 + 重叠桶 + 覆盖计数 + 依赖链（见上） |
| ~~**H1** 语料可复现包~~ | 已完成（见上） |
| ~~**H2** 兼容边分级~~ | 已完成（见上）；结论是 pair 层没有任何可用证据，产品化要等新语料 |
| **A6** VS Code 扩展 | 新仓库级工作量（L–XL） |
| ~~**I4** 前端拆分~~ | 已完成（见上） |
| **B5** 英文润色 | 44 条正文重写，主观判断多，建议与翻译一起做一次通读 |
| **C4/C5** 反馈入库、匿名统计 | C4 依赖真实反馈先积累；C5 是产品决策（默认关闭的统计要不要做） |

## 六、体验优化（2026-11-18，按"项目本身够不够好"这条线）

| 问题 | 改法 | 证据 |
|---|---|---|
| **页面里有一份手写的假诊断**：`index.html` 的结论区直接写死了"lithium 97%、120 秒"等一整块 DOM，未运行时也像算出来的结果 | 删掉整块 mock，改成"结论区是空的，因为这里只显示真的跑出来的结果"，并把示例交给真数据 | `index.html` 少 90 行、少 6 个 `sample.*` 文案键；浏览器实测：点示例前 `#out` 为空 |
| **示例要等引擎**：点「用示例试试」要等 Pyodide 下载完（约 9 s） | 构建期用同一引擎预生成 `sample-diagnosis.{zh,en}.json`；点击时先渲染它，引擎就绪后再用同结果替换；CDN 不可达时示例仍然可用 | 浏览器实测 **126 ms** 出结论（拦住 CDN 的情况下），不依赖网络 |
| **中文输出不折行**：旧的 `_wrap` 按空格切，中文没有空格，一段 117 字的说明变成 117 列宽的一行，是横幅宽度的两倍 | 按**显示列宽**折行（CJK 记 2 列）、允许汉字间断行、避头标点不回行首、数字与英文单词不断开 | `tests/test_render_width.py` 6 项：中英两种输出每行 ≤74 列 |
| **首屏到结论没有引导**：输出在 700px 以下，点完没有任何提示 | 渲染后把焦点与滚动落到结论标题，并给标题补 `scroll-margin-top`，避开吸顶导航 | 浏览器实测标题 top=176px，导航底 65px |
| 终端页眉被长路径与长根因挤爆；页脚没有下一步 | `source` 只显示文件名；根因/描述按列宽折行并缩进续行；结尾加 `--explain` / `--feedback` 两行提示 | 输出每行 ≤74 列（中英实测 0 行超宽） |

| **散文被说成"报告解析干净"** | 粘贴一段中文描述时，引擎照常返回 0 命中，页面却说"崩溃报告已解析"——对输入的错误陈述 | 新增"这看起来不是一份崩溃报告"卡片：给三种报告位置，不再显示环境信息与原始 JSON（那些是凭空造的）；状态行同步改为"这不是崩溃报告" | 浏览器实测：散文 → 专用卡片；真实日志 → 仍是"没有命中" |
| **3 行日志被判成"不是日志"** | `looksLikeLog` 要求 ≥5 行带时间戳，用户粘贴"崩溃前后几行"会被警告 | 阈值降到 2，并认 `Starting minecraft server version` / `Done (3.2s)!` | 实测：3 行服务端日志不再触发警告 |
| **9 MB 粘贴冻结 11.6 秒** | `MAX_BYTES` 只拦文件拖入，粘贴不受限，Pyodide 吃掉整个字符串后返回"没有命中" | `diagnose()` 先按 UTF-8 字节数检查上限，超了立刻提示 | 实测：9.4 MB 粘贴 → 立即提示"上限 8 MB，请贴报告本身" |
| **示例结果的说明放错位置** | 结论卡静态写着"示例…"，粘散文时也在；状态行又说"正在启动运行时" | 说明改成卡片注释，只在预生成示例上出现；删掉静态行与两个 dead key | 实测：散文无注释，示例有注释 |

| **CLI 的三种"不是报告"** | 空文件会打印一整页空诊断并退出 0；散文会被说成"没有命中规则"；30 MB 文件被说成"目录下没有报告" | 空文件/空 stdin 直接报错退出 2；散文在诊断后补一行"nothing diagnosable"，并计入失败；显式指定的文件不再按扩展名过滤；超过 8 MB 直接拒绝并说明"贴报告本身" | `tests/test_cli_input_states.py` 9 项；实测：空文件/散文/30.7 MB 全部退出 2 且信息准确，真实报告仍退出 0 |

| **Pack Doctor 的"什么都没检查"** | 传错目录时三种情况同一句话："no mods/ directory with .jar files"；只有坏 jar 的包输出"no contradictions"并退出 0；坏 jar 原因里文件名重复两遍 | 错误信息按情况区分（不存在 / 是文件 / mods 里没有 jar）；零个可读清单时打印"nothing to compare"并退出 2；去掉重复的文件名前缀 | `tests/test_pack_states.py` 8 项；实测：不存在 / 空 mods / 坏 jar 三种目录都给出各自的原因 |
| **Server Doctor 的空目录** | 空目录输出一大段"not checked"后退出 0，容易被当成"检查通过" | 保留 0（没东西可查不是错误），但把"没有崩溃报告"作为 INFO 风险放在最前，并把 logs/、mods/ 的缺失逐条列出 | 实测：空目录、只有日志的目录输出与退出码符合预期 |

| **--explain 第一次用** | 权重行最长 110+ 列；"无法解析"的 jar 名挤成一句 200 列；已经加了 `--explain`，页脚还在提示"用 --explain" | 权重行按词折行（长类名在自己的点号处断，如 `...reflection.` / `ReflectionUtil.hasMethodOverride`）；无法解析项一行一个；页脚在 explain 模式下去掉那一句 | 实测中英输出 **0 行超过 74 列** |
| **--timeline 丢掉异常正文** | 时间戳窗口只保留带时间的行，"java.lang.OutOfMemoryError" 这种没有时间戳的尾部行被计入"跳过"——恰好是崩在哪的那两行 | 尾部无时间戳的行按原样附在时间线后，标注"after the last timestamp, verbatim"；空文件改为报错退出 2；超过 8 MB 拒绝 | `tests/test_timeline.py` 新增 4 项；实测日志尾部异常能显示 |
| **Action 对坏输入照常出结论** | `--path` 指向散文/空文件/9 MB 日志时，Action 照样输出 Incident JSON（0 findings），workflow 会把"没问题"评论到 issue 上 | 与 CLI 共用同一组输入守卫：散文 → `found=false` 且安静退出；空文件 → 说明；超限 → 退出 2 让 workflow 变红 | `tests/test_action.py` 新增 3 项（28 项全过） |

| **批量模式只说"几个成功了"** | 一次诊断 20 个文件，结尾只有 `12/12 diagnosed (7 with findings)`——回答了"跑完没有"，没回答"先修哪个" | 结尾新增按**最严重规则**分组的清单（同规则的文件合并、超过 3 个折叠），只显示置信度 ≥60% 的嫌疑模组，并把"不是报告"与"没有规则命中"分开计数 | `tests/test_batch_summary.py` 6 项；实测 5 个文件分成 2 组 + 2 个失败，一眼看出先修 oom.heap |

### 性能排查（2026-11-19，结论是"先别动"）

对单份 266 模组报告做了 cProfile：0.375 s（剖析器本身约 1.7× 开销，实跑约 0.22 s），其中 PyYAML 解析规则 0.117 s（批量只在第一次付）、正则匹配 0.121 s（586 次调用）、解析报告 0.108 s。**没有一处值得为它改架构**：规则已按目录缓存，解析本身就是正则活。真正的成本在网页首次下载约 10 MB 的 Pyodide 运行时，而"换更小的构建"是依赖决策，不是本地能验证的优化——不在没有数据的情况下改它。

排查时从输出里发现两个真实缺陷并修掉（见 `tests/test_render_width.py` 15 项）：

| 问题 | 改法 |
|---|---|
| 上一轮的按列折行把长类名切成 `ReflectionUtil.ha` / `sMethodOverride` | 英文 token 只在自己的点号/斜线/美元号处断；中文仍按字断，避头标点不回行首 |
| 终端"root"行打印的是 80 字符的**分组键**，于是 `seconds (should be max 0.05)` 被截成 `seconds (shoul`，看起来像报告里有错别字 | 新增 `ExceptionInfo.headline`（完整首行，按词在 160 字处收尾并加省略号）用于显示；`signature` 保持原样继续做分组键 |

### 一份摘要，四个出口（2026-11-19）

上一轮只修了终端：根因显示从 80 字符的分组键 `signature` 换成完整首行 `headline`。这一轮把同一条判断推到所有出口，并顺手修了 Markdown 这个“贴进 issue”的成品：

| 出口 | 之前 | 现在 |
|---|---|---|
| JSON `summary.root_cause` | 80 字符截断（`seconds (shoul`） | 完整首行；`signature` 继续只做分组键 |
| Markdown 表格 | 同一段截断 + 整个本地路径 | 完整首行；来源只显示文件名 |
| Markdown 修复列表 | 每项都写 `1.` | `1.` `2.` `3.`，源码里也能读 |
| 网页 `cause-raw` | JS 在完整字符串后硬加 `…`，把没截断的文本标成截断 | 完整文本留在 DOM，用 CSS 两行截断——复制得到的是整句 |
| Markdown 反引号 | 消息里有反引号时提前闭合代码段 | `_md_code` 改用双反引号包裹，且不再把反斜杠翻倍（Windows 路径不会被写成 `C:\\\\Users`） |

测试：`tests/test_markdown_shape.py` 5 项（整行、文件名、编号、反引号、JSON 摘要）；预生成示例因摘要变化自动过期，由 `test_web_sample_diagnosis` 拦下，重新生成后才通过。

### 实时监视与"有洞的句子"（2026-11-19）

`mcd --watch` 是最接近"真的在用"的入口，用真实管道测了一次，发现三个问题：

| 问题 | 证据 | 改法 |
|---|---|---|
| 管道里看不到输出 | 子进程接管道后运行 5 秒、写入两次崩溃，输出只有 65 字节的启动横幅——`print` 到管道是块缓冲，杀掉进程还会丢掉缓冲 | 默认 emitter 每次诊断 `flush=True`；实测同样场景立刻出现完整诊断 |
| 连续两次崩溃粘在一起，不知道哪次是哪次 | 两次诊断之间只有一个空行 | 每次诊断前加一行本地时间 + 触发它的那一行日志（截断到 100 列） |
| 日志被轮转后，旧文件的证据混进新崩溃 | `Tail` 检测到文件变短只重置偏移，窗口（ring）还留着上一个文件的 2000 行 | `Tail.rotated` 标记，watcher 清空窗口；测试构造"先 OOM 后轮转为 watchdog"，第二次诊断里不再出现 `oom.heap` |

顺带修了一个从模板层冒出来的问题：没有 System Details 的日志里，`oom.heap` 会打印 **"Max heap was  MiB at crash time."**——占位符为空，句子中间留了个洞。

- 引擎新增可选片段：`{{#key}} … {{/key}}`，值存在才保留，否则整段消失；未闭合的标记在渲染时被剥掉，并在加载期点名（`unbalanced conditional block`）
- 迁移了 4 段文案（`oom.heap` / `oom.save-time` 的中英），每句独立，不会因为缺一半数据留下悬空标点
- 测试：`tests/test_rule_templates.py` 6 项，其中一项把 46 条规则跑遍 6 份地面真值，断言输出里不出现 `{{`

### 文案空洞扫描（2026-11-19）

把 46 条规则的标题、说明、修复项（中英各一套，共 200+ 段）全部用"报告字段全空"的上下文渲染一遍，找三类痕迹：占位符残留、连续空格、空括号。

第一遍命中 25 处，绝大多数来自同一类：日志里没有 System Details 时，`{{mc_version}}` / `{{loader}}` / `{{suspect_top}}` 被替换成空串，句子中间就出现 `for  / fabric`、`支持 Minecraft 。`、`(attribution confidence )`。

处理分两层：

1. **可选片段**（上一轮）：真正成句的缺失用 `{{#key}} … {{/key}}` 包起来，整句消失
2. **收尾清理** `_tidy()`：删除空括号 → 去掉标点前空格 → 去括号内空格 → 合并连续空格（顺序有讲究：先删括号，否则留下双空格）

结果是 0 处。测试 `test_no_rendered_copy_has_a_hole` 把这条守住：只要新增规则在缺字段时留下双空格、空括号或 `{{`，就会失败并点名规则与字段。

这条测试也解释了为什么清理放在渲染层而不是逐条改文案：规则会继续增加，闸门要能跟着新规则一起生效。

### 网页无障碍与键盘操作（2026-11-19）

用无头浏览器逐项检查，而不是看代码下结论：Tab 顺序、焦点环、对比度（oklch 经 canvas 转成 sRGB 实测）、跳转链接、landmark。

| 问题 | 证据 | 改法 |
|---|---|---|
| 跳转链接是坏的 | 键盘 Tab 到「跳到正文」，回车后 `document.activeElement` 是 `BODY`，滚动位置仍是 0——等于什么都没发生 | `<main id="main" tabindex="-1">`；`#main:focus` 去掉整列焦点框 |
| `#out` 的 `aria-label` 被忽略 | `aria-label` 挂在没有 role 的 `div` 上，读屏不会把它当区域 | 加 `role="region"`，现在 landmark 计数从 0 变 1 |
| 语言按钮默认是 submit | 现在没有 form 所以无害，但语义错误，将来包进 form 就会提交 | `type="button"` |

核对通过、无需改动的项：

- 焦点环：`#log` 3px、按钮 2px 实线，全部可见
- 对比度：正文 16.5:1、次要文字 11.3:1、说明 7.4:1、FATAL 徽标 6.6:1（阈值 4.5）
- 纯键盘流程：Tab 到「用示例试试」→ 回车 → 焦点落在结论标题 → 下一个 Tab 到「结论不对？」
- 图片都有 alt；状态行是 `role="status" aria-live="polite"`；textarea 有 aria-label

`tests/test_web_a11y_markup.py` 6 项把能在 diff 里悄悄退化的部分钉住（跳转目标可聚焦、语言按钮类型与 `aria-pressed`、`#out` 的 region、状态行 live、alt、按钮可访问名）。

### 系统偏好、窄屏与构建卫生（2026-11-19）

| 项 | 实测 | 结论 |
|---|---|---|
| `prefers-reduced-motion: reduce` | 入场动画仍是 420ms，全站没有一条 reduce 规则 | 把三个时长 token 归零；再测动画时长 420ms → 0.01ms，650ms 后元素 opacity 全为 1（不是"关掉动画后内容不出现"） |
| `prefers-color-scheme: light` | `color-scheme: dark` 已声明，textarea 背景透明、光标为琥珀色、滚动条深色 | 无需改动 |
| 320px 宽 | `.statement` 用了 `text-wrap: nowrap`，在 288px 列里撑到 329px，最后两个字跑出照片 | 改 `balance`，320 无横向溢出（`<pre>` 仍按设计内部滚动） |
| 200% 文字 / 720px 布局 | 结论卡 672px、无横向溢出 | 无需改动 |

构建侧发现两件事：

1. 手动检查留下的截图被 `build_web` 当成了发布文件（520 KB，仅因超出总预算才暴露）。现在 `web/` 顶层文件是**白名单**，不在 `SHIPPED` 里的文件直接让构建失败并点名。
2. `moment.js` 是死代码：它在找 `[data-count]`，而这个属性只属于早已删掉的那份假诊断。1.3 KB 加一个 `defer` 请求什么也没做——删除，并加测试防止被"恢复"。

测试：`tests/test_web_css_guards.py` 3 项、`tests/test_build_hygiene.py` 3 项。
