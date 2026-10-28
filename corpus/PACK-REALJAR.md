# Pack Doctor 在真实整合包上的第一次体检（C1）

> 2026-10-27。此前 `--pack` 的 46 项测试**全部**喂代码里现场 zip 出来的合成 jar，
> 仓库内真实 `.jar` 数量为 0。本文记录第一次在真实整合包上跑的结果，以及它暴露的
> 五个缺陷。**二进制不入库**：这里只记包的位置、规模与结论，jar 本身不提交。

## 样本

| 项 | 值 |
|---|---|
| 位置 | `C:\Users\Administrator\Desktop\Infinity Legacy II`（本机真实服务器包） |
| 规模 | 355 个 jar，588 MB；`modrinth.index.json` 声明 403 个文件 |
| 声明版本 | Minecraft 1.21.1，NeoForge 350 / Fabric 3 个 jar |
| 是否可用 | **是**。它自己的 `logs/latest.log` 有 `Done (4.723s)! For help, type "help"` |
| 复现 | `python -m mcd --pack "<该目录>"`（只读，不写盘、不联网、不需要 API） |

“可用”这一条是整个取证的前提：**在一个能启动的包上报出的每一条 finding，都要能
解释清楚，否则就是误报。**

## 结果

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| findings | **35** | **1** |
| — `pack.declared-conflict` | 9 | 0 |
| — `pack.missing-dependency` | 21 | 0 |
| — `pack.version-mismatch` | 4 | 0 |
| — `pack.mixed-loaders` | 1 | 1（**真阳性**） |
| undecided | 24 | **1** |
| unreadable | 2 | 1 |

剩下的那 1 条 finding 是真实的：NeoForge 实例里装了 3 个纯 Fabric jar
（`collective` 等），没有 Sinytra Connector，NeoForge 不会加载它们。

剩下的 1 条 undecided 是 `[3.2.1.+,)`：NeoForge 的 `.+` 写法我们还不解析，**如实
说不知道**，没有硬猜。剩下的 1 个 unreadable 是
`ScalableCatsForce-NeoForge-3.7.1-build-11-with-library.jar`，它确实没有顶层清单。

## 五个缺陷（每条都由真实声明触发）

### ① `INCOMPATIBLE` 是带版本区间的，我们当成了“装了就不兼容”

`ae2wtlib-19.5.1.jar` 的 `META-INF/neoforge.mods.toml`：

```toml
[[dependencies.ae2wtlib]]
modId = "extendedae"
type = "INCOMPATIBLE"
versionRange = "(,1.21-1.1.4-neoforge]"     # 只有旧版本不兼容
```

包里装的是 `ExtendedAE-1.21-2.2.35-neoforge` —— **不在**该区间内。旧实现只要发现
对方已安装就报冲突，于是 9 条冲突里 8 条是这种。修法：把区间当作条件，与正向依赖
同等对待；区间读不懂 → `undecided`，不报 finding。

### ② jar-in-jar 提供的 mod 被当成“没人提供”

包自己的日志写得很清楚：

```
Found mod file "de.mari_023.ae2wtlib_api-19.5.1.jar"
  [parent: ae2wtlib-19.5.1.jar, locator: jarinjar, reader: mod manifest]
```

`ae2wtlib_api` 是 4 个 mod 的 REQUIRED 依赖，由 `ae2wtlib` 内嵌的 jar 提供
（`META-INF/jarjar/`）。本包共 **47 个 jar 内嵌 jar，覆盖 30 个 mod id**。
旧实现只读顶层清单，于是 21 条缺依赖里大多数是误报。

修法：新增 `nested_modids()`，只读内嵌 jar 的 **mod id**（够用来满足依赖），
不读它们自己的依赖 —— 后者仍写在 `NOT_CHECKED` 里，不假装查过。

### ③ `${file.jarVersion}` 被当成了字面版本号

Forge 允许 mod 在 `mods.toml` 里把版本写成占位符，由加载器从 jar 的
`META-INF/MANIFEST.MF` 的 `Implementation-Version` 填。旧实现原样保留，于是无法与
任何区间比较。本包 **25 个 jar 用了该占位符，25/25 都能从 MANIFEST 解析**——
它是 `undecided` 的最大单一来源（24 条里 22 条）。

### ④ `<mc版本>-<mod版本>` 被当成 semver 预发布

