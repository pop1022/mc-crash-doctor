# 0.1.0 发布清单（E3 / E5）

> 2026-11-07。`publish.yml` **从未运行过**：代码侧就绪，卡在 PyPI 网页端一次性配置。
> 本文把"需要老板做的"和"我已经做完并验证过的"分开列，照着做即可发版。

## 一、需要你做（约 5 分钟）

在 PyPI → Your projects → Publishing → **Add a pending publisher**，五个字段必须
与 `.github/workflows/publish.yml` 顶部完全一致：

| 字段 | 值 |
|---|---|
| PyPI project name | `mc-crash-doctor` |
| Owner | `pop1022` |
| Repository | `mc-crash-doctor` |
| Workflow name | `publish.yml` |
| Environment | `pypi` |

任一字段不符，OIDC 交换会在**上传之前**失败（这是设计好的失败模式，不会传坏包）。

另：本机没有 `gh` CLI，无法从这台机器触发 `workflow_dispatch`。在 GitHub
网页端 Actions → publish → Run workflow，勾选 `dry_run=true` 先跑一次。

## 二、我已经做完并验证过的

| 项 | 证据 |
|---|---|
| wheel 能构建，且**内含 3 份规则 YAML** | `python -m build --wheel`；`zipfile -l` 数出 3 个 `.yaml` |
| 干净 venv 安装可用 | 新建 `tmp/venv` → `pip install` wheel → 从**中性目录**确认 `mcd.__file__` 指向 site-packages；`--version` / `--rules`（44 条）/ 诊断 / `--pack` / `--explain` 全部跑通 |
| 七道门禁 | `bash run_tests.sh` → ALL GATES PASSED |
| 指标与文档一致 | `tests/test_doc_numbers.py`（门禁 [7]）按 JSON 反查文档数字 |
| 网页版真实浏览器验证 | `tools/verify_web_e2e.py` → **34/34 PASS / RESULT: VERIFIED**（本地与公网 Pages 各一次） |
| 网页抗 CDN 屏蔽 | 屏蔽 jsDelivr 主域名后走 fastly 镜像仍能"引擎就绪"；全屏蔽时列出三个 URL 供定位 |
| 发布政策已由机器强制 | `corpus/blind-eval.json` 的 `ci95.quotable_as_rate.blame_error=false` |

干净安装这一步我踩过一次坑并纠正：第一次在仓库根目录跑，`sys.path` 把仓库的
`mcd/` 放在了安装包前面，测的其实是仓库代码。换到 `tmp/` 后 `mcd.__file__` 才
指向 venv，那次结果才算数。

## 三、发布政策（E5 选 B：没有 PAT，就用 7 份样本）

**可以对外引用**（n ≥ 30，机器已算 Wilson 区间）：

- 盲测诊断率 **156/216 = 72.2% [66%, 78%]**
- 语料诊断率 **344/454 = 75.8%**（全语料，不是盲测）
- 根因抽取 215/216 [97%, 100%]；mod 仓 top-1 112/143 [71%, 84%]

**不可以引用**：甩锅率 1/7 = 14%。样本 n=7，Wilson 区间 [3%, 51%]，
宽到没有信息量；`quotable_as_rate.blame_error=false` 会在脚本里挡住它。
README / PyPI 长描述 / release notes 一律不写这个数字。

`docs/DECISION-pat.md` 是两个分支的完整成本对比；以后补了 PAT，4h 内可把 B
升级成 A，不需要重排任何任务。

## 四、发版动作顺序

1. 网页端 `workflow_dispatch` + `dry_run=true` → 看 build/gates 是否在 Ubuntu 上也绿。
2. 确认 dry_run 里 artifact 同时有 sdist 与 wheel，且 wheel 内含 3 份 YAML。
3. `git tag -a v0.1.0 -m "0.1.0"` → `git push origin v0.1.0`（触发真发布）。
4. 发布后另起一个干净 venv：`pip install mc-crash-doctor` → `mcd --version` →
   `mcd --rules` 应为 44 条 → 诊断一份 fixture。
5. 把 CHANGELOG 里 `[Unreleased]` 改成 `[0.1.0]` 并补日期。

## 五、遗留风险

- **OIDC 从未实跑**：dry_run 是唯一能在不上传的前提下验证 workflow 的手段，必须先做。
- **tag 触发条件**：`v*` 会匹配任何以 v 开头的 tag，推之前确认没有误打的 tag。
- **Pages 与 PyPI 是两条独立链路**：网页版已上线并能验证，不代表 publish.yml 能跑。
