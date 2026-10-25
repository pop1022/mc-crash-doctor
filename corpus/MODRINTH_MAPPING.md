# MODRINTH_MAPPING — 1D.0 现状量化结果

> 由 `tools/audit_modrinth_mapping.py` 生成，**不要手改**。
> 目的：在写 1D.2（Modrinth 元数据抓取）之前，量清楚语料里的模组
> 标识能不能映射到 Modrinth 项目，以及作者到底会不会声明
> `incompatible`。判据见 `ROADMAP.md` 1D.0。

生成时间：2026-10-21T22:51:51+0800　·　语料报告数：454　·　网络请求：0（缓存命中 433）

## 一、判定

**门槛（匹配率 ≥ 40%）：通过**

- 整体匹配率：**50.8%**（61/120）
  命中方式：`slug` 53、`variant` 6、`search` 2
- 候选总数 751，其中**运行时库 25 个**（guava/bus/mixin/asm/netty 等）与**加载器产物 12 个**（fmlloader/fabric-loader 等）——两者都不是模组，已排除出分母，待测模组候选 714 个；本报告按 sha256(name) 序确定性抽取 **120** 个实测（可复现、与名称和频次无关）。
  按二项分布，该样本量在 95% 置信下误差约 ±9 个百分点——够用于「做/不做」的判定，不够用于精度声明。
  **修正前口径**（不排除运行时库）实测为 36.7%（44/120）；两个数字都保留，读者可自行判断差别来自方法还是生态。用 `--no-exclude-libs` 可复现修正前口径。
- 预算足以覆盖全部抽样候选，无截断。
- 结论：匹配率达标，1D.2（Modrinth 元数据抓取）可以做；优先级取决于第七节的 `incompatible` 密度——若该密度过低，声明式边的价值主要来自 jar 清单（1D.1），而非 API。

## 二、候选标识来源分布

| 来源 | 候选数 | 已解析 | 匹配率 |
|---|---:|---:|---:|
| both | 8 | 5 | 62.5% |
| mixin | 82 | 39 | 47.6% |
| jar | 30 | 17 | 56.7% |

`mod_ids` 字段：**106/454 份报告有值**（索引里声明了该字段但采集器从未填充——这是 1D.1 的输入缺口）。

## 三、失败原因分布

| 原因 | 数量 | 含义 |
|---|---:|---|
| `not_on_modrinth` | 45 | 名称在 Modrinth 上查不到（可能只在 CurseForge） |
| `name_collision_or_alias` | 14 | 有搜索结果但无一精确匹配（别名/缩写/中文名） |

## 四、被排除的非模组产物（Top 15）

这些名字来自栈帧后缀（`~[guava-32.1.2-jre.jar:?]`），随 JVM/MC/加载器
分发，用户不会从模组站安装。1.20+ 崩溃报告已无 `-- Mod List --` 段，
模组与库走同一通道，故按运行时命名空间语义排除；加载器产物（fmlloader 等）同理。

| 名称 | 出现在报告数 |
|---|---:|
| `client` | 131 |
| `forge` | 77 |
| `fmlloader` | 52 |
| `eventbus` | 51 |
| `neoforge` | 46 |
| `bootstraplauncher` | 45 |
| `securejarhandler` | 39 |
| `fmlcore` | 37 |
| `gson` | 37 |
| `datafixerupper` | 30 |
| `bus` | 28 |
| `server` | 27 |
| `fabric-loader` | 25 |
| `lwjgl-glfw` | 25 |
| `javafmllanguage` | 24 |

## 五、未被解析的模组候选（Top 25，按出现报告数排序）

