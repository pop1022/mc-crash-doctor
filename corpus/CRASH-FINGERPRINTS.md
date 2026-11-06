# 崩溃指纹聚类（D3 / R11 验收）

> 生成：`python tools/crash_fingerprints.py`。语料 454 份，
> 成功解析 454 份 → **377 个指纹**，平均簇 1.20，
> 多成员簇 38 个。

指纹 = `(loader, 根因 kind + 归一化 message, top suspect, 顶层帧)`。
报告 id、时间戳、路径、数字一律不进指纹——它们只会让同一个 bug 的两份日志
看起来不同。

## R11：过粗合并的判据

一个簇里出现 **>1 种 description**，说明它把不同的问题合在了一起。
本次：7 / 38 个多成员簇混合了 description。
下表把每个簇的差异全部列出来，合并是否可接受由人判断，工具不替人删。

| 指纹 | 份数 | 不同描述 | 不同规则 | 根因 |
|---|---:|---:|---:|---|
| `014753faa504` | 13 | 1 | 2 | `java.lang.IllegalStateException: Failed to load registries d` |
| `6ad2fd720379` | 12 | 1 | 1 | `net.fabricmc.loader.impl.FormattedException: Some of your mo` |
| `ec61182395e6` | 10 | 2 | 1 | `java.lang.ClassNotFoundException: net.minecraft.client.gui.t` |
| `41d75b0912ad` | 4 | 1 | 1 | `java.lang.Exception: Mod Loading has failed` |
| `364ca0648e83` | 3 | 1 | 1 | `java.lang.RuntimeException: Minecraft game provider couldn't` |
| `5022698ac40a` | 3 | 1 | 3 | `java.lang.IllegalStateException: Expected BEGIN_OBJECT but w` |
| `56ed6ba004db` | 3 | 1 | 1 | `java.util.zip.ZipException: zip END header not found` |
| `78134c701d15` | 3 | 1 | 0 | `java.lang.IllegalArgumentException: The specified resource '` |
| `79a42ca3a4c1` | 3 | 1 | 2 | `java.lang.NullPointerException: Cannot invoke "net.fabricmc.` |
| `8c8857805426` | 3 | 1 | 0 | `java.lang.Throwable: Manually triggered debug crash` |
| `cc3c2aba3f43` | 3 | 1 | 1 | `java.net.UnknownHostException: api.minecraftservices.com` |
| `fb16d086478e` | 3 | 1 | 1 | `java.lang.UnsupportedClassVersionError: net/minecraft/bundle` |
| `028f08acc315` | 2 | 2 | 1 | `java.lang.IllegalArgumentException: TranslatableContents' ar` |
| `17ad3c8eb238` | 2 | 1 | 2 | `java.lang.IllegalArgumentException: No known containers for ` |
| `2a2e284ef827` | 2 | 2 | 2 | `` |
| `318c6c560df3` | 2 | 2 | 2 | `java.lang.IllegalArgumentException: No model for layer twili` |
| `3aabfc106bed` | 2 | 1 | 1 | `java.lang.Error: ServerHangWatchdog detected that a single s` |
| `41e88ce65b8c` | 2 | 1 | 0 | `java.lang.UnsatisfiedLinkError: Unable to load library 'flit` |
| `476cf40303fa` | 2 | 1 | 1 | `org.spongepowered.asm.mixin.transformer.throwables.InvalidMi` |
| `5576fd3d0d6a` | 2 | 1 | 2 | `java.util.zip.ZipException: zip file is empty` |
| `572c5826f853` | 2 | 1 | 0 | `java.lang.Throwable: Manually triggered debug crash` |
| `5f07375b20f5` | 2 | 1 | 3 | `org.spongepowered.asm.mixin.injection.throwables.InjectionEr` |
| `6a1f6ce41b69` | 2 | 1 | 2 | `com.electronwill.nightconfig.core.io.ParsingException: Not e` |
| `749bb384a71c` | 2 | 2 | 1 | `java.lang.RuntimeException` |
| `88fde7ebcb7a` | 2 | 1 | 0 | `java.lang.ClassNotFoundException: kotlin.jvm.internal.Lambda` |
| `89d6abb79cf0` | 2 | 2 | 4 | `java.lang.NullPointerException: Cannot invoke "net.minecraft` |
| `91befd6401f2` | 2 | 1 | 1 | `java.lang.ClassCastException: Cannot coerce loader value to ` |
| `93021e67d23a` | 2 | 1 | 2 | `java.lang.Exception: Mod Loading has failed` |
| `970476202cea` | 2 | 1 | 1 | `org.spongepowered.asm.mixin.throwables.ClassAlreadyLoadedExc` |
| `9a9ac5dc9568` | 2 | 2 | 2 | `java.lang.IllegalStateException: Can't access registry Resou` |
| `9fcb91f8785b` | 2 | 1 | 1 | `net.neoforged.fml.ModLoadingException: Loading errors encoun` |
| `a6c2e2708044` | 2 | 1 | 1 | `net.fabricmc.loader.impl.FormattedException: Mod resolution ` |
| `ba33bd6955a4` | 2 | 1 | 1 | `net.fabricmc.loader.impl.FormattedException: Mod resolution ` |
| `ba5963a7fdb1` | 2 | 1 | 1 | `java.util.zip.ZipException: zip END header not found` |
| `ca32a2961f62` | 2 | 1 | 1 | `com.electronwill.nightconfig.core.io.ParsingException: Inval` |
| `cfdcdaac283e` | 2 | 1 | 1 | `java.lang.UnsupportedOperationException: Attempted to retrie` |
| `d28736a7b9c9` | 2 | 1 | 2 | `java.lang.ClassNotFoundException: mod.azure.azurelib.rewrite` |
| `d28c4caf7274` | 2 | 1 | 1 | `java.lang.UnsupportedOperationException` |

