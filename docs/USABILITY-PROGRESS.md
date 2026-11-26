# mc-crash-doctor 可用性实施进度

2026-11-22 起｜负责人：CodeBuddy｜对应方案：docs/USABILITY-PLAN-2026-11-22.md
本文件记录**实际执行**：改了哪些文件、跑了什么命令、看到什么结果、还差什么。未执行的检查写"未运行"，不写"通过"。

## 基线（P0.1 固定比较对象）

| 项 | 值 |
|---|---|
| 本地 HEAD | `b88dca6`（perf(parser): skip platform probes…） |
| 公开 CI 提交 | `41f3fcc`（origin/main，docs(readme)…） |
| 工作副本 | 86 项改动：35 个已跟踪文件修改（+2428/−434），51 个未跟踪文件 |
| 候选树自检 | 3.12：1193 passed, 1 skipped；3.11（uv 解释器 + `[pretty,test]` 同等依赖）：1193 passed, 1 skipped |

未提交改动全部保留；未 reset/clean、未提交/推送/打 tag。

### 公开 CI 失败的复现与归因

在临时 worktree 里检出 `41f3fcc`（`git worktree add tmp/public-41f3fcc 41f3fcc`），用同一套依赖跑 3.11：

```
3 failed, 740 passed, 42 skipped in 26.71s
  test_index.py::test_row_count_matches_crash_text_count
  test_rule_drafts.py::test_every_candidate_fixture_resolves
  test_rule_lifecycle.py::test_snapshot_is_current_for_this_corpus_revision
```

三个失败同源：`corpus/index.jsonl` 有 454 行，但 `corpus/github/**/*.crash.txt` 在公开树里是 **0 个文件**（该目录是抓取的用户内容，未入库），候选工作区里有 **454 个**。因此：

- 不是 Python 版本差异，也不是夹具内容本身错误；
- 是"公开树缺少私有语料，测试却按有语料来断言"；
- 结论：需要把公开 PR 门禁与私有扩展门禁分开，缺数据时显式报"未运行"，而不是失败或静默 skip。

## P0.3（先行部分）公开/私有门禁分离

新增/修改：

- `tests/_corpus_gate.py`：语料检测、跳过原因归类、一行汇总文案
- `tests/conftest.py`：注册 `private_corpus` 标记；缺语料时给这些用例加 skip；会话结束打印 `extended gate: RAN/NOT RUN`；`MCD_REQUIRE_CORPUS=1` 时只要有语料用例被跳过就把退出码改成 1
- `tests/test_index.py`、`tests/test_rule_drafts.py`、`tests/test_rule_lifecycle.py`：三条依赖语料正文的测试加 `@pytest.mark.private_corpus`
- `tests/test_corpus_gate.py`：3 项，钉住两种汇总文案与跳过原因归类

证据：

| 场景 | 命令 | 结果 |
|---|---|---|
| 公开树（无语料） | 把上述文件复制进 worktree 后跑全量 | 740 passed, 45 skipped, **exit 0**，打印 `extended gate: NOT RUN … 38 corpus case(s) skipped` |
| 公开树 + 强制 | `MCD_REQUIRE_CORPUS=1 pytest tests/test_index.py` | **exit 1**，汇总行同上 |
| 候选树（有语料） | 全量 | 1193 passed, 1 skipped，打印 `extended gate: RAN -- 454 crash texts on disk` |

这一步解决的是"CI 红且看不出原因"和"42 个静默 skip 假装绿"两件事；没解决的是：公开树依然只有 740 条用例覆盖，语料门禁的真实通过仍需私有 CI 设置 `MCD_REQUIRE_CORPUS=1`。

## 待办（按方案顺序）

- P0.2 发布链：release.yml 的 `--no-deps` 漏装 PyYAML；Release 与 PyPI 各自重建产物；dispatch 能否上传；三条路径（分支演练/正确标签/错误标签）本地演练
- P0.3 余下：`MCD_DRIFT_FULL=1` 的 110/454 与 106/454 口径、连续两次生成一致性、CI 执行 lint/覆盖率/契约检查
- P0.4 产品承诺：97% 的表述、157/214 与 112/143 的含义、网页/README/assessment 同步
- P1–P3 见方案，尚未开始

## P0.2 发布链（本地演练完成，远端未验）

改动：

