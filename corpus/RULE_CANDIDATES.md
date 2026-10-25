# RULE_CANDIDATES — 未覆盖长尾的候选清单（不是规则）

> 由 `tools/suggest_rules.py --report` 生成，**不要手改**。
> 本文件只提出候选，**不含任何生效规则**；生效路径见文末「怎么用」。

扫描 454 份 · 未覆盖 **117** 份 · 签名聚类 107 个

## 先看这两个数：一条规则能买到几份报告

- 只按签名聚类，一条规则平均覆盖 **1.09 份**报告
- 其中 **100** 个聚类只有 1 份报告（合计 100 份，占未覆盖集的 85%）
- top-10 聚类合计 20 份 = **17%**

ROADMAP 风险 R4 的停手判据是「top-10 < 30% → 长尾已枯竭，转结构化输出，停止堆规则」。本次实测 17%，**判据触发**：写规则不再是瓶颈。

## 聚类清单

| # | 份数 | 桶 | 签名 | 泛化判定 |
|---|---|---|---|---|
| 1 | 4 | `other` | `java.lang.Throwable: Manually triggered debug crash` | `reusable` |
| 2 | 3 | `other` | `java.lang.reflect.InvocationTargetException` | `needs_generalisation` |
| 3 | 2 | `native` | `com.mojang.text2speech.Narrator$InitializeException: Failed to load library flit` | `reusable` |
| 4 | 2 | `other` | `java.lang.ClassCastException: Cannot coerce loader value to a String` | `reusable` |
| 5 | 2 | `other` | `java.lang.RuntimeException: An exception occurred when launching the server!` | `reusable` |
| 6 | 2 | `other` | `java.lang.RuntimeException: Minecraft game provider couldn't locate the game! Th` | `reusable` |
| 7 | 2 | `mod-loading` | `net.fabricmc.loader.impl.FormattedException: java.lang.RuntimeException: Could n` | `reusable` |
| 8 | 1 | `other` | `com.google.common.util.concurrent.ExecutionError: java.lang.StackOverflowError` | `singleton` |
| 9 | 1 | `other` | `com.google.gson.JsonParseException: Unknown registry key in ResourceKey[minecraf` | `singleton` |
| 10 | 1 | `mod-bug` | `com.google.gson.JsonParseException: com.google.gson.stream.MalformedJsonExceptio` | `singleton` |
| 11 | 1 | `other` | `com.google.gson.JsonParseException: com.google.gson.stream.MalformedJsonExceptio` | `singleton` |
| 12 | 1 | `other` | `com.mojang.authlib.exceptions.InvalidCredentialsException: Status: 401` | `singleton+overfit` |
| 13 | 1 | `other` | `io.netty.handler.codec.DecoderException: The received string length is longer th` | `singleton` |
| 14 | 1 | `other` | `io.netty.handler.codec.DecoderException: Unknown serializer type 111` | `singleton+overfit` |
| 15 | 1 | `other` | `io.netty.handler.codec.DecoderException: java.io.IOException: Packet play/client` | `singleton` |
| 16 | 1 | `other` | `io.netty.handler.codec.EncoderException: Failed to encode packet 'serverbound/mi` | `singleton` |
| 17 | 1 | `other` | `java.io.FileNotFoundException: https://raw.githubusercontent.com/ToCraft/crafted` | `singleton+overfit` |
| 18 | 1 | `other` | `java.io.IOException: File [G:\恢复\测试服务器-新\modernfix\structureCacheV1\apotheosis_t` | `singleton+overfit` |
| 19 | 1 | `other` | `java.io.IOException: The handle is invalid` | `singleton` |
| 20 | 1 | `other` | `java.io.UncheckedIOException: java.nio.file.AccessDeniedException: <HOME>\AppDat` | `singleton+overfit` |
| 21 | 1 | `other` | `java.lang.ArrayIndexOutOfBoundsException: -1` | `singleton` |
| 22 | 1 | `other` | `java.lang.ArrayIndexOutOfBoundsException: 4` | `singleton` |
| 23 | 1 | `mod-bug` | `java.lang.ArrayIndexOutOfBoundsException: Index 4 out of bounds for length 4` | `singleton` |
| 24 | 1 | `mod-bug` | `java.lang.ClassCastException: class com.thevortex.allthemodium.material.ATMTier ` | `singleton` |
| 25 | 1 | `other` | `java.lang.ClassCastException: class net.minecraft.client.renderer.RenderType$Com` | `singleton` |
| 26 | 1 | `mod-loading` | `java.lang.ClassNotFoundException: kotlin.jvm.internal.Lambda` | `singleton` |
| 27 | 1 | `mod-loading` | `java.lang.ClassNotFoundException: net.fabricmc.loader.impl.launch.knot.KnotClien` | `singleton` |
| 28 | 1 | `mod-loading` | `java.lang.ClassNotFoundException: net.minecraft.client.Minecraft` | `singleton` |
| 29 | 1 | `mod-loading` | `java.lang.ClassNotFoundException: net.minecraft.client.renderer.texture.Abstract` | `singleton` |
| 30 | 1 | `mod-loading` | `java.lang.ClassNotFoundException: shadows.placebo.util.PlaceboTaskQueue` | `singleton` |
| 31 | 1 | `other` | `java.lang.Error: Invalid java.home value? 'D:' for vm 'OpenJDK 64-Bit Server VM'` | `singleton` |
| 32 | 1 | `other` | `java.lang.Error: Why would you set the warning level multiple times?` | `singleton` |
| 33 | 1 | `other` | `java.lang.IllegalArgumentException: Data for attachment 'worldgendevtools:featur` | `singleton+overfit` |
| 34 | 1 | `other` | `java.lang.IllegalArgumentException: No value with id -1` | `singleton` |
| 35 | 1 | `other` | `java.lang.IllegalArgumentException: Payload may not be larger than 32767 bytes` | `singleton+overfit` |
| 36 | 1 | `mod-bug` | `java.lang.IllegalArgumentException: Unsupported class file major version 21845` | `singleton+overfit` |
| 37 | 1 | `watchdog` | `java.lang.IllegalArgumentException: null` | `singleton` |
| 38 | 1 | `other` | `java.lang.IllegalArgumentException: unknown format type: lựa chọn  --> Note: thi` | `singleton` |
| 39 | 1 | `other` | `java.lang.IllegalStateException: Can't getDevice() before it was initialized` | `singleton` |
| 40 | 1 | `mod-bug` | `java.lang.IllegalStateException: Capability missing for <UUID>` | `singleton` |
| 41 | 1 | `other` | `java.lang.IllegalStateException: Not building!` | `singleton` |
| 42 | 1 | `world-data` | `java.lang.IllegalStateException: Overflowed the mesh time buffer at 224x31` | `singleton` |
| 43 | 1 | `other` | `java.lang.IllegalStateException: Player is either on another team or not on any ` | `singleton` |
| 44 | 1 | `other` | `java.lang.IllegalStateException: Texture is required if use_mob_texture is false` | `singleton` |
| 45 | 1 | `other` | `java.lang.IllegalStateException: Tried to lookup sprite, but atlas is not initia` | `singleton` |
| 46 | 1 | `other` | `java.lang.IncompatibleClassChangeError: Method 'int net.minecraft.world.item.Ite` | `singleton` |
| 47 | 1 | `mod-bug` | `java.lang.NullPointerException: Cannot invoke "com.wudji.xplusautofish.XPlusAuto` | `singleton` |
| 48 | 1 | `other` | `java.lang.NullPointerException: Cannot invoke "it.unimi.dsi.fastutil.objects.Obj` | `singleton` |
| 49 | 1 | `mod-bug` | `java.lang.NullPointerException: Cannot invoke "net.caffeinemc.mods.sodium.client` | `singleton` |
| 50 | 1 | `other` | `java.lang.NullPointerException: Cannot invoke "net.minecraft.class_2680.method_2` | `singleton` |
| 51 | 1 | `mod-bug` | `java.lang.NullPointerException: Cannot invoke "net.minecraft.class_3222.method_5` | `singleton` |
| 52 | 1 | `other` | `java.lang.NullPointerException: Cannot invoke "org.quiltmc.loader.api.VersionInt` | `singleton` |
| 53 | 1 | `mod-bug` | `java.lang.NullPointerException: Cannot invoke "xaero.map.graphics.GLObjectDelete` | `singleton` |
| 54 | 1 | `other` | `java.lang.NullPointerException: Trying to access unbound value: ResourceKey[mine` | `singleton` |
| 55 | 1 | `other` | `java.lang.NullPointerException: entité de bloc à cocher` | `singleton` |
| 56 | 1 | `other` | `java.lang.RuntimeException: Could not create directory <HOME>\AppData\Roaming\.m` | `singleton+overfit` |
| 57 | 1 | `other` | `java.lang.RuntimeException: Could not execute entrypoint stage 'client' due to e` | `singleton` |
| 58 | 1 | `mixin` | `java.lang.RuntimeException: Error creating Mixin config fabric-crash-report-info` | `singleton` |
| 59 | 1 | `mixin` | `java.lang.RuntimeException: Error creating Mixin config omega-config.mixins.json` | `singleton` |
| 60 | 1 | `other` | `java.lang.RuntimeException: Exception thrown while executing job` | `singleton` |
| 61 | 1 | `other` | `java.lang.RuntimeException: Fabric permissions version 0.4.0-SNAPSHOT is not sup` | `singleton` |
| 62 | 1 | `other` | `java.lang.RuntimeException: Failed to load class file for 'net.minecraft.client.` | `singleton` |
| 63 | 1 | `other` | `java.lang.RuntimeException: Failed to read accessWidener file from mod wurst` | `singleton` |
| 64 | 1 | `other` | `java.lang.RuntimeException: Failed to read classTweaker file from mod fabric-bio` | `singleton` |
| 65 | 1 | `other` | `java.lang.RuntimeException: Non-unique Mixin config name mixins.reach-entity-att` | `singleton` |
| 66 | 1 | `other` | `java.lang.RuntimeException: Non-unique Mixin config name xlpackets.mixins.json u` | `singleton` |
| 67 | 1 | `mod-bug` | `java.lang.RuntimeException: Sodium mod config not found` | `singleton` |
| 68 | 1 | `mod-bug` | `java.lang.RuntimeException: Unfixable conflicts` | `singleton` |
| 69 | 1 | `mod-bug` | `java.lang.RuntimeException: Unknown variable: BIOME_PALE_GARDEN` | `singleton` |
| 70 | 1 | `mod-bug` | `java.lang.RuntimeException: broken shader file` | `singleton` |
| 71 | 1 | `other` | `java.lang.RuntimeException: error remapping game jars [<HOME>\AppData\Roaming\co` | `singleton+overfit` |
| 72 | 1 | `other` | `java.lang.RuntimeException: error remapping game jars [F:\Modded MC\curseforge\m` | `singleton+overfit` |
| 73 | 1 | `other` | `java.lang.RuntimeException: java.util.concurrent.ExecutionException: java.lang.A` | `singleton` |
| 74 | 1 | `other` | `java.lang.RuntimeException: net.fabricmc.loader.api.VersionParsingException: Cou` | `singleton` |
| 75 | 1 | `other` | `java.lang.StackOverflowError: Exception in server tick loop` | `singleton` |
| 76 | 1 | `other` | `java.lang.StackOverflowError: null` | `singleton` |
| 77 | 1 | `other` | `java.lang.StringIndexOutOfBoundsException: Range [16, 13) out of bounds for leng` | `singleton` |
| 78 | 1 | `other` | `java.lang.Throwable: null` | `singleton` |
| 79 | 1 | `mod-loading` | `java.lang.TypeNotPresentException: Type kts/dev/common/A not present` | `singleton+overfit` |
| 80 | 1 | `native` | `java.lang.UnsatisfiedLinkError: Failed to locate library: liblwjgl.so` | `singleton` |
| 81 | 1 | `other` | `java.lang.UnsupportedOperationException: Reflective setAccessible(true) disabled` | `singleton` |
| 82 | 1 | `other` | `java.net.ConnectException: Connection timed out: connect` | `singleton` |
| 83 | 1 | `other` | `java.net.SocketTimeoutException: connect timed out` | `singleton` |
| 84 | 1 | `other` | `java.net.http.HttpConnectTimeoutException: HTTP connect timed out` | `singleton` |
| 85 | 1 | `other` | `java.net.http.HttpTimeoutException: request timed out` | `singleton` |
| 86 | 1 | `other` | `java.nio.file.NoSuchFileException: config\metadata.json` | `singleton` |
| 87 | 1 | `other` | `java.util.ConcurrentModificationException: null` | `singleton` |
| 88 | 1 | `other` | `java.util.ServiceConfigurationError: org.spongepowered.asm.service.IMixinService` | `singleton` |
| 89 | 1 | `mod-bug` | `java.util.concurrent.CompletionException: java.lang.ClassCastException: class ne` | `singleton` |
| 90 | 1 | `other` | `java.util.concurrent.CompletionException: java.lang.NoSuchMethodError: 'net.mine` | `singleton` |
| 91 | 1 | `other` | `java.util.concurrent.CompletionException: java.lang.RuntimeException: could not ` | `singleton` |
| 92 | 1 | `mod-bug` | `net.fabricmc.fabric.impl.registry.sync.RemapException: Received 4 registry entri` | `singleton` |
| 93 | 1 | `mod-loading` | `net.fabricmc.loader.impl.FormattedException: java.lang.IllegalArgumentException:` | `singleton` |
| 94 | 1 | `mod-loading` | `net.fabricmc.loader.impl.FormattedException: joptsimple.MultipleArgumentsForOpti` | `singleton` |
| 95 | 1 | `other` | `net.minecraft.ReportedException: Exception generating new chunk` | `singleton` |
| 96 | 1 | `other` | `net.minecraft.ReportedException: Manually triggered debug crash` | `singleton` |
| 97 | 1 | `other` | `net.minecraftforge.fml.LoadingFailedException: Loading errors encountered: [` | `singleton` |
| 98 | 1 | `mod-loading` | `net.neoforged.neoforge.logging.CrashReportExtender$ModLoadingCrashException: Mod` | `singleton` |
| 99 | 1 | `other` | `org.gradle.api.internal.tasks.testing.TestSuiteExecutionException: Could not sta` | `singleton` |
| 100 | 1 | `mod-bug` | `org.gradle.api.plugins.UnknownPluginException: Plugin [id: 'fabric-loom', versio` | `singleton` |
| 101 | 1 | `mixin` | `org.spongepowered.asm.mixin.injection.throwables.InvalidInjectionException: Inva` | `singleton` |
| 102 | 1 | `other` | `org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException: net.minecraf` | `singleton` |
| 103 | 1 | `other` | `org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException: net.minecraf` | `singleton` |
| 104 | 1 | `mixin` | `org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException: @Shado` | `singleton` |
| 105 | 1 | `mixin` | `org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException: @Shado` | `singleton+overfit` |
| 106 | 1 | `mixin` | `org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError: An une` | `singleton` |
| 107 | 1 | `other` | `org.spongepowered.asm.mixin.transformer.throwables.ReEntrantTransformerError: Re` | `singleton` |