`1.21.1-93-NEOFORGE` 是“Minecraft 1.21.1 + 构建 93”，不是“1.21.1 的预发布 93”。
旧实现把所有 `1.21.1-*` 读成同一个版本，于是
`[1.21.1-1.1.0,1.21.1-2.0.0)` 对已装的 `1.21.1-1.2.0` 判成不满足 → 3 条误报。

第一版修法是“把后缀拼进数字元组”，结果 `(1,21,1,93)` 与 `(1,21,87)` 比较时用 MC 段
比 mod 段，反而新造了一条误报（Patchouli）。**最终按两级比较**：先比 MC 段，相等
再比 mod 段；字母开头的后缀仍按预发布处理（`1.20.1-beta < 1.20.1` 的语义没变）。

### ⑤ `side="CLIENT"` 的依赖在服务端包上被当成“缺失”

`connectedglass` 要求 `fusion`、`fancymenu` 要求 `melody`，两条都写着
`side = "CLIENT"`。服务端不需要它们，而 `--pack DIR` 无法判断目录是客户端还是
服务端。修法：跳过 side 限定的依赖，并把它写进 `NOT_CHECKED`（**不是静默跳过**）。
真正的解法是 `--side server|client`（计划里的 C2）。

## 顺带修的一个小问题

`BUILTIN_IDS` 有 `fabric-loader` / `fabric_loader` / `fabricloader`，但没有
`fabric` —— 而 Fabric 的 `fabric.mod.json` 里 `depends: {"fabric": "*"}` 正是这么写
加载器自己的。于是任何 Fabric mod 都会触发一条“缺 fabric 依赖”。

## 测试

`tests/test_pack_realworld.py`（10 项）用合成 jar **复刻上面每一种形态**，并带反向
对照（区间确实覆盖已装版本时仍然报冲突；`side="BOTH"` 仍然报缺依赖）。
`tests/test_version_range.py` 追加 7 项参数化版本用例。原来的手写夹具无法覆盖这些
形态——这正是“真实 jar 取证”这件事的价值所在。

## 第六件事：`--side` 让两个问题变成可回答的（2026-10-28）

`--pack DIR` 只看目录，看不出这个目录是客户端还是服务端。加 `--side
server|client` 之后，两件事从 `not_checked` 变成真检查：

1. **Fabric/Quilt 的 `environment`** → 新 finding `pack.wrong-side-mod`
   （双向：服务端目录里的 `environment: client`，以及客户端目录里的
   `environment: server`）。`environment: "*"` 和"没写"都不报 —— 后者是
   Forge/NeoForge 的全部情况，它们的清单格式没有 per-mod 侧别字段。
2. **`side=CLIENT/SERVER` 的依赖要求**按侧生效。

同一个目录、两种答案，都对：

| 命令 | findings |
|---|---|
| `--pack … --side server` | **1**（mixed-loaders） |
| `--pack … --side client` | **3**（mixed-loaders + `fusion` + `melody` 缺失） |

因为 `connectedglass` 要求 `fusion`、`fancymenu` 要求 `melody`，两条都写着
`side = "CLIENT"`：服务端不需要它们，客户端缺了就是缺了。

**诚实标注**：这个包里的 3 个 Fabric mod 全部声明 `environment: "*"`，所以
`pack.wrong-side-mod` 在本样本上**没有命中**。本机另外三个真实包
（241 / 189 / 159 jar）里的 Fabric mod 也全是 `"*"`。也就是说这条检查目前
只有测试覆盖，没有真实命中样本 —— 它会在"把客户端包直接当服务端开"的场合
第一次真正发挥作用。

`not_checked` 从 3 条降到 1 条（只剩"内嵌 jar 自己的依赖"）。

## 仍然不检查

1. 客户端限定模组装到服务端（`environment` 字段未读）。
2. 单侧依赖（`side=CLIENT/SERVER`），因为包的方向未知。
3. 内嵌 jar **自己**声明的依赖。
4. 嵌套的嵌套、`mcmod.info`（1.13 以前）。
5. 版本是否存在 / 是否最新（需要 Modrinth，即 2.1）。

其中第 1、2 条在给了 `--side` 之后**不再是缺口**；不给 `--side` 时它们仍然
出现在 `not_checked` 里，因为不知道目录朝哪一侧跑。

以上都会出现在 `--pack` 输出的 `not checked` 段里，不静默。