## 每个多成员簇的成员与差异

### `014753faa504` — 13 份

- `4862.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `4909.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5049.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5102.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5147.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5208.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5234.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5237.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5269.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5343.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5356.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5360.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod
- `5407.crash.txt` [fabric] desc=`mouseClicked event handler` rules=crash.registry-load-failed,crash.runtime-mod

### `6ad2fd720379` — 12 份

- `3524.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3813.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3816.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3819.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3845.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3861.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3864.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `3907.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `5197.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `5362.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `1035.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `1039.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set

### `ec61182395e6` — 10 份

- **不同描述**: `(空)` / `Initializing game`
- `535.crash.txt` [fabric] desc=`(空)` rules=mod.coremod-missing
- `4491.crash.txt` [fabric] desc=`Initializing game` rules=mod.coremod-missing
- `1027.crash.txt` [fabric] desc=`Initializing game` rules=mod.coremod-missing
- `1100.crash.txt` [fabric] desc=`(空)` rules=mod.coremod-missing
- `711.crash.txt` [fabric] desc=`Initializing game` rules=mod.coremod-missing
- `821.crash.txt` [fabric] desc=`(空)` rules=-
- `827.crash.txt` [fabric] desc=`Initializing game` rules=mod.coremod-missing
- `882.crash.txt` [fabric] desc=`(空)` rules=mod.coremod-missing
- `900.crash.txt` [fabric] desc=`(空)` rules=-
- `622.crash.txt` [fabric] desc=`(空)` rules=mod.coremod-missing

### `41d75b0912ad` — 4 份

- `8391.crash.txt` [forge] desc=`Mod loading error has occurred` rules=mod.load-failed.fabric-entry
- `8479.crash.txt` [forge] desc=`Mod loading error has occurred` rules=mod.load-failed.fabric-entry
- `344.crash.txt` [forge] desc=`Mod loading error has occurred` rules=mod.load-failed.fabric-entry
- `509.crash.txt` [forge] desc=`Mod loading error has occurred` rules=mod.load-failed.fabric-entry

### `364ca0648e83` — 3 份

- `1032.crash.txt` [fabric] desc=`(空)` rules=loader.game-provider-missing
- `1093.crash.txt` [fabric] desc=`(空)` rules=loader.game-provider-missing
- `714.crash.txt` [fabric] desc=`(空)` rules=loader.game-provider-missing

### `5022698ac40a` — 3 份

- `2533.crash.txt` [neoforge] desc=`(空)` rules=crash.datapack-book,mod.config-invalid,net.connectivity
- `2541.crash.txt` [neoforge] desc=`(空)` rules=mod.config-invalid
- `2577.crash.txt` [neoforge] desc=`(空)` rules=mod.config-invalid