## 每个聚类建议的 `when` 骨架

`singleton` 的条目也列出来，理由不是「可以写」，而是让后来人看到「这里写过一次就没再出现过」——否则每半年都会有人重新发现它们。

### 1. java.lang.Throwable: Manually triggered debug crash — 4 份

- 桶：`other` · 异常类：`java.lang.Throwable`
- 描述：`Manually triggered debug crash`
- 泛化判定：`reusable`
- 报告：`CaffeineMC__sodium/3473`, `CaffeineMC__sodium/3505`, `CaffeineMC__sodium/3873`, `CaffeineMC__sodium/3915`
- 建议 `when`：

```yaml
when:
  description:
    - 'Manually triggered debug crash'
  exception:
    - '^java\.lang\.Throwable$'
  exception_msg:
    - 'Manually\ triggered\ debug\ crash'
```

### 2. java.lang.reflect.InvocationTargetException — 3 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`, `java.lang.reflect.GenericSignatureFormatError`, `net.fabricmc.loader.impl.lib.classtweaker.reader.ClassTweakerFormatException`
- 泛化判定：`needs_generalisation`
- 报告：`CaffeineMC__sodium/3611`, `FabricMC__fabric-api/5417`, `FabricMC__fabric-loader/1135`
- 建议 `when`：