- `.github/workflows/release.yml`：改成 门禁 → 构建一次 → 验证 → 挂 Release → 用**同一次构建**的产物发布 PyPI。
  - 删掉旧的 `pip install --no-deps dist/*.whl`：PyYAML 是硬依赖，那个 venv 根本 import 不了 mcd，"通过"只是没检查。
  - publish job 从本次运行的 artifact 取包，先 `sha256sum -c SHA256SUMS` 再上传。
- `.github/workflows/publish.yml`：改为**只能演练**的 workflow_dispatch（构建 + 验证 + 上传 artifact，无任何上传 PyPI 的路径）。原文件里 `dry_run=false` 的分支派发可以直接发布。
- `tools/verify_release.py`（新）：装进临时 venv（带依赖）、检查导入来自 site-packages、版本、tag、规则 id 对照 `corpus/rule-lifecycle.json`、诊断、timeline、pack 入口，写 `SHA256SUMS`。
- `tests/test_verify_release.py`：5 项（tag 相等、规则集来自清单、空 wheel 被拒、缺产物报错、sha256）。

本地证据（`python -m build --no-isolation --outdir dist-verify`）：

| 路径 | 命令 | 结果 |
|---|---|---|
| 正确标签 | `python tools/verify_release.py dist-verify --sums --tag v0.1.0` | `release verification: OK`，exit 0；46 rules installed = 46 expected；sha256 已写 |
| 错误标签 | 同上 `--tag v0.2.0` | exit 1，`tag 'v0.2.0' != version '0.1.0'` |
| 分支演练 | 构建 + `verify_release.py`（无 tag） | OK；与 release 走同一脚本，没有上传入口 |

未验证：GitHub Actions 上的实际运行、PyPI trusted publisher、`actions/upload-artifact` 的行为。这些需要远端权限。

## P0.3 数字可重建

- 用生产脚本重建：`tools/coverage_report.py`、`tools/suggest_rules.py`。当前口径：**348/454 = 76.6%**，未覆盖 **106**（旧文件写的是 344/454、110）。
- 连续两次生成的差异只有 `generated_at` 与 `elapsed_seconds`（diff 证据在本次会话），其余字节一致；`MCD_DRIFT_FULL=1 pytest tests/test_rule_candidates.py` 现在 14 passed（此前因 110≠106 失败）。
- 文档数字随机器值同步：README 中英、ROADMAP、docs/ASSESSMENT、docs/AUDIT（加"2026-11-22 复算说明"保留历史）、docs/DECISION-longtail-freeze、docs/RELEASE-0.1.0；`tests/test_doc_numbers.py` 15 passed。
- CI：`tests.yml` 新增 `full-gates` job（3.12）跑 `bash run_tests.sh`，即 lint/覆盖率/文档数字/契约八道门禁；此前 CI 只跑 pytest 子集。

## P0.4 产品承诺

| 原来 | 现在 |
|---|---|
| assessment / AUDIT / RELEASE 把 112/143 = 78.3% 写成"归因 top-1" | 改为**模组仓诊断率**，并注明不是"指对了模组"；可计分归因只有 7 例（5 对 / 1 错 / 1 不选） |
| 网页示例 "置信度 97%" | 改 "证据强度 97%"，卡片补一句：加权分数，不是校准过的「猜对概率」 |
| README 首段 "lithium, 97% confidence" | "lithium — evidence strength 97%"；中文同步 |

## 人工/远端清单（未做，需要人或权限）

1. 在 PyPI 配置 trusted publisher（pypi environment），否则 publish job 会在 OIDC 交换处失败（设计如此）。
2. 推 tag 前确认 `mcd.__version__` 与 tag 一致（verify_release 会拦，但 CI 未跑过）。
3. 私有 CI 上设置 `MCD_REQUIRE_CORPUS=1`，否则扩展门禁仍只打印 NOT RUN。
4. 3.9 / 3.13 解释器本机没有；3.11 与 3.12 已跑同一套依赖（1193 passed）。
5. 真实用户试用（5 位玩家 / 服主 / 维护者）与 P1–P3 的其余条目。

## 收口（本轮最后一次全量校验）