| 候选 | 来源 | 出现在报告数 | 原因 |
|---|---|---:|---|
| `notenoughanimations` | mixin | 8 | name_collision_or_alias |
| `core` | jar | 7 | name_collision_or_alias |
| `rarcompat` | jar+mixin | 7 | not_on_modrinth |
| `NewLaunch` | jar | 6 | not_on_modrinth |
| `TConstruct` | jar | 6 | name_collision_or_alias |
| `appliedenergistics2` | jar+mixin | 6 | name_collision_or_alias |
| `justzoom` | mixin | 6 | not_on_modrinth |
| `supermartijn642corelib` | mixin | 6 | not_on_modrinth |
| `betterendisland` | mixin | 5 | not_on_modrinth |
| `fabric-lifecycle-events` | jar | 5 | not_on_modrinth |
| `enhancedcelestials` | mixin | 4 | not_on_modrinth |
| `puffish_skills` | mixin | 4 | not_on_modrinth |
| `valkyrienskies` | mixin | 4 | name_collision_or_alias |
| `bankstorage` | mixin | 3 | not_on_modrinth |
| `amecsapi` | mixin | 2 | not_on_modrinth |
| `betterendforge` | mixin | 2 | not_on_modrinth |
| `bygonenether` | mixin | 2 | not_on_modrinth |
| `dataanchor` | mixin | 2 | not_on_modrinth |
| `dynamiclightsreforged` | mixin | 2 | not_on_modrinth |
| `fabric-rendering-data-attachment-v1` | mixin | 2 | not_on_modrinth |
| `glsl-processor` | jar | 2 | not_on_modrinth |
| `hexplat` | mixin | 2 | not_on_modrinth |
| `ldlib2` | mixin | 2 | name_collision_or_alias |
| `libbamboo` | mixin | 2 | not_on_modrinth |
| `recipeessentials` | jar+mixin | 2 | not_on_modrinth |

## 六、因果边的 subject 可解析性

`compat-edges.jsonl` 里 `caused`/`suspected` 的 subject 去重后 **87 个**，实测 60 个，解析成功 **28 个**（46.7%）。

> 背景：这些边全部是自环（`subject == object`），即「某模组被指为
> 元凶」。语料里**没有任何一条 A↔B 的成对不兼容边**——这正是
> 声明式边要填的空白。

## 七、`incompatible` 声明密度（抽样）

抽样 25 个项目、各探最多 2 个版本：

- 至少有一个 `incompatible` 依赖声明的项目：**3/25**（12.0%）
- 至少有一个（任意类型）依赖声明的项目：16/25

依赖类型分布：

| dependency_type | 数量 |
|---|---:|
| `required` | 33 |
| `optional` | 28 |
| `incompatible` | 5 |
| `embedded` | 2 |

`incompatible` 样例（项目 → 目标项目 ID）：

- `wither-spawn-animation` @ 1.6.2 → `KseM6VIg`
- `wither-spawn-animation` @ 1.0.0 → `KseM6VIg`
- `veil` @ 4.5.2 → `sk9rgfiA`
- `veil` @ 1.2.0 → `4ZqxOvjD`
- `ae2` @ 26.3.1-alpha → `tq47Uqpn`

## 八、方法与局限

- **保守匹配**：只接受精确 slug，或搜索结果中归一化后完全相等的
  slug/标题。不做模糊接受——错一条边比少一条边更糟，因为下游会当真。
- **分母不含加载器产物**（forge/fabric-loader/paper 等），否则匹配率
  会被永远查不到的合法名称拉低。
- **只抽 2 个版本**做依赖探测，且 `versions` 数组顺序未在文档中约定，
  故取首尾两端。因此声明密度是**下界**，不是精确值。
- **词边界重试（默认开启）**：Modrinth 搜索按词匹配，而压缩写法
  （`notenoughanimations`）一个词都召不回。所以命中失败后会再问一次
  「驼峰/字母数字边界」形式（`XaerosWorldMap` → `xaeros world map`）。
  **接受的规则不变**——命中项仍须归一化后与候选完全相等，因此它只可能
  找到正确的项目，不可能编出一个名字不对的匹配。但它仍可能在一组同名
  项目（本体/移植/续作）里挑错，这一点无法用字符串规则消除。
  实测收益：45.8% → 50.8%（6/120 全部是驼峰名）。
  用 `--no-variant-retry` 可关闭。
- **未覆盖 CurseForge**：需 `x-api-key` + 审批 + 商用协议。若大量
  `not_on_modrinth` 实际在 CurseForge，本报告的匹配率会低估真实可达性。
- **全小写连写与真别名机械无解**：`justzoom`、`rarcompat` 没有可切分点
  （需要词典/分词器），`appliedenergistics2`→`ae2`、`TConstruct`→
  `tinkers-construct` 是项目改名/别名（需要人工别名表）。这两类占残差的
  主体，**都不是调参数能解决的**。

网络错误统计：`{}`