### `56ed6ba004db` — 3 份

- `1110.crash.txt` [fabric] desc=`(空)` rules=mod.corrupt-jar
- `852.crash.txt` [fabric] desc=`(空)` rules=mod.corrupt-jar
- `958.crash.txt` [fabric] desc=`(空)` rules=mod.corrupt-jar

### `78134c701d15` — 3 份

- `1135.crash.txt` [fabric] desc=`(空)` rules=-
- `620.crash.txt` [fabric] desc=`(空)` rules=-
- `750.crash.txt` [fabric] desc=`(空)` rules=-

### `79a42ca3a4c1` — 3 份

- `4641.crash.txt` [fabric] desc=`Rendering entity in world` rules=crash.rendering,crash.rendering-entity
- `859.crash.txt` [fabric] desc=`Rendering entity in world` rules=crash.rendering,crash.rendering-entity
- `938.crash.txt` [fabric] desc=`Rendering entity in world` rules=crash.rendering,crash.rendering-entity

### `8c8857805426` — 3 份

- `3473.crash.txt` [fabric] desc=`Manually triggered debug crash` rules=-
- `3505.crash.txt` [fabric] desc=`Manually triggered debug crash` rules=-
- `3873.crash.txt` [fabric] desc=`Manually triggered debug crash` rules=-

### `cc3c2aba3f43` — 3 份

- `2389.crash.txt` [forge] desc=`(空)` rules=net.connectivity
- `2390.crash.txt` [forge] desc=`(空)` rules=net.connectivity
- `2391.crash.txt` [forge] desc=`(空)` rules=net.connectivity

### `fb16d086478e` — 3 份

- `641.crash.txt` [fabric] desc=`(空)` rules=java.class-version
- `736.crash.txt` [fabric] desc=`(空)` rules=java.class-version
- `766.crash.txt` [fabric] desc=`(空)` rules=java.class-version

### `028f08acc315` — 2 份

- **不同描述**: `Narrating screen` / `Unexpected error`
- `776.crash.txt` [neoforge] desc=`Narrating screen` rules=crash.runtime-mod
- `777.crash.txt` [neoforge] desc=`Unexpected error` rules=crash.runtime-mod

### `17ad3c8eb238` — 2 份

- `8276.crash.txt` [neoforge] desc=`Rendering screen` rules=crash.rendering,crash.runtime-mod
- `8304.crash.txt` [neoforge] desc=`Rendering screen` rules=crash.rendering,crash.runtime-mod

### `2a2e284ef827` — 2 份

- **不同描述**: `Loading screen debug info` / `Ticking entity`
- `8550.crash.txt` [forge] desc=`Loading screen debug info` rules=mod.load-fatal
- `2618.crash.txt` [forge] desc=`Ticking entity` rules=crash.ticking-entity

### `318c6c560df3` — 2 份

- **不同描述**: `Rendering overlay` / `Unexpected error`
- `2517.crash.txt` [neoforge] desc=`Unexpected error` rules=crash.runtime-mod
- `2543.crash.txt` [neoforge] desc=`Rendering overlay` rules=crash.rendering,crash.runtime-mod

### `3aabfc106bed` — 2 份

- `8291.crash.txt` [neoforge] desc=`Watching Server` rules=hang.watchdog
- `8389.crash.txt` [neoforge] desc=`Watching Server` rules=hang.watchdog

### `41e88ce65b8c` — 2 份

- `423.crash.txt` [neoforge] desc=`(空)` rules=-
- `543.crash.txt` [neoforge] desc=`(空)` rules=-

### `476cf40303fa` — 2 份

- `321.crash.txt` [forge] desc=`(空)` rules=mixin.apply-failed
- `322.crash.txt` [forge] desc=`(空)` rules=mixin.apply-failed

### `5576fd3d0d6a` — 2 份

- `4907.crash.txt` [fabric] desc=`(空)` rules=mod.corrupt-jar,mod.incompatible-set
- `5179.crash.txt` [fabric] desc=`(空)` rules=mod.corrupt-jar,mod.incompatible-set

### `572c5826f853` — 2 份

- `3627.crash.txt` [fabric] desc=`Manually triggered debug crash` rules=-
- `3915.crash.txt` [fabric] desc=`Manually triggered debug crash` rules=-

### `5f07375b20f5` — 2 份