- `bash run_tests.sh`：**8/8 全绿**，1201 passed, 1 skipped，覆盖率 89.2%
- 3.11（uv 解释器 + 同等 extras）：1193 passed, 1 skipped（加新增测试前）
- `ruff check mcd/ tools/ tests/`（0.17.6）：**All checks passed**
  - 新 CI 的 lint 门禁第一次跑就暴露 5 个既有问题，已修：`mcd/metadata/jars.py` 缺 `Path` 导入（F821）、`expect.py` 的 `__all__` 指向不存在的 `FIXTURE_ROOTS`（F822）、render 循环未用变量、两个测试里的死变量/未用导入
- 工作副本：102 项改动（未提交）；`tmp/public-41f3fcc` worktree 保留，可用 `git worktree remove tmp/public-41f3fcc --force` 删除（里面只有我为复现 CI 复制的测试文件）

未运行的检查（不要当成通过）：GitHub Actions 实际运行、PyPI trusted publisher、3.9/3.13 本机矩阵、真实用户试用、P1–P3 全部条目。

## P1（部分）玩家第一次就能用：先拒绝对的东西

本轮做了 P1 里最小、最可验证的一块——**两类常见输入不再被"假装诊断"**，以及 **97% 的表述统一**。

| 输入 | 之前 | 现在 |
|---|---|---|
| JVM `hs_err_pid*.log` | 打印空诊断，先说"没有规则命中这份报告"，再说"看起来不是报告"，自相矛盾 | CLI 退出 2、不打印诊断，给四行下一步（更新显卡驱动 / 移除带原生库的模组 / 只发 Problematic frame 那一行）；网页同样拦截并给卡片级提示 |
| 只有 `exit code: 1` | 同上 | 说明退出码只说明进程死了，指到 `logs/latest.log`；网页同样拦截 |

实现：新增 `mcd/input_kind.py`（CLI 与网页共用同一组形状判断），CLI 的 `_looks_like_report` 改为委托它；网页 `validate()` 增加两个分支与 `val.hsErr` / `val.exitCode` 双语文案。

网页文案统一：hero、结论区导语、规则区标题、结果卡标签全部从"置信度"改为"证据强度"，卡片补一句"加权分数，不是校准过的猜对概率"；`web/index.html` 里已无"置信度"。

证据：

- `python -m mcd hs_err_pid1234.txt` → exit 2，stderr 以 `this is a JVM fatal-error log` 开头，stdout 0 字节
- `printf 'exit code: 1' | python -m mcd --stdin` → exit 2
- 浏览器直接调用 `validate()`：hs_err → `val.hsErr`，退出码 → `val.exitCode`，真实报告 → 放行，散文 → 原有 warning
- `tests/test_input_kind.py` 6 项、`tests/test_web_copy.py` 4 项

P1 尚未做：首页"去哪找文件"入口（默认启动器/Prism/Modrinth/服务端）、结果的四段式顺序、并列/仅共现时的补充材料指引、`performance` 四项计时与 Worker 评估、隐私行为测试。

## P1 继续：先回答"文件在哪"

在粘贴框下方加了一个折叠块（原生 `<details>`，无需 JS、键盘可用）：

- 顺序按方案：先 `crash-reports` 里最新的 .txt，没有再看 `logs/latest.log`
- 四个入口：官方启动器（Windows 路径 + macOS/Linux 备选）、Prism、Modrinth App、服务端
- 中英双语；320px 下 0 横向溢出；`details` 展开后状态行与路径之间留 16px

顺带修了一个**既有**的样式 bug：`paintStatus()` 里 `el.className = STATUS.kind` 会把基础类 `status` 一起覆盖掉，导致第一次刷新状态后：

- 状态行退回正文字号与颜色（看起来像路径列表的一部分）
- `.status.ok` / `.status.err` 永远匹配不上（选择器要求两个类）

改成保留基础类；实测 margin 从 0 变 16px，状态行恢复小号弱化颜色。`tests/test_web_copy.py` 增加 4 项（where 块、反斜杠不重复、双语四个入口、状态类保留），共 8 项。

预算按实际增长调整并写明理由：app.js 64→68 KB（两条拒绝路径 + 双语指引），总载荷 370→385 KB（现值 367.9 KB）。

## P1 结果顺序：什么 → 依据 → 先做什么 → 怎么验证/撤回

结论卡按阅读顺序重排（浏览器实测 DOM 顺序）：

