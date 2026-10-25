# COVERAGE — 按失败模式的诊断覆盖率

> 由 `tools/coverage_report.py` 生成，**不要手改**。
> 回答的问题是：「下一条规则该写什么」。
> 分类只看报告的**输入属性**（异常类型、描述文本、加载器、最深一层抛出点），
> 不看命中了哪条规则——否则「未覆盖的类别」会按定义不存在。

生成时间：2026-10-25T14:55:36+0800　·　扫描 454 份　·　耗时 36.0s

## 一、总体

**诊断率 74.2%**（337/454），未覆盖 117 份，解析失败 0 份。

未覆盖绝对数最大：`other` 78 份、`mod-bug` 16 份、`mod-loading` 11 份（合计 105/117）。

诊断率最低：`other` 55%（175 份）、`native` 57%（7 份）。**下一条规则应当从这两处来。**

## 二、按失败模式

| 失败模式 | 样本数 | 已诊断 | 诊断率 | 含致命/错误级 | 有维护者结论 |
|---|---:|---:|---:|---:|---:|
| `oom` 内存耗尽 (OutOfMemoryError / heap space) | 0 | 0 | — | 0 | 0 |
| `watchdog` 看门狗强杀 / 主线程卡死 | 14 | 13 | 93% | 13 | 2 |
| `mixin` Mixin 注入失败 | 64 | 57 | 89% | 57 | 25 |
| `native` 原生崩溃（JVM 层 / 显卡驱动） | 7 | 4 | 57% | 4 | 1 |
| `mod-loading` 模组加载 / 依赖 / 类缺失 | 82 | 71 | 87% | 71 | 26 |
| `plugin` 服务端插件（Bukkit 系） | 0 | 0 | — | 0 | 0 |
| `world-data` 世界数据 / 区块 / 实体 tick | 21 | 20 | 95% | 20 | 3 |
| `mod-bug` 根因抛在模组自身代码里 | 91 | 75 | 82% | 74 | 12 |
| `other` 其他 / 未分类 | 175 | 97 | 55% | 95 | 44 |

### 空桶：不是规则缺陷，是语料里没有这一类

- `oom`：语料里没有任何 OOM 报告（`OutOfMemoryError` / `java heap space` 命中 0 份）
- `plugin`：语料里没有纯 Bukkit 系服务端报告（只有 mohist / arclight 这类混合端）

> 空桶必须显式出现。若只写 0 行，读者会以为「已覆盖」；若直接省略，读者会以为「不存在」。两者都是错的。

加载器分布（判断「空桶」是否有语料依据）：`fabric` 173　`forge` 127　`neoforge` 87　`vanilla` 40　`quilt` 21　`mohist` 3　`arclight` 2　`custom-skin-loader` 1。

> 匹配顺序（先命中先归入，`other` 兜底）：`oom` → `watchdog` → `mixin` → `native` → `mod-loading` → `plugin` → `world-data` → `mod-bug` → `other`。
> 顺序即契约：同一个 OutOfMemoryError 若发生在模组加载阶段，归入 `oom`，
> 因为用户要修的是内存。改动顺序会改变数字，故由测试钉死。
> `mod-bug` 排在最后（`other` 之前），因为「根因抛在模组代码里」是最不具体的断言；
> 它读的是最深一层 `Caused by:` 的首个栈帧，不读规则引擎与归因结果——否则覆盖率会循环论证。

## 三、未覆盖报告的实际长相（Top 20）

这些是「解析成功但没有任何规则命中」的报告按异常签名聚类。
**排在最上面的就是下一条规则的候选**。

| 异常签名 | 数量 | 所属失败模式 |
|---|---:|---|
| `java.lang.Throwable: Manually triggered debug crash` | 4 | `other` |
| `java.lang.reflect.InvocationTargetException` | 3 | `mixin` |
| `java.lang.RuntimeException: An exception occurred when launching the server!` | 2 | `other` |
| `java.lang.RuntimeException: Minecraft game provider couldn't locate the game! The game may be absent from th` | 2 | `other` |
| `net.fabricmc.loader.impl.FormattedException: java.lang.RuntimeException: Could not execute entrypoint stage 'preLaunch' due t` | 2 | `mod-loading` |
| `java.lang.ClassCastException: Cannot coerce loader value to a String` | 2 | `other` |
| `com.mojang.text2speech.Narrator$InitializeException: Failed to load library flite` | 2 | `native` |
| `org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException: @Shadow field val$p_434753_ was not located in the target class net.minecraft.cl` | 1 | `mixin` |
| `java.lang.NullPointerException: Cannot invoke "net.caffeinemc.mods.sodium.client.render.chunk.translucent_sortin` | 1 | `mod-bug` |
| `net.minecraft.ReportedException: Manually triggered debug crash` | 1 | `other` |
| `org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError: An unexpected critical error was encountered` | 1 | `mixin` |
| `java.lang.NullPointerException: Trying to access unbound value: ResourceKey[minecraft:block / aether:skyroot_log` | 1 | `other` |
| `com.google.gson.JsonParseException: com.google.gson.stream.MalformedJsonException: Use JsonReader.setLenient(true) t` | 1 | `other` |
| `java.lang.IllegalStateException: Overflowed the mesh time buffer at 224x31` | 1 | `world-data` |
| `java.lang.RuntimeException: Sodium mod config not found` | 1 | `mod-bug` |
| `net.neoforged.neoforge.logging.CrashReportExtender$ModLoadingCrashException: Mod loading has failed` | 1 | `mod-loading` |
| `java.lang.RuntimeException: Exception thrown while executing job` | 1 | `other` |
| `java.lang.ArrayIndexOutOfBoundsException: Index 4 out of bounds for length 4` | 1 | `mod-bug` |
| `io.netty.handler.codec.DecoderException: java.io.IOException: Packet play/clientbound/minecraft:level_particles (class_26` | 1 | `other` |
| `java.lang.IllegalArgumentException: Data for attachment 'worldgendevtools:feature_positions' was too big (32768 byte` | 1 | `other` |

## 四、未覆盖报告是否本来就无解？

用维护者标签做交叉检查：如果这些报告的 issue 也没有结论，那缺口是
**报告本身信息不足**，不该由规则去填。

| 维护者结论 | 数量 |
|---|---:|
| `(none)` | 97 |
| `user_error_or_config` | 19 |
| `bug_in_this_mod` | 1 |

**这项检查对 83% 的缺口没有结论**：97/117 份未覆盖报告的 issue 本身没有任何维护者标签。所以不能读成「缺口本来就无解」——只能说对剩下的 20 份，维护者认为它们有明确原因，其中 `user_error_or_config` 与 `bug_in_this_mod` 是规则应该能命中的。

## 五、方法

- 桶分类**先命中先归入**，顺序见第二节；`other` 是兜底且必须最后。
- 每份报告都跑真实规则引擎（含归因，因为 `has_suspect` 门控的规则依赖它），
  不是「模拟命中」。
- 解析失败单独计数，**不混进诊断率**——否则解析 bug 会伪装成覆盖缺口。
- 只记录异常签名与计数，不含报告正文与玩家数据。