```yaml
when:
  exception:
    - '^(java\.lang\.IllegalArgumentException|java\.lang\.reflect\.GenericSignatureFormatError|net\.fabricmc\.loader\.impl\.lib\.classtweaker\.reader\.ClassTweakerFormatException)$'
```

### 3. com.mojang.text2speech.Narrator$InitializeException: Failed to load library flite — 2 份

- 桶：`native` · 异常类：`java.lang.NullPointerException`, `java.lang.UnsatisfiedLinkError`
- 泛化判定：`reusable`
- 报告：`Snownee__Jade/423`, `Snownee__Jade/543`
- 建议 `when`：

```yaml
when:
  exception:
    - '^(java\.lang\.NullPointerException|java\.lang\.UnsatisfiedLinkError)$'
  exception_msg:
    - 'Failed\ to\ load\ library\ flite'
```

### 4. java.lang.ClassCastException: Cannot coerce loader value to a String — 2 份

- 桶：`other` · 异常类：`java.lang.ClassCastException`
- 泛化判定：`reusable`
- 报告：`QuiltMC__quilt-loader/368`, `QuiltMC__quilt-loader/415`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassCastException$'
  exception_msg:
    - 'Cannot\ coerce\ loader\ value\ to\ a\ String'
```

### 5. java.lang.RuntimeException: An exception occurred when launching the server! — 2 份

- 桶：`other` · 异常类：`java.lang.RuntimeException`, `java.nio.file.FileSystemException`
- 泛化判定：`reusable`
- 报告：`FabricMC__fabric-loader/1022`, `FabricMC__fabric-loader/1093`
- 建议 `when`：

```yaml
when:
  exception:
    - '^(java\.lang\.RuntimeException|java\.nio\.file\.FileSystemException)$'
  exception_msg:
    - 'An\ exception\ occurred\ when\ launching\ the\ server!'
```

### 6. java.lang.RuntimeException: Minecraft game provider couldn't locate the game! The game may be absent — 2 份

- 桶：`other` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`reusable`
- 报告：`FabricMC__fabric-loader/1032`, `FabricMC__fabric-loader/714`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Minecraft\ game\ provider\ couldn''t\ locate\ the\ game!\ The\ game\ may\ be\ absent\ from\ th'
```

### 7. net.fabricmc.loader.impl.FormattedException: java.lang.RuntimeException: Could not execute entrypoin — 2 份

- 桶：`mod-loading` · 异常类：`java.lang.IllegalStateException`, `java.lang.NoSuchMethodException`
- 泛化判定：`reusable`
- 报告：`FabricMC__fabric-loader/651`, `FabricMC__fabric-loader/783`
- 建议 `when`：

```yaml
when:
  exception:
    - '^(java\.lang\.IllegalStateException|java\.lang\.NoSuchMethodException)$'
  exception_msg:
    - 'java\.lang\.RuntimeException:\ Could\ not\ execute\ entrypoint\ stage\ ''preLaunch''\ due\ t'
```

### 8. com.google.common.util.concurrent.ExecutionError: java.lang.StackOverflowError — 1 份

- 桶：`other` · 异常类：`java.lang.StackOverflowError`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/434`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.StackOverflowError$'
  exception_msg:
    - 'java\.lang\.StackOverflowError'
```

### 9. com.google.gson.JsonParseException: Unknown registry key in ResourceKey[minecraft:root / minecraft:r — 1 份

- 桶：`other` · 异常类：`com.google.gson.JsonParseException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/464`
- 建议 `when`：

```yaml
when:
  exception:
    - '^com\.google\.gson\.JsonParseException$'
  exception_msg:
    - 'Unknown\ registry\ key\ in\ ResourceKey\[minecraft:root\ /\ minecraft:recipe_serializer'
```

### 10. com.google.gson.JsonParseException: com.google.gson.stream.MalformedJsonException: Expected name at  — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/632`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'com\.google\.gson\.stream\.MalformedJsonException:\ Expected\ name\ at\ line\ 8\ column\ 6'
```

### 11. com.google.gson.JsonParseException: com.google.gson.stream.MalformedJsonException: Use JsonReader.se — 1 份

- 桶：`other` · 异常类：`java.lang.UnsupportedOperationException`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3731`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.UnsupportedOperationException$'
  exception_msg:
    - 'com\.google\.gson\.stream\.MalformedJsonException:\ Use\ JsonReader\.setLenient\(true\)\ t'