```
致命/根因 → 标题 → 元信息 → 原始异常行 → 最可能的原因 + 证据强度
→ 依据（栈帧）→ 先做这两步 → 怎么算修好了 / 怎么撤回 → 操作按钮
```

几个具体决定：

- **"依据"有了标签**：原来是一串无标题的 bullets，读起来像第二条意见；现在标明它是证据，且在"先做什么"之前
- **验证看哪一行**：用 findings 的**最后一条**证据（如 `single server tick took 120.00 seconds`），不是第一条 `java.lang.Error`——后者每个 Java 崩溃都有，拿来判断"修好没有"没有意义
- **撤回写清楚**：只改一处就改回去（版本/`-Xmx`/装回模组），并明说工具不会改任何文件
- 没有命中时不出验证块（没有可验证的"这一步"）

代价与证据：卡片高度 715 → 924 px（1440×1000 仍在一屏内）；`tests/test_web_copy.py` 增加 3 项（顺序、双语标签、用最后一条证据），共 11 项。

预算：app.js 67,182 / 68,000（余量 818 B）。再加卡片文案需要先压缩或调预算。

## P0.1 收口：公开 CI 转绿（2026-11-22）

推送后第一次运行是红的，三个原因逐个定位：

| 现象 | 根因 | 修法 |
|---|---|---|
| 3.11 / 3.13 pytest 全红 | 提交时 .gitattributes 把两个规则包从 CRLF 转成 LF，而 wheel 与 manifest 是本机 CRLF 版本构建的，digest 在 CI 必然不匹配 | 用 LF 源码重建 wheel + manifest 并提交 |
| 3.9 卡在 "Set up Python 3.9" | 24.04 runner 没有 3.9 的安装包 | 矩阵固定在 ubuntu-22.04，保留 >=3.9 的声明 |
| 3.9 pytest 12 个 TypeError | 测试用了 Path.write_text(newline=)（3.10+） | 改字节写入；本机 3.9 实测 1215 passed |
| full-gates 的 gate 4/8 | 全新 clone 没有 tmp/（gitignored），pytest --basetemp 不创建缺失的父目录，176 个 tmp_path 测试报 FileNotFoundError | run_tests.sh 开头 mkdir -p tmp；全新 clone 复跑 8/8 通过 |

为了让失败点可读（GitHub 的 job 日志要仓库管理员权限），run_tests.sh 现在把每道失败门禁和每个 FAILED 测试写成 ::error:: 注解——公开 API 能读。

最终：b4091fa 上 4 个 job 全绿（3.9 / 3.11 / 3.13 / full-gates），Pages 同步成功。

推送方式改为 SSH（公钥在这台机器上，用户一次性授权），后续改动由我直接推送，不再需要用户手动操作。

## P1 继续：分数接近时不给假答案

结论卡原来只显示得分最高的那个模组，即使第二名只差 1 分。现在：

- 前两名分差 **< 20 个百分点** → 显示「两个模组分数接近」，写清楚两人各多少分，并给出二分法：**一次只禁一个、每次重启复现**；一次删一批就不知道是谁了
- 有 finding 但没有定位到模组 → 说明这条规则只到问题类型，**不要为此删模组**
- 单选题照旧只显示一个模组，不加提示

浏览器实测四种情况：0.97 vs 0.90 显示并列提示；0.97 vs 0.40 不显示；无 suspect 显示提示；预生成示例（单个模组）不显示。

测试：`tests/test_web_copy.py` 新增 2 项（阈值与文案成对、卡片拿到全部 suspects），共 13 项。预算 app.js 68 → 70 KB，总载荷 372 KB / 385 KB。

## 构建产物可复现（2026-11-22）

发现两个跟行尾/时间戳有关的坑，都会让“同一份源码”产出不同字节：

1. `python -m build` 用 setuptools 打包时把文件 mtime 写进 zip，连续两次构建的 wheel 哈希不同（实测 `e3926600…` vs `eafa362e…`），每次构建都会把仓库弄脏
2. `tools/make_web_sample.py` 用 `write_text` 写样例，Windows 下是 CRLF，而仓库里是 LF

修法：构建时设置 `SOURCE_DATE_EPOCH=315532800`（zip 能表示的最早时间），样例改字节写入。现在连续两次 `tools/build_web.py` 产出的 wheel 哈希一致（`508b3bb7…`），`web/sample.js` 也稳定为 LF。
