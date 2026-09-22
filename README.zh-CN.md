# mc-crash-doctor

**诊断 Minecraft 崩溃报告与日志：给出根因、肇事模组和修复方法。**

把你 200 模组服务器的崩溃报告贴进来，得到的是「lithium，97% 置信度，栈帧 #32」，而不是 1500 行堆栈。

```
  platform : forge 47.4.16
  version  : Minecraft 1.20.1 | Java 21.0.12
  heap     : 6965/8192 MiB (85% used)   mods: 266
  root     : java.lang.Error: ServerHangWatchdog detected that a single
             server tick took 120.00 seconds

  SUSPECT MODS
  ● lithium    97%
      - stack frame #32: me.jellysquid.mods.lithium.common.reflection
        .ReflectionUtil.hasMethodOverride (line 13)

  [1] FATAL  Server hung for 120.00s and was killed by the watchdog
      单次 tick 耗时 120 秒（上限 60）。看门狗杀掉了 JVM，所以这份报告
      显示的是「卡在哪里」，不是「谁抛的异常」。
      fix:
        1. 看栈顶几帧——第一个非 vanilla 的类通常就是元凶。
```

[English](README.md) · [为什么做这个](#为什么做这个) · [安装](#安装) · [用法](#用法) · [加规则](#加规则)

---

## 为什么做这个

[mclo.gs](https://mclo.gs) 很好用，我们也在用。但它的引擎（[aternosorg/codex-minecraft](https://github.com/aternosorg/codex-minecraft)，MIT）**对内存与性能类故障的规则数为零**。

我们把它的代码整个读了一遍来确认：

| | 实测 |
|---|---|
| Problem 类 | 69 个 |
| 消息文案 | 96 条 |
| 命中 `memory\|heap\|oom\|watchdog\|hang\|gc\|xmx` | **0 条** |

（4 处原始命中全是假阳性——`c**hang**e-motd-solution` 里含 "hang"。）它的 201 份测试语料里根本没有内存类崩溃。它的 Forge 规则只覆盖**加载期**（缺依赖、重复模组、版本不符）；遇到 `Ticking entity` 只会说「删掉这个实体」，从不告诉你**是哪个模组干的**。

而这些恰恰是模组服最常见的死法：

- **堆内存 OOM** —「平时玩着没事，一 `stop` 就崩」（这不是内存泄漏，见[规则](mcd/rules/builtin/memory-performance.yaml)）
- **ServerHangWatchdog** — 单次 tick 耗时 120 秒，JVM 被杀，报告只显示卡在哪
- **mixin 冲突** — 两个模组改同一个类
- **Metaspace 溢出** — 调大 `-Xmx` 完全没用

mc-crash-doctor 专攻这一类，并交叉索引三个独立的溯源信号来指认模组。

## 肇事模组定位靠什么

崩溃报告里有三处携带模组溯源信息。三个都用上，才能把「崩了」变成「模组 X，97%」：

1. **Mixin 归属** — `pl:mixin:APP:create.mixins.json:Class from mod (create)`。mixin 崩溃几乎都是 mixin 所有者的锅。**最强信号**。
2. **模组栈帧** — 根因调用栈里第一个非 vanilla、非加载器的类，再用报告自带的 Mod List 反查（266 个模组照样全解析）。
3. **Jar 名** — `~[some-mod-1.2.3.jar%2312!/:1.2.3]`。

得分归一化成置信度。当两个模组得分相差在 20% 以内时，它会**如实说明**而不是硬猜：

```
  ● cupboard         50%
  ● l2screentracker  50%
  ! 'cupboard' 与 'l2screentracker' 得分几乎相同——这更像是两个模组的
    交互问题，而非某一个坏了。请逐个移除以确认。
```

## 安装

```bash
pip install mc-crash-doctor              # CLI + 引擎
pip install "mc-crash-doctor[pretty]"    # + rich 彩色终端输出
```

Python 3.9+。唯一的硬依赖是 PyYAML。

源码安装：

```bash
git clone https://github.com/YOURNAME/mc-crash-doctor
cd mc-crash-doctor
pip install -e ".[pretty]"
```

## 用法

```bash
# 单个崩溃报告
mc-crash-doctor crash-2026-09-08_22.42.32-server.txt

# 整个服务端目录（自动先找 crash-reports/，再找 logs/）
mc-crash-doctor /path/to/server

# mclo.gs 链接——自动拉取
mc-crash-doctor --url https://mclo.gs/6cWndzQ

# 管道输入
cat latest.log | mc-crash-doctor --stdin

# 贴进 GitHub issue / Discord
mc-crash-doctor report.txt --markdown

# 机器可读
mc-crash-doctor report.txt --json

# CI 门禁：出现 ERROR/FATAL 时退出码为 1
mc-crash-doctor --dir ./server --exit-code
```

作为库使用：

```python
from mcd import diagnose

rep, findings, triage = diagnose("crash-report.txt")

print(rep.system.loader, rep.system.xmx_mib)     # forge 2048
print(rep.root_cause.signature)                   # java.lang.OutOfMemoryError: ...
for s in triage.suspects:                         # 排名后的嫌疑模组
    print(s.modid, f"{s.confidence:.0%}", s.reasons[0])
for f in findings:
    print(f.severity.name, f.rule_id, f.title)
    for fix in f.fixes:
        print("  →", fix)
```

## 已覆盖的故障类型

两个规则包共 25 条规则。规则是 YAML——加一条不用写 Python。

| 规则包 | 规则 |
|---|---|
| [`memory-performance.yaml`](mcd/rules/builtin/memory-performance.yaml) | 堆 OOM · 保存时 OOM · Metaspace OOM · GC overhead · ServerHangWatchdog · tick 超时 · Java 类版本 · mixin 应用失败 · mixin 目标缺失 · ticking entity/block entity · 渲染崩溃 · OpenGL/驱动 · 磁盘满 · 区块文件损坏 |
| [`mod-loading.yaml`](mcd/rules/builtin/mod-loading.yaml) | 缺依赖（Forge 1.13+/1.12 及更早、Fabric/Quilt）· 模组集不兼容 · MC 版本不符 · 重复模组 · 加载期致命错误 · 配置解析失败 · 缺 coremod/前置库 |

平台识别覆盖 Forge、NeoForge、Fabric、Quilt、Paper、Purpur、Folia、Spigot、CraftBukkit、Glowstone、Magma、Mohist、Arclight、CatServer、Velocity、Waterfall、BungeeCord、Bedrock、PocketMine、Geyser 及主流启动器——在 201 份回归语料上 **100% 准确**。

## 准确率

由 [`tests/eval_parser.py`](tests/eval_parser.py)（对照上游期望值）和 [`tests/test_e2e.py`](tests/test_e2e.py)（对照真实报告）实测：

```
platform accuracy : 201/201 = 100.0%
version accuracy  : 176/177 =  99.4%
ground truth      : 6/6 matched
```

地面真值集是 6 份来自 266 模组 Forge 1.20.1 服务端的真实报告（4 次堆 OOM、2 次看门狗击杀）。测试同时断言**不该触发**的规则——例如 `oom.save-time` 不能在栈里没有区块序列化路径的报告上触发。判错会把用户引向排查一个根本不存在的内存泄漏。

唯一的版本误判来自语料本身自相矛盾：文件里同时有 `1.8.8` 启动行和相隔三小时的 Magma 横幅 `(MC: 1.12.2)`。我们采信软件自己的横幅。

## 加规则

规则是声明式的，所以新故障类型就是一个 YAML PR：

```yaml
rules:
  - id: my.new-rule
    title: "Something went wrong with {{cap:text:1}}"
    severity: fatal          # fatal | error | warning | hint | info
    priority: 25             # 数字小的先跑
    confidence: 0.85
    tags: [my-category]
    when:                    # 各键之间 AND；同一键内多个条目 OR
      exception: ["java\\.lang\\.IllegalStateException"]
      text: ["my mod said ([\\w\\-]+) was broken"]
    explanation: >-
      发生了什么、为什么。可用占位符 {{mc_version}}、{{loader}}，
      以及上面捕获组得到的 {{cap:text:1}}。
    fixes:
      - "先做第一件事。"
      - "再做第二件。"
    suspects_from: [frame_mods, mixin, jar]
```

可用占位符：`{{description}} {{loader}} {{loader_version}} {{mc_version}} {{java_version}} {{java_major}} {{xms_mib}} {{xmx_mib}} {{heap_used_mib}} {{heap_max_mib}} {{mod_count}} {{os}} {{time}} {{root_exception}} {{root_message}}`，以及正则捕获 `{{cap:<key>:<group>}}`。

`when` 支持的键：`description exception exception_msg exception_any caused_by frame frame_top jar mixin text`（正则）、`loader kind`（精确匹配）、`java_major max_heap_mib mod_count`（`{lt,le,gt,ge,eq}`）、`has_mod not_has_mod`（通配符）。

不用安装就能测你的规则：

```bash
MCD_RULES_PATH=./my-rules mc-crash-doctor report.txt
mc-crash-doctor --rules      # 列出已加载的全部规则
```

## 语料与评测

两套语料支撑测试：

- **`corpus/aternos/`** — 来自 [aternosorg/codex-minecraft](https://github.com/aternosorg/codex-minecraft)（MIT）的 201 份真实日志 + 期望输出 JSON。署名见 [`corpus/aternos/NOTICE.md`](corpus/aternos/NOTICE.md)。用 `python tools/fetch_aternos_corpus.py` 重新拉取。
- **`corpus/github/`** — 由 [`tools/harvest_corpus.py`](tools/harvest_corpus.py) 从模组仓库 issue 区采集的真实崩溃报告。它会自动跟取 mclo.gs / gist / pastebin 外链，脱敏玩家名、家目录路径、IP 与 UUID，并记录维护者标签（`confirmed`、`Not <Mod>`、`Loader Issue`、`Support`）作为根因判定的弱监督标注。

采集到的原文只留在本地（已 gitignore）——那是别人的 bug 报告。仓库里只提交事实性索引。

```bash
python tools/harvest_corpus.py --repo mekanism/Mekanism --max-issues 500
python tests/eval_parser.py --strict    # 平台/版本准确率门禁
python tests/test_e2e.py                # 端到端 + 地面真值
python tests/debug_platform.py --file <log>   # 为什么判成了 X？
```

## 路线图

- [ ] 网页版——浏览器里粘贴即诊断，无需安装
- [ ] GitHub Action——自动诊断 issue 里贴的崩溃报告
- [ ] 基于 Modrinth API（7.5 万模组）的模组关系图——已知冲突与版本兼容查询
- [ ] 用维护者标签做弱监督分类器，在规则无法定论时给嫌疑模组排序
- [ ] 客户端日志实时跟踪（监听 `latest.log`）

## 尚未覆盖

诚实说明范围：Bukkit/Spigot 的**插件**类故障能识别平台，但规则很少（那是 mclo.gs 的强项，建议用它）。Bedrock、PocketMine 与代理日志能解析，但诊断能力有限。遇到未覆盖的情况，工具会明确说出来而不是瞎猜：

```
No rule matched this report. It parsed cleanly, but this failure mode is
not covered yet — please open an issue with the report attached.
```

## 许可

MIT——见 [LICENSE](LICENSE)。第三方语料署名见 [corpus/aternos/NOTICE.md](corpus/aternos/NOTICE.md)。

本项目与 Mojang、Microsoft、Forge、NeoForge、Fabric 及 Aternos 无任何关联。