```

### 12. com.mojang.authlib.exceptions.InvalidCredentialsException: Status: 401 — 1 份

- 桶：`other` · 异常类：`java.lang.Exception`
- 泛化判定：`singleton+overfit` · 报告特有内容：long number
- 报告：`TheIllusiveC4__Curios/470`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.Exception$'
  exception_msg:
    - 'Status:\ 401'
```

### 13. io.netty.handler.codec.DecoderException: The received string length is longer than maximum allowed ( — 1 份

- 桶：`other` · 异常类：`io.netty.handler.codec.DecoderException`
- 泛化判定：`singleton`
- 报告：`TheIllusiveC4__Curios/346`
- 建议 `when`：

```yaml
when:
  exception:
    - '^io\.netty\.handler\.codec\.DecoderException$'
  exception_msg:
    - 'The\ received\ string\ length\ is\ longer\ than\ maximum\ allowed\ \(27\ >\ 25\)'
```

### 14. io.netty.handler.codec.DecoderException: Unknown serializer type 111 — 1 份

- 桶：`other` · 异常类：`io.netty.handler.codec.DecoderException`
- 泛化判定：`singleton+overfit` · 报告特有内容：long number
- 报告：`QuiltMC__quilt-loader/379`
- 建议 `when`：

```yaml
when:
  exception:
    - '^io\.netty\.handler\.codec\.DecoderException$'
  exception_msg:
    - 'Unknown\ serializer\ type\ 111'
```

### 15. io.netty.handler.codec.DecoderException: java.io.IOException: Packet play/clientbound/minecraft:leve — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 描述：`Packet handling error`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-api/4622`
- 建议 `when`：

```yaml
when:
  description:
    - 'Packet handling error'
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'java\.io\.IOException:\ Packet\ play/clientbound/minecraft:level_particles\ \(class_26'
```

### 16. io.netty.handler.codec.EncoderException: Failed to encode packet 'serverbound/minecraft:custom_paylo — 1 份

- 桶：`other` · 异常类：`io.netty.handler.codec.EncoderException`
- 描述：`Packet handling error`
- 泛化判定：`singleton`
- 报告：`McJtyMods__RFTools/2211`
- 建议 `when`：

```yaml
when:
  description:
    - 'Packet handling error'
  exception:
    - '^io\.netty\.handler\.codec\.EncoderException$'
  exception_msg:
    - 'Failed\ to\ encode\ packet\ ''serverbound/minecraft:custom_payload'''
```

### 17. java.io.FileNotFoundException: https://raw.githubusercontent.com/ToCraft/craftedcore/main/common/src — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`TeamTwilight__twilightforest/2534`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'https://raw\.githubusercontent\.com/ToCraft/craftedcore/main/common/src/main/resou'
```

### 18. java.io.IOException: File [G:\恢复\测试服务器-新\modernfix\structureCacheV1\apotheosis_tower_leaf_38f64271ea — 1 份

- 桶：`other` · 异常类：`java.io.FileNotFoundException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`embeddedt__ModernFix/485`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.FileNotFoundException$'
  exception_msg:
    - 'File\ \[G:\\恢复\\测试服务器\-新\\modernfix\\structureCacheV1\\apotheosis_tower_leaf_38f64271eab'
```

### 19. java.io.IOException: The handle is invalid — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/16`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'The\ handle\ is\ invalid'
```

### 20. java.io.UncheckedIOException: java.nio.file.AccessDeniedException: <HOME>\AppData\Roaming.minecraft\ — 1 份

- 桶：`other` · 异常类：`java.nio.file.AccessDeniedException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`FabricMC__fabric-loader/1080`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.nio\.file\.AccessDeniedException$'
  exception_msg:
    - 'java\.nio\.file\.AccessDeniedException:\ <HOME>\\AppData\\Roaming\.minecraft\\<INSTANCE>'
```

### 21. java.lang.ArrayIndexOutOfBoundsException: -1 — 1 份

- 桶：`other` · 异常类：`java.lang.ArrayIndexOutOfBoundsException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/7`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ArrayIndexOutOfBoundsException$'
  exception_msg:
    - '\-1'
```

### 22. java.lang.ArrayIndexOutOfBoundsException: 4 — 1 份

- 桶：`other` · 异常类：`java.lang.ArrayIndexOutOfBoundsException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/13`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ArrayIndexOutOfBoundsException$'
  exception_msg:
    - '4'
```

### 23. java.lang.ArrayIndexOutOfBoundsException: Index 4 out of bounds for length 4 — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.ArrayIndexOutOfBoundsException`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3893`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ArrayIndexOutOfBoundsException$'
  exception_msg:
    - 'Index\ 4\ out\ of\ bounds\ for\ length\ 4'
```

### 24. java.lang.ClassCastException: class com.thevortex.allthemodium.material.ATMTier cannot be cast to cl — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.ClassCastException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/534`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.ClassCastException$'
  exception_msg:
    - 'class\ com\.thevortex\.allthemodium\.material\.ATMTier\ cannot\ be\ cast\ to\ class\ net\.mi'
```

### 25. java.lang.ClassCastException: class net.minecraft.client.renderer.RenderType$CompositeRenderType can — 1 份

- 桶：`other` · 异常类：`java.lang.ClassCastException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-api/4738`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassCastException$'
  exception_msg:
    - 'class\ net\.minecraft\.client\.renderer\.RenderType\$CompositeRenderType\ cannot\ be\ cas'
```

### 26. java.lang.ClassNotFoundException: kotlin.jvm.internal.Lambda — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/613`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'kotlin\.jvm\.internal\.Lambda'
```

### 27. java.lang.ClassNotFoundException: net.fabricmc.loader.impl.launch.knot.KnotClient — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/821`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'net\.fabricmc\.loader\.impl\.launch\.knot\.KnotClient'
```

### 28. java.lang.ClassNotFoundException: net.minecraft.client.Minecraft — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/1034`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'net\.minecraft\.client\.Minecraft'
```

### 29. java.lang.ClassNotFoundException: net.minecraft.client.renderer.texture.AbstractTexture — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton`
- 报告：`TheIllusiveC4__Curios/391`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'net\.minecraft\.client\.renderer\.texture\.AbstractTexture'
```

### 30. java.lang.ClassNotFoundException: shadows.placebo.util.PlaceboTaskQueue — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/38`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'shadows\.placebo\.util\.PlaceboTaskQueue'
```

### 31. java.lang.Error: Invalid java.home value? 'D:' for vm 'OpenJDK 64-Bit Server VM' — 1 份

- 桶：`other` · 异常类：`java.lang.Error`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/400`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.Error$'
  exception_msg:
    - 'Invalid\ java\.home\ value\?\ ''D:''\ for\ vm\ ''OpenJDK\ 64\-Bit\ Server\ VM'''
```

### 32. java.lang.Error: Why would you set the warning level multiple times? — 1 份

- 桶：`other` · 异常类：`java.lang.Error`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/224`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.Error$'
  exception_msg:
    - 'Why\ would\ you\ set\ the\ warning\ level\ multiple\ times\?'