- `1006.crash.txt` [fabric] desc=`(空)` rules=crash.runtime-mod,mixin.apply-failed,mixin.injection-failed
- `1007.crash.txt` [fabric] desc=`(空)` rules=crash.runtime-mod,mixin.apply-failed,mixin.injection-failed

### `6a1f6ce41b69` — 2 份

- `389.crash.txt` [forge] desc=`Exception in server tick loop` rules=mod.config-invalid,quilt.config-broken
- `573.crash.txt` [forge] desc=`Exception in server tick loop` rules=mod.config-invalid,quilt.config-broken

### `749bb384a71c` — 2 份

- **不同描述**: `Exception in server tick loop` / `Initializing game`
- `1902.crash.txt` [forge] desc=`Initializing game` rules=crash.runtime-mod
- `1953.crash.txt` [forge] desc=`Exception in server tick loop` rules=crash.runtime-mod

### `88fde7ebcb7a` — 2 份

- `613.crash.txt` [forge] desc=`(空)` rules=-
- `391.crash.txt` [forge] desc=`(空)` rules=-

### `89d6abb79cf0` — 2 份

- **不同描述**: `(空)` / `Feature placement`
- `2392.crash.txt` [forge] desc=`(空)` rules=crash.runtime-mod,mod.config-invalid,mod.coremod-missing,perf.tick-timeout
- `2514.crash.txt` [forge] desc=`Feature placement` rules=crash.runtime-mod

### `91befd6401f2` — 2 份

- `368.crash.txt` [quilt] desc=`(空)` rules=quilt.version-constraint-unreadable
- `415.crash.txt` [quilt] desc=`(空)` rules=quilt.version-constraint-unreadable

### `93021e67d23a` — 2 份

- `335.crash.txt` [forge] desc=`Mod loading error has occurred` rules=crash.runtime-mod,mod.load-failed.fabric-entry
- `370.crash.txt` [forge] desc=`Mod loading error has occurred` rules=crash.runtime-mod,mod.load-failed.fabric-entry

### `970476202cea` — 2 份

- `533.crash.txt` [vanilla] desc=`(空)` rules=mixin.class-already-loaded
- `534.crash.txt` [vanilla] desc=`(空)` rules=mixin.class-already-loaded

### `9a9ac5dc9568` — 2 份

- **不同描述**: `(空)` / `Ticking entity`
- `598.crash.txt` [neoforge] desc=`Ticking entity` rules=crash.runtime-mod,crash.ticking-entity
- `617.crash.txt` [neoforge] desc=`(空)` rules=crash.runtime-mod

### `9fcb91f8785b` — 2 份

- `8631.crash.txt` [neoforge] desc=`Unexpected error` rules=mod.load-failed.neoforge
- `8633.crash.txt` [neoforge] desc=`Unexpected error` rules=mod.load-failed.neoforge

### `a6c2e2708044` — 2 份

- `631.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `664.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set

### `ba33bd6955a4` — 2 份

- `4809.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set
- `795.crash.txt` [fabric] desc=`(空)` rules=mod.incompatible-set

### `ba5963a7fdb1` — 2 份

- `685.crash.txt` [fabric] desc=`Initializing game` rules=mod.corrupt-jar
- `720.crash.txt` [fabric] desc=`Initializing game` rules=mod.corrupt-jar

### `ca32a2961f62` — 2 份

- `476.crash.txt` [mohist] desc=`Exception in server tick loop` rules=mod.config-invalid
- `456.crash.txt` [mohist] desc=`Exception in server tick loop` rules=mod.config-invalid

### `cfdcdaac283e` — 2 份

- `5293.crash.txt` [fabric] desc=`Unexpected error` rules=crash.runtime-mod
- `5295.crash.txt` [fabric] desc=`Unexpected error` rules=crash.runtime-mod

### `d28736a7b9c9` — 2 份

- `8508.crash.txt` [neoforge] desc=`(空)` rules=mod.coremod-missing
- `584.crash.txt` [neoforge] desc=`(空)` rules=mod.coremod-missing,mod.load-failed.neoforge

### `d28c4caf7274` — 2 份

- `988.crash.txt` [fabric] desc=`(空)` rules=crash.runtime-mod
- `769.crash.txt` [fabric] desc=`(空)` rules=crash.runtime-mod
