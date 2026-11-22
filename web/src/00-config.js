/* mc-crash-doctor web UI.
 *
 * Loads Pyodide (CPython compiled to WASM), micropip-installs the project
 * wheel from wheel-manifest.json, then runs the SAME parse -> rules -> triage
 * pipeline as the CLI, entirely client-side. The pasted log is never sent
 * anywhere -- that is the whole point of this deployment model.
 *
 * UX contract (kept deliberately explicit, see the P0 audit):
 *  - verdict first: root cause + suspect + the first two fixes, in one screen;
 *  - every input path is validated visibly -- a link or a stray paragraph gets
 *    an explanation instead of a silent "no rule matched";
 *  - boot reports three named stages and can be retried;
 *  - the result is announced (status line) and focus moves to the verdict, so
 *    keyboard and screen-reader users know it landed;
 *  - every diagnosis and every fix can be copied out.
 *
 * i18n: the UI ships bilingual (zh default, en toggle). Every user-facing
 * string lives in I18N below -- nothing is concatenated inline, because a
 * half-translated page reads worse than an untranslated one. Diagnosis CONTENT
 * (finding titles, fixes) comes from the YAML rules and stays as the engine
 * emits it: it is data, pinned by tests/test_e2e.py and the Incident schema,
 * and translating it needs a schema-level change, not a UI one.
 */
"use strict";

const SAMPLE = `---- Minecraft Crash Report ----
// I blame Dinnerbone.

Time: 2026-09-08 18:47:46
Description: Ticking entity

java.lang.OutOfMemoryError: Java heap space
\tat net.minecraft.world.level.Level.tickEntities(Level.java:512) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]
\tat net.minecraft.client.Minecraft.tick(Minecraft.java:1755) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]
\tat mekanism.common.CommonWorldTickHandler.onTick(CommonWorldTickHandler.java:44) ~[Mekanism-1.20.1-10.4.5.19.jar%23155!/:10.4.5.19]

A detailed walkthrough of the error, its code path and all known details is as follows:
---------------------------------------------------------------------------------------

-- Head --
Thread: Render thread
Stacktrace:
\tat net.minecraft.world.level.Level.tickEntities(Level.java:512) ~[client-1.20.1-20230612.114412-srg.jar%23161!/:?]

-- Entity being ticked --
Details:
\tEntity Type: minecraft:item (net.minecraft.world.entity.item.ItemEntity)
\tEntity ID: 12345

-- System Details --
Details:
\tMinecraft Version: 1.20.1
\tJava Version: 21.0.2, Eclipse Adoptium
\tMemory: 3200 MiB / 4096 MiB
\tJVM Flags: 3 total; -Xmx4G -Xms1G
\tLoader: Forge 1.20.1-47.2.20
\tMod Count: 241
\tMods: 
\t\tMekanism|mekanism|10.4.5.19|DONE|NOSIGNATURE|Mekanism-1.20.1-10.4.5.19.jar
\t\tJust Enough Items|jei|15.2.0.27|DONE|NOSIGNATURE|jei-1.20.1-forge-15.2.0.27.jar
\t\tLithium|lithium|0.11.2|DONE|NOSIGNATURE|lithium-forge-mc1.20.1-0.11.2.jar
\t\tSodium|sodium|0.5.3|DONE|NOSIGNATURE|sodium-forge-mc1.20.1-0.5.3.jar`;

const MAX_BYTES = 8 * 1024 * 1024;
const SEV_RANK = { fatal: 4, error: 3, warning: 2, hint: 1, info: 0 };
const ISSUE_URL = "https://github.com/pop1022/mc-crash-doctor/issues/new?template=crash-not-covered.md";
const STORE_KEY = "mcd.lang";