```

### 33. java.lang.IllegalArgumentException: Data for attachment 'worldgendevtools:feature_positions' was too — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 描述：`Exception chunk generation/loading`
- 泛化判定：`singleton+overfit` · 报告特有内容：long number
- 报告：`FabricMC__fabric-api/4669`
- 建议 `when`：

```yaml
when:
  description:
    - 'Exception chunk generation/loading'
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Data\ for\ attachment\ ''worldgendevtools:feature_positions''\ was\ too\ big\ \(32768\ byte'
```

### 34. java.lang.IllegalArgumentException: No value with id -1 — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 描述：`Packet handling error`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/515`
- 建议 `when`：

```yaml
when:
  description:
    - 'Packet handling error'
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'No\ value\ with\ id\ \-1'
```

### 35. java.lang.IllegalArgumentException: Payload may not be larger than 32767 bytes — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton+overfit` · 报告特有内容：long number
- 报告：`McJtyMods__RFTools/1898`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Payload\ may\ not\ be\ larger\ than\ 32767\ bytes'
```

### 36. java.lang.IllegalArgumentException: Unsupported class file major version 21845 — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton+overfit` · 报告特有内容：long number
- 报告：`FabricMC__fabric-loader/809`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Unsupported\ class\ file\ major\ version\ 21845'
```

### 37. java.lang.IllegalArgumentException: null — 1 份

- 桶：`watchdog` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton`
- 报告：`TeamTwilight__twilightforest/2450`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'null'
```

### 38. java.lang.IllegalArgumentException: unknown format type: lựa chọn  --> Note: this string translate t — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/871`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'unknown\ format\ type:\ lựa\ chọn\ \ \-\->\ Note:\ this\ string\ translate\ to\ "options"\ in\ e'
```

### 39. java.lang.IllegalStateException: Can't getDevice() before it was initialized — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/692`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Can''t\ getDevice\(\)\ before\ it\ was\ initialized'
```

### 40. java.lang.IllegalStateException: Capability missing for <UUID> — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.IllegalStateException`
- 泛化判定：`singleton`
- 报告：`TheIllusiveC4__Curios/463`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Capability\ missing\ for\ <UUID>'
```

### 41. java.lang.IllegalStateException: Not building! — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`mekanism__Mekanism/8376`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Not\ building!'
```

### 42. java.lang.IllegalStateException: Overflowed the mesh time buffer at 224x31 — 1 份

- 桶：`world-data` · 异常类：`java.lang.IllegalStateException`
- 描述：`Render Frame`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3809`
- 建议 `when`：

```yaml
when:
  description:
    - 'Render Frame'
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Overflowed\ the\ mesh\ time\ buffer\ at\ 224x31'
```

### 43. java.lang.IllegalStateException: Player is either on another team or not on any team. Cannot remove  — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 描述：`Packet handling error`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/959`
- 建议 `when`：

```yaml
when:
  description:
    - 'Packet handling error'
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Player\ is\ either\ on\ another\ team\ or\ not\ on\ any\ team\.\ Cannot\ remove\ from\ team\ ''Na'
```

### 44. java.lang.IllegalStateException: Texture is required if use_mob_texture is false — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 泛化判定：`singleton`
- 报告：`mekanism__Mekanism/8256`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Texture\ is\ required\ if\ use_mob_texture\ is\ false'
```

### 45. java.lang.IllegalStateException: Tried to lookup sprite, but atlas is not initialized — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/651`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Tried\ to\ lookup\ sprite,\ but\ atlas\ is\ not\ initialized'
```

### 46. java.lang.IncompatibleClassChangeError: Method 'int net.minecraft.world.item.ItemStack.getEnchantmen — 1 份

- 桶：`other` · 异常类：`java.lang.IncompatibleClassChangeError`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/645`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IncompatibleClassChangeError$'
  exception_msg:
    - 'Method\ ''int\ net\.minecraft\.world\.item\.ItemStack\.getEnchantmentLevel\(net\.minecraft'
```

### 47. java.lang.NullPointerException: Cannot invoke "com.wudji.xplusautofish.XPlusAutofish.tick(net.minecr — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.NullPointerException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/89`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "com\.wudji\.xplusautofish\.XPlusAutofish\.tick\(net\.minecraft\.client\.M'
```

### 48. java.lang.NullPointerException: Cannot invoke "it.unimi.dsi.fastutil.objects.ObjectArrayList.get(int — 1 份

- 桶：`other` · 异常类：`java.lang.NullPointerException`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/473`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "it\.unimi\.dsi\.fastutil\.objects\.ObjectArrayList\.get\(int\)"\ because\ "'
```

### 49. java.lang.NullPointerException: Cannot invoke "net.caffeinemc.mods.sodium.client.render.chunk.transl — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.NullPointerException`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3506`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "net\.caffeinemc\.mods\.sodium\.client\.render\.chunk\.translucent_sortin'
```

### 50. java.lang.NullPointerException: Cannot invoke "net.minecraft.class_2680.method_26227()" because the  — 1 份

- 桶：`other` · 异常类：`java.lang.NullPointerException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/877`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "net\.minecraft\.class_2680\.method_26227\(\)"\ because\ the\ return\ value'
```

### 51. java.lang.NullPointerException: Cannot invoke "net.minecraft.class_3222.method_5682()" because "play — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.NullPointerException`
- 描述：`Ticking player`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/947`
- 建议 `when`：

```yaml
when:
  description:
    - 'Ticking player'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "net\.minecraft\.class_3222\.method_5682\(\)"\ because\ "player"\ is\ null'
```

### 52. java.lang.NullPointerException: Cannot invoke "org.quiltmc.loader.api.VersionInterval.getMin()" beca — 1 份

- 桶：`other` · 异常类：`java.lang.NullPointerException`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/296`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "org\.quiltmc\.loader\.api\.VersionInterval\.getMin\(\)"\ because\ "this\.qu'
```

### 53. java.lang.NullPointerException: Cannot invoke "xaero.map.graphics.GLObjectDeleter.work()" because "x — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.NullPointerException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/86`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Cannot\ invoke\ "xaero\.map\.graphics\.GLObjectDeleter\.work\(\)"\ because\ "xaero\.map\.Wor'
```

### 54. java.lang.NullPointerException: Trying to access unbound value: ResourceKey[minecraft:block / aether — 1 份

- 桶：`other` · 异常类：`java.lang.NullPointerException`
- 描述：`Unexpected error`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3728`
- 建议 `when`：

```yaml
when:
  description:
    - 'Unexpected error'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'Trying\ to\ access\ unbound\ value:\ ResourceKey\[minecraft:block\ /\ aether:skyroot_log'
```

### 55. java.lang.NullPointerException: entité de bloc à cocher — 1 份

- 桶：`other` · 异常类：`java.lang.NullPointerException`
- 描述：`entité de blocage`
- 泛化判定：`singleton`
- 报告：`McJtyMods__RFTools/1995`
- 建议 `when`：

```yaml
when:
  description:
    - 'entité de blocage'
  exception:
    - '^java\.lang\.NullPointerException$'
  exception_msg:
    - 'entité\ de\ bloc\ à\ cocher'
```

### 56. java.lang.RuntimeException: Could not create directory <HOME>\AppData\Roaming\.minecraft\<INSTANCE>\ — 1 份

- 桶：`other` · 异常类：`java.nio.file.NoSuchFileException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`FabricMC__fabric-loader/805`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.nio\.file\.NoSuchFileException$'
  exception_msg:
    - 'Could\ not\ create\ directory\ <HOME>\\AppData\\Roaming\\\.minecraft\\<INSTANCE>\\iris\-res'
```

### 57. java.lang.RuntimeException: Could not execute entrypoint stage 'client' due to errors, provided by ' — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalArgumentException`
- 描述：`Initializing game`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/1153`
- 建议 `when`：

```yaml
when:
  description:
    - 'Initializing game'
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Could\ not\ execute\ entrypoint\ stage\ ''client''\ due\ to\ errors,\ provided\ by\ ''fabric\-r'
```

### 58. java.lang.RuntimeException: Error creating Mixin config fabric-crash-report-info-v1.mixins.json for  — 1 份

- 桶：`mixin` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/750`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Error\ creating\ Mixin\ config\ fabric\-crash\-report\-info\-v1\.mixins\.json\ for\ mod\ fabr'
```

### 59. java.lang.RuntimeException: Error creating Mixin config omega-config.mixins.json for mod omega-confi — 1 份

- 桶：`mixin` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/620`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'Error\ creating\ Mixin\ config\ omega\-config\.mixins\.json\ for\ mod\ omega\-config'
```

### 60. java.lang.RuntimeException: Exception thrown while executing job — 1 份

- 桶：`other` · 异常类：`net.minecraft.world.level.chunk.MissingPaletteEntryException`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3879`
- 建议 `when`：

```yaml
when:
  exception:
    - '^net\.minecraft\.world\.level\.chunk\.MissingPaletteEntryException$'
  exception_msg:
    - 'Exception\ thrown\ while\ executing\ job'
```

### 61. java.lang.RuntimeException: Fabric permissions version 0.4.0-SNAPSHOT is not supported. Please updat — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/650`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'Fabric\ permissions\ version\ 0\.4\.0\-SNAPSHOT\ is\ not\ supported\.\ Please\ update\ Fabric'
```

### 62. java.lang.RuntimeException: Failed to load class file for 'net.minecraft.client.main.Main'! — 1 份

- 桶：`other` · 异常类：`java.io.FileNotFoundException`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/463`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.FileNotFoundException$'
  exception_msg:
    - 'Failed\ to\ load\ class\ file\ for\ ''net\.minecraft\.client\.main\.Main''!'
```

### 63. java.lang.RuntimeException: Failed to read accessWidener file from mod wurst — 1 份

- 桶：`other` · 异常类：`net.fabricmc.loader.impl.lib.accesswidener.AccessWidenerFormatException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/939`
- 建议 `when`：

```yaml
when:
  exception:
    - '^net\.fabricmc\.loader\.impl\.lib\.accesswidener\.AccessWidenerFormatException$'
  exception_msg:
    - 'Failed\ to\ read\ accessWidener\ file\ from\ mod\ wurst'
```

### 64. java.lang.RuntimeException: Failed to read classTweaker file from mod fabric-biome-api-v1 — 1 份

- 桶：`other` · 异常类：`net.fabricmc.loader.impl.lib.classtweaker.reader.ClassTweakerFormatException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-api/5046`
- 建议 `when`：

```yaml
when:
  exception:
    - '^net\.fabricmc\.loader\.impl\.lib\.classtweaker\.reader\.ClassTweakerFormatException$'
  exception_msg:
    - 'Failed\ to\ read\ classTweaker\ file\ from\ mod\ fabric\-biome\-api\-v1'
```

### 65. java.lang.RuntimeException: Non-unique Mixin config name mixins.reach-entity-attributes.json used by — 1 份

- 桶：`other` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/778`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Non\-unique\ Mixin\ config\ name\ mixins\.reach\-entity\-attributes\.json\ used\ by\ the\ mod'
```

### 66. java.lang.RuntimeException: Non-unique Mixin config name xlpackets.mixins.json used by the mods thic — 1 份

- 桶：`other` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/834`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Non\-unique\ Mixin\ config\ name\ xlpackets\.mixins\.json\ used\ by\ the\ mods\ thiccpackets'
```

### 67. java.lang.RuntimeException: Sodium mod config not found — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3832`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Sodium\ mod\ config\ not\ found'
```

### 68. java.lang.RuntimeException: Unfixable conflicts — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/905`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Unfixable\ conflicts'
```

### 69. java.lang.RuntimeException: Unknown variable: BIOME_PALE_GARDEN — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/563`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'Unknown\ variable:\ BIOME_PALE_GARDEN'
```

### 70. java.lang.RuntimeException: broken shader file — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.RuntimeException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/883`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.RuntimeException$'
  exception_msg:
    - 'broken\ shader\ file'
```

### 71. java.lang.RuntimeException: error remapping game jars [<HOME>\AppData\Roaming\com.modrinth.theseus\m — 1 份

- 桶：`other` · 异常类：`java.nio.file.NoSuchFileException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`FabricMC__fabric-loader/863`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.nio\.file\.NoSuchFileException$'
  exception_msg:
    - 'error\ remapping\ game\ jars\ \[<HOME>\\AppData\\Roaming\\com\.modrinth\.theseus\\meta\\vers'
```

### 72. java.lang.RuntimeException: error remapping game jars [F:\Modded MC\curseforge\minecraft\Install\ver — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`FabricMC__fabric-api/4986`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'error\ remapping\ game\ jars\ \[F:\\Modded\ MC\\curseforge\\minecraft\\Install\\versions\\fa'
```

### 73. java.lang.RuntimeException: java.util.concurrent.ExecutionException: java.lang.ArrayIndexOutOfBounds — 1 份

- 桶：`other` · 异常类：`java.lang.ArrayIndexOutOfBoundsException`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/482`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ArrayIndexOutOfBoundsException$'
  exception_msg:
    - 'java\.util\.concurrent\.ExecutionException:\ java\.lang\.ArrayIndexOutOfBoundsExceptio'
```

### 74. java.lang.RuntimeException: net.fabricmc.loader.api.VersionParsingException: Could not parse version — 1 份

- 桶：`other` · 异常类：`java.lang.NumberFormatException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/945`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.NumberFormatException$'
  exception_msg:
    - 'net\.fabricmc\.loader\.api\.VersionParsingException:\ Could\ not\ parse\ version\ number'
```

### 75. java.lang.StackOverflowError: Exception in server tick loop — 1 份

- 桶：`other` · 异常类：`java.lang.StackOverflowError`
- 描述：`Exception in server tick loop`
- 泛化判定：`singleton`
- 报告：`SlimeKnights__TinkersConstruct/5446`
- 建议 `when`：

```yaml
when:
  description:
    - 'Exception in server tick loop'
  exception:
    - '^java\.lang\.StackOverflowError$'
  exception_msg:
    - 'Exception\ in\ server\ tick\ loop'
```

### 76. java.lang.StackOverflowError: null — 1 份

- 桶：`other` · 异常类：`java.lang.StackOverflowError`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/710`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.StackOverflowError$'
  exception_msg:
    - 'null'
```

### 77. java.lang.StringIndexOutOfBoundsException: Range [16, 13) out of bounds for length 45 — 1 份

- 桶：`other` · 异常类：`java.lang.StringIndexOutOfBoundsException`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/474`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.StringIndexOutOfBoundsException$'
  exception_msg:
    - 'Range\ \[16,\ 13\)\ out\ of\ bounds\ for\ length\ 45'
```

### 78. java.lang.Throwable: null — 1 份

- 桶：`other` · 异常类：`java.lang.Throwable`
- 泛化判定：`singleton`
- 报告：`QuiltMC__quilt-loader/233`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.Throwable$'
  exception_msg:
    - 'null'
```

### 79. java.lang.TypeNotPresentException: Type kts/dev/common/A not present — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.ClassNotFoundException`
- 泛化判定：`singleton+overfit` · 报告特有内容：path
- 报告：`FabricMC__fabric-loader/900`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.ClassNotFoundException$'
  exception_msg:
    - 'Type\ kts/dev/common/A\ not\ present'
```

### 80. java.lang.UnsatisfiedLinkError: Failed to locate library: liblwjgl.so — 1 份

- 桶：`native` · 异常类：`java.lang.UnsatisfiedLinkError`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/977`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.UnsatisfiedLinkError$'
  exception_msg:
    - 'Failed\ to\ locate\ library:\ liblwjgl\.so'
```

### 81. java.lang.UnsupportedOperationException: Reflective setAccessible(true) disabled — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 泛化判定：`singleton`
- 报告：`TeamTwilight__twilightforest/2666`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'Reflective\ setAccessible\(true\)\ disabled'
```

### 82. java.net.ConnectException: Connection timed out: connect — 1 份

- 桶：`other` · 异常类：`java.net.SocketException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/108`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.net\.SocketException$'
  exception_msg:
    - 'Connection\ timed\ out:\ connect'
```

### 83. java.net.SocketTimeoutException: connect timed out — 1 份

- 桶：`other` · 异常类：`java.net.SocketTimeoutException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/37`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.net\.SocketTimeoutException$'
  exception_msg:
    - 'connect\ timed\ out'
```

### 84. java.net.http.HttpConnectTimeoutException: HTTP connect timed out — 1 份

- 桶：`other` · 异常类：`java.net.ConnectException`
- 泛化判定：`singleton`
- 报告：`TeamTwilight__twilightforest/2550`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.net\.ConnectException$'
  exception_msg:
    - 'HTTP\ connect\ timed\ out'
```

### 85. java.net.http.HttpTimeoutException: request timed out — 1 份

- 桶：`other` · 异常类：`java.net.http.HttpTimeoutException`
- 泛化判定：`singleton`
- 报告：`TeamTwilight__twilightforest/2467`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.net\.http\.HttpTimeoutException$'
  exception_msg:
    - 'request\ timed\ out'
```

### 86. java.nio.file.NoSuchFileException: config\metadata.json — 1 份

- 桶：`other` · 异常类：`com.google.gson.stream.MalformedJsonException`
- 泛化判定：`singleton`
- 报告：`TeamTwilight__twilightforest/2487`
- 建议 `when`：

```yaml
when:
  exception:
    - '^com\.google\.gson\.stream\.MalformedJsonException$'
  exception_msg:
    - 'config\\metadata\.json'
```

### 87. java.util.ConcurrentModificationException: null — 1 份

- 桶：`other` · 异常类：`java.util.ConcurrentModificationException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/497`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.util\.ConcurrentModificationException$'
  exception_msg:
    - 'null'
```

### 88. java.util.ServiceConfigurationError: org.spongepowered.asm.service.IMixinServiceBootstrap: Provider  — 1 份

- 桶：`other` · 异常类：`org.spongepowered.asm.service.ServiceNotAvailableError`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/811`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.service\.ServiceNotAvailableError$'
  exception_msg:
    - 'org\.spongepowered\.asm\.service\.IMixinServiceBootstrap:\ Provider\ net\.fabricmc\.load'
```

### 89. java.util.concurrent.CompletionException: java.lang.ClassCastException: class net.minecraft.world.le — 1 份

- 桶：`mod-bug` · 异常类：`java.lang.ClassCastException`
- 描述：`Exception in server tick loop`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/45`
- 建议 `when`：

```yaml
when:
  description:
    - 'Exception in server tick loop'
  exception:
    - '^java\.lang\.ClassCastException$'
  exception_msg:
    - 'java\.lang\.ClassCastException:\ class\ net\.minecraft\.world\.level\.block\.entity\.Block'
```

### 90. java.util.concurrent.CompletionException: java.lang.NoSuchMethodError: 'net.minecraft.nbt.ListTag co — 1 份

- 桶：`other` · 异常类：`java.util.concurrent.CompletionException`
- 泛化判定：`singleton`
- 报告：`Snownee__Jade/468`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.util\.concurrent\.CompletionException$'
  exception_msg:
    - 'java\.lang\.NoSuchMethodError:\ ''net\.minecraft\.nbt\.ListTag\ com\.simibubi\.create\.cont'
```

### 91. java.util.concurrent.CompletionException: java.lang.RuntimeException: could not reload shaders — 1 份

- 桶：`other` · 异常类：`java.io.IOException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/931`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.io\.IOException$'
  exception_msg:
    - 'java\.lang\.RuntimeException:\ could\ not\ reload\ shaders'
```

### 92. net.fabricmc.fabric.impl.registry.sync.RemapException: Received 4 registry entries that are unknown  — 1 份

- 桶：`mod-bug` · 异常类：`net.fabricmc.fabric.impl.registry.sync.RemapException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-api/4753`
- 建议 `when`：

```yaml
when:
  exception:
    - '^net\.fabricmc\.fabric\.impl\.registry\.sync\.RemapException$'
  exception_msg:
    - 'Received\ 4\ registry\ entries\ that\ are\ unknown\ to\ this\ client\.'
```

### 93. net.fabricmc.loader.impl.FormattedException: java.lang.IllegalArgumentException: Invalid UUID string — 1 份

- 桶：`mod-loading` · 异常类：`java.lang.IllegalArgumentException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/913`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalArgumentException$'
  exception_msg:
    - 'java\.lang\.IllegalArgumentException:\ Invalid\ UUID\ string'
```

### 94. net.fabricmc.loader.impl.FormattedException: joptsimple.MultipleArgumentsForOptionException: Found m — 1 份

- 桶：`mod-loading` · 异常类：`joptsimple.MultipleArgumentsForOptionException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/955`
- 建议 `when`：

```yaml
when:
  exception:
    - '^joptsimple\.MultipleArgumentsForOptionException$'
  exception_msg:
    - 'joptsimple\.MultipleArgumentsForOptionException:\ Found\ multiple\ arguments\ for\ opt'
```

### 95. net.minecraft.ReportedException: Exception generating new chunk — 1 份

- 桶：`other` · 异常类：`java.lang.IllegalStateException`
- 泛化判定：`singleton`
- 报告：`McJtyMods__RFTools/2192`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.IllegalStateException$'
  exception_msg:
    - 'Exception\ generating\ new\ chunk'
```

### 96. net.minecraft.ReportedException: Manually triggered debug crash — 1 份

- 桶：`other` · 异常类：`java.lang.Throwable`
- 描述：`Manually triggered debug crash`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3627`
- 建议 `when`：

```yaml
when:
  description:
    - 'Manually triggered debug crash'
  exception:
    - '^java\.lang\.Throwable$'
  exception_msg:
    - 'Manually\ triggered\ debug\ crash'
```

### 97. net.minecraftforge.fml.LoadingFailedException: Loading errors encountered: [ — 1 份

- 桶：`other` · 异常类：`net.minecraftforge.fml.LoadingFailedException`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/74`
- 建议 `when`：

```yaml
when:
  exception:
    - '^net\.minecraftforge\.fml\.LoadingFailedException$'
  exception_msg:
    - 'Loading\ errors\ encountered:\ \['
```

### 98. net.neoforged.neoforge.logging.CrashReportExtender$ModLoadingCrashException: Mod loading has failed — 1 份

- 桶：`mod-loading` · 异常类：`net.neoforged.neoforge.logging.CrashReportExtender$ModLoadingCrashException`
- 描述：`Mod loading failures have occurred; consult the issue messages for more details`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3853`
- 建议 `when`：

```yaml
when:
  description:
    - 'Mod loading failures have occurred; consult the issue messages for more details'
  exception:
    - '^net\.neoforged\.neoforge\.logging\.CrashReportExtender\$ModLoadingCrashException$'
  exception_msg:
    - 'Mod\ loading\ has\ failed'
```

### 99. org.gradle.api.internal.tasks.testing.TestSuiteExecutionException: Could not start Gradle Test Execu — 1 份

- 桶：`other` · 异常类：`java.lang.AssertionError`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/987`
- 建议 `when`：

```yaml
when:
  exception:
    - '^java\.lang\.AssertionError$'
  exception_msg:
    - 'Could\ not\ start\ Gradle\ Test\ Executor\ 15\.'
```

### 100. org.gradle.api.plugins.UnknownPluginException: Plugin [id: 'fabric-loom', version: '1.3-SNAPSHOT'] w — 1 份

- 桶：`mod-bug` · 异常类：`org.gradle.api.plugins.UnknownPluginException`
- 泛化判定：`singleton`
- 报告：`FabricMC__fabric-loader/835`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.gradle\.api\.plugins\.UnknownPluginException$'
  exception_msg:
    - 'Plugin\ \[id:\ ''fabric\-loom'',\ version:\ ''1\.3\-SNAPSHOT''\]\ was\ not\ found\ in\ any\ of\ the'
```

### 101. org.spongepowered.asm.mixin.injection.throwables.InvalidInjectionException: Invalid descriptor on fa — 1 份

- 桶：`mixin` · 异常类：`org.spongepowered.asm.mixin.injection.throwables.InvalidInjectionException`
- 泛化判定：`singleton`
- 报告：`TheIllusiveC4__Curios/410`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.injection\.throwables\.InvalidInjectionException$'
  exception_msg:
    - 'Invalid\ descriptor\ on\ fastanim\.mixins\.json:ParrotEntityModelMixin\ from\ mod\ faste'
```

### 102. org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException: net.minecraft.server.world.Serve — 1 份

- 桶：`other` · 异常类：`org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/533`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.throwables\.ClassAlreadyLoadedException$'
  exception_msg:
    - 'net\.minecraft\.server\.world\.ServerChunkLoadingManager\ was\ already\ classloaded'
```

### 103. org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException: net.minecraft.world.World was al — 1 份

- 桶：`other` · 异常类：`org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedException`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/534`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.throwables\.ClassAlreadyLoadedException$'
  exception_msg:
    - 'net\.minecraft\.world\.World\ was\ already\ classloaded'
```

### 104. org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException: @Shadow field overlay was  — 1 份

- 桶：`mixin` · 异常类：`org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException`
- 泛化判定：`singleton`
- 报告：`embeddedt__ModernFix/676`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.transformer\.throwables\.InvalidMixinException$'
  exception_msg:
    - '@Shadow\ field\ overlay\ was\ not\ located\ in\ the\ target\ class\ net\.minecraft\.client\.M'
```

### 105. org.spongepowered.asm.mixin.transformer.throwables.InvalidMixinException: @Shadow field val$p_434753 — 1 份

- 桶：`mixin` · 异常类：`org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError`
- 泛化判定：`singleton+overfit` · 报告特有内容：mixin shadow field
- 报告：`CaffeineMC__sodium/3460`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.transformer\.throwables\.MixinTransformerError$'
  exception_msg:
    - '@Shadow\ field\ val\$p_434753_\ was\ not\ located\ in\ the\ target\ class\ net\.minecraft\.cl'
```

### 106. org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError: An unexpected critical err — 1 份

- 桶：`mixin` · 异常类：`org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError`
- 描述：`Initializing game`
- 泛化判定：`singleton`
- 报告：`CaffeineMC__sodium/3693`
- 建议 `when`：

```yaml
when:
  description:
    - 'Initializing game'
  exception:
    - '^org\.spongepowered\.asm\.mixin\.transformer\.throwables\.MixinTransformerError$'
  exception_msg:
    - 'An\ unexpected\ critical\ error\ was\ encountered'
```

### 107. org.spongepowered.asm.mixin.transformer.throwables.ReEntrantTransformerError: Re-entrance error. — 1 份

- 桶：`other` · 异常类：`org.spongepowered.asm.mixin.transformer.throwables.ReEntrantTransformerError`
- 泛化判定：`singleton`
- 报告：`Shadows-of-Fire__Placebo/17`
- 建议 `when`：

```yaml
when:
  exception:
    - '^org\.spongepowered\.asm\.mixin\.transformer\.throwables\.ReEntrantTransformerError$'
  exception_msg:
    - 'Re\-entrance\ error\.'
```

## 怎么用（人在环，两步）

1. **写**：把某个聚类（或几个聚类）写成候选 YAML，放到任意临时路径。`lifecycle_status` 必须是 `draft`，`id` 必须以 `candidate.` 开头，`provenance.fixtures` 必须指向真实存在的报告，并带 `generated_by: {model, date}`。
2. **过闸**：

```bash
python tools/suggest_rules.py --ingest <候选.yaml> \
    --model "<生成模型名>" --date <YYYY-MM-DD>
```

工具会拒收以下任一情况：不是 `draft`、`id` 前缀不对、fixture 不存在、缺 `generated_by`、以及**在语料上一份报告都不命中**（写不出证据的规则就是死重量）。通过后落到 `corpus/rule-drafts/`，**永远不进 `mcd/rules/builtin/`**。

`tests/test_rule_drafts.py` 对 `corpus/rule-drafts/` 复查同一组约束，`tests/test_rule_metadata.py::test_no_draft_rule_is_in_builtin` 保证草稿不会混进发货规则。
