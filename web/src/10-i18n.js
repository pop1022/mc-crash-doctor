/* ------------------------------------------------------------------- i18n */

const I18N = {
  zh: {
    title: "mc-crash-doctor — 在浏览器里诊断 Minecraft 崩溃",
    metaDesc: "粘贴 Minecraft 崩溃报告或服务器日志，由 mc-crash-doctor 规则引擎在浏览器本地完成诊断；日志不会离开你的电脑。",
    sub: "粘贴 Minecraft 崩溃报告或服务器日志 → 直接给出根因、修复步骤，以及该找哪个模组算账。",
    privacy: "<b>纯本地运行。</b> 日志不会离开你的浏览器。",
    privacyTitle: "诊断在标签页内的 WebAssembly 里完成，不上传、无服务器、无统计。",
    fieldLabel: "崩溃报告或日志",
    placeholder: "把 crash-report.txt / latest.log 粘到这里，或者把文件拖进这个框…",
    hint: "贴完整报告效果最好：Mod List 和 System Details 能让定责准确很多。也可以把 <code>.txt</code>/<code>.log</code> 文件拖进这个框，或点「选择文件…」。上限 8 MB。",
    diagnose: "开始诊断",
    sample: "用示例试试",
    "out.empty.t": "结论区是空的，因为这里只显示真的跑出来的结果。",
    "out.empty.b": "粘一份崩溃报告，或点「用示例试试」——示例会在 0.2 秒内给出真实报告在浏览器里跑出的结论，不用等引擎下载完。",
    "sample.offline": "<b>引擎没能启动。</b> 这是同一版本离线预生成的示例结果；你自己的报告仍需要引擎。",
    pick: "选择文件…",
    clear: "清空",
    stepRuntime: "Python 运行时",
    stepEngine: "规则引擎",
    stepReady: "就绪",
    footerTail: "· 与 CLI 同一套引擎 · 规则是 YAML，欢迎 PR",

    "boot.idle": "引擎按需加载：第一次诊断会拉一次约 10 MB 的运行时",
    "boot.runtime": "正在启动 Python 运行时…",
    "boot.runtimeElapsed": (v) => `正在启动 Python 运行时… ${v.s}s（首次要下 ~10 MB，只下一次）`,
    "boot.engine": "正在安装诊断引擎…",
    "boot.ready": "引擎就绪 — 粘贴崩溃报告后点「开始诊断」",
    "boot.failed": "引擎加载失败",

    "bootErr": (v) => "<p><b>诊断引擎没能加载。</b>运行时要从 CDN 下载后装进这个标签页，被网络拦掉是最常见的原因。</p>" +
      `<details><summary>试过的地址</summary><pre>${v.msg}</pre></details>` +
      '<div class="row" style="margin-top:0">' +
      '<button id="retry">重试</button>' +
      '<button class="ghost" id="copyerr">复制错误</button></div>' +
      '<p class="hint">同一套引擎也能本地跑：<code>pip install mc-crash-doctor</code>，' +
      "然后 <code>mc-crash-doctor crash-report.txt</code>。</p>",

    "where.summary": "刚崩了，不知道文件在哪？",
    "where.lead": "先找 <code>crash-reports</code> 里最新的 <code>.txt</code>；没有的话，<code>logs/latest.log</code> 也能诊断。",
    "where.vanilla": "官方启动器：<code>%APPDATA%\\.minecraft\\crash-reports\\</code>",
    "where.vanillaAlt": "macOS：<code>~/Library/Application Support/minecraft/crash-reports/</code>；Linux：<code>~/.minecraft/crash-reports/</code>",
    "where.prism": "Prism：右键实例 →「打开文件夹」→ <code>crash-reports\\</code>",
    "where.modrinth": "Modrinth App：<code>%APPDATA%\\ModrinthApp\\profiles\\&lt;实例&gt;\\crash-reports\\</code>",
    "where.server": "服务端：服务器目录下的 <code>crash-reports\\</code>；没有就看 <code>logs\\latest.log</code>",
    "val.empty": "先粘一份崩溃报告 — 或者点「用示例试试」。",
    "val.hsErr": "<b>这是 JVM 的 hs_err 日志，不是 Minecraft 崩溃报告。</b> 它记录的是原生崩溃（多半是显卡驱动或带原生库的模组），本工具的规则读不了。下一步：先更新显卡驱动；如果刚加了光影/语音/手柄类模组，先移除它。求助时只发「Problematic frame」那一行——整份文件里有你的路径和用户名。",
    "val.exitCode": "<b>只有退出码，信息不够。</b> 退出码只说明进程死了，原因在同一次运行的日志里。下一步：贴 <code>logs/latest.log</code>（服务端）或 <code>.minecraft/logs/latest.log</code>（客户端）。目录里没有 crash-reports 通常意味着是被杀掉的或没启动成功，latest.log 里仍有原因。",
    "val.link": () => "<b>这是一条链接，不是日志。</b> 打开它、把报告内容复制过来贴在这里——" +
      "浏览器没法替你去抓别的站点的粘贴页（跨域限制）。",
    "val.prose": () => "<b>这看起来不像崩溃报告或日志。</b> 还是继续诊断，但大概率匹配不上——" +
      "正常报告里通常有堆栈帧（<code>at …</code>）或「Minecraft Crash Report」抬头。",

    "st.blocked": "没有诊断 — 看上面的提示",
    "st.diagnosing": "正在诊断…",
    "st.findings": (v) => `找到 ${v.n} 条问题 — 结论在下方`,
    "st.none": "完成 — 这份报告没有命中任何规则",
    "st.instant": "示例结果 · 由同一版本离线预生成，与引擎跑出来的一致（引擎正在后台启动）",
    "st.notReport": "这不是崩溃报告 — 没看到可诊断的内容",
    "weak.title": "这看起来不是一份崩溃报告",
    "weak.body": "文本里没有崩溃报告或服务端日志的特征。描述问题帮不上忙——引擎只读文件，直接粘报告或日志。",
    "weak.li1": "崩溃报告：.minecraft/crash-reports/ 或服务端 crash-reports/ 里的 .txt",
    "weak.li2": "服务端日志：logs/latest.log，崩溃那一次的前后几十行就够",
    "weak.li3": "启动器日志：启动器的「日志」页，或 launcher_log.txt",
    "st.failed": (v) => `诊断失败：${v.msg}`,

    "diagErr": (v) => "<p><b>引擎在诊断过程中抛了异常。</b>文本已经解析，但某条规则崩了" +
      `——请带上这份日志提个 issue。</p><pre>${v.msg}</pre>`,

    "verdict.rootCause": "根因",
    "verdict.suspect": "最可能的原因",
    "verdict.confidence": "证据强度",
    "verdict.startHere": "先做这两步",
    "verdict.noRule": "没有规则命中这份报告。解析是干净的，只是这个故障模式还没覆盖——带上报告开个 issue，它就会变成下一条规则 + 测试。",
    "verdict.parsed": "崩溃报告已解析",
    "verdict.failedBadge": "未命中",

    "act.copyFix": "复制修复步骤",
    "act.copyMd": "复制诊断",
    "act.issue": "去开 issue",
    "act.feedback": "结论不对？",
    "act.feedbackFail": "没能生成反馈链接，请直接去仓库开 issue",
    "fb.title": "把这个发到 GitHub？",
    "fb.lead": "下面是要发出去的全部内容。日志正文不在里面；需要贴报告时请自己脱敏。",
    "fb.open": "打开 issue",
    "fb.cancel": "取消",

    "ov.findings": (v) => `${v.n} 条问题`,
    "findings.title": "全部发现",
    "findings.blame": "归责：",
    "findings.fixes": "修复步骤",
    "findings.copyFixes": "复制这些步骤",
    "findings.evidence": "证据",

    "env.summary": "环境信息",
    "raw.summary": "原始 JSON",

    "copy.ok": "已复制到剪贴板",
    "copy.fail": "复制失败",
    "copy.btnOk": "已复制",
    "copy.btnFail": "复制失败",

    "file.tooBig": (v) => `这份内容有 <b>${v.size}</b> — 上限 8 MB。请贴崩溃报告本身，而不是整个日志压缩包。`,
    "file.notLog": "这个文件看起来不像崩溃报告或日志。还是继续诊断，但请确认选对了文件。",
    "file.loaded": (v) => `已载入 <b>${v.name}</b>（${v.size}）。点「开始诊断」。`,
    "file.readFail": (v) => `读不了这个文件。${v.msg}`,

    "md.title": "## Minecraft 崩溃诊断",
    "md.env": "**环境**",
    "md.rootCause": "**根因**",
    "md.suspect": "**嫌疑模组**",
    "md.fixes": "**修复步骤**",
    "md.footer": "_由 mc-crash-doctor 在本地诊断 — 日志从未被上传。_",

    "env.root": "根因",
    "env.loader": "加载器",
    "env.minecraft": "游戏版本",
    "env.java": "Java",
    "env.mods": "模组数",
    "env.heap": "堆内存",
    "env.side": "运行侧",
    "env.server": "服务端",
    "env.client": "客户端",
    "env.modsCount": (v) => `${v.n} 个模组`,
    "env.heapLine": (v) => `堆 ${v.used}/${v.max} MiB`,
    "env.mcVersion": (v) => `MC ${v.v}`,
    "env.javaMajor": (v) => `Java ${v.v}`,

    skip: "跳到正文",
    "nav.label": "页面章节",
    "nav.verdict": "结论",
    "nav.evidence": "证据",
    "nav.coverage": "覆盖",
    "nav.rules": "规则",
    "nav.faq": "常见问题",

    "hero.h1": "服务器崩了。<br>找出那个模组。",
    "hero.lead": "粘一份崩溃报告。规则引擎在浏览器里跑完，给出根因、可疑模组和证据强度。日志不出这台机器。",
    "hero.fact1.b": "本地 WASM",
    "hero.fact1.s": "无上传，无服务器",
    "hero.fact2.b": "16 条规则",
    "hero.fact2.s": "YAML 写，PR 就能加",
    "hero.fact3.b": "同一套引擎",
    "hero.fact3.s": "CLI 与网页共用",
    "hero.limit": "≤ 8 MB · .txt / .log",

    "verdict.h2": "结论先给，证据在后。",
    "verdict.lead": "点「用示例试试」：一台 266 模组服务器的真实报告会在 0.2 秒内出结论——根因、可疑模组、证据强度，全部由同一套引擎算出。",
    "verdict.source": "看规则源码",
    "verdict.strengthNote": "证据强度是各条线索的加权分数，不是校准过的「猜对概率」；它只说明这条线索有多硬。",
    "tie.title": "两个模组分数接近",
    "tie.body": "「{a}」{pa}% 与「{b}」{pb}% 相差不到 20 个百分点，证据还不足以二选一。要二分的话，一次只禁用其中一个、每次重启复现——一次删一批就不知道是谁了。",
    "noSuspect.note": "这条规则能说出问题类型，但没有定位到具体模组。先按上面的步骤做，不要为此删模组。",
    "verdict.anchor": "依据",
    "verify.title": "怎么算修好了：",
    "verify.body": "照原样再跑一次（同一存档、同一条命令）。日志里不再出现 {line} 就算修好；如果还是同一条，说明这一步没解决，换下一条。",
    "verify.undoTitle": "怎么撤回：",
    "verify.undo": "只改了一处的话，改回去即可——换回原版本、恢复原来的 -Xmx、把模组装回去。工具没有改动任何文件。",
    "verify.anchorFallback": "这条规则报的那一行",


    "ev.h2": "崩在哪一行，就指向哪个模组。",
    "ev.lead": "同一份报告把模组的出处写在三个地方。三处对上，才敢报 97%。",
    "ev.s1.t": "Mixin 归属",
    "ev.s1.b": "一个 mixin 崩了，几乎总是它主人的锅。这是最硬的信号。",
    "ev.s2.t": "模组自己的堆栈帧",
    "ev.s2.b": "根因调用栈里第一个非原版、非加载器的类，拿去报告自己的 Mod List 里对。",
    "ev.s3.t": "jar 名",
    "ev.s3.b": "帧尾的 jar 与版本直接给出构件，不用猜缩写。",
    "ev.ledger": "解析结果",
    "ev.root": "根因",

    "cov.h2": "四类死法，正好是没人管的那些。",
    "cov.lead": "它们不给你一条干净的异常，只留一份长得像正常关服的日志。",
    "cov.1.t": "堆耗尽",
    "cov.1.b": "“平时好好的，一 stop 就崩”——不是内存泄漏，是存档时把整片区域一次性编码进内存。",
    "cov.2.t": "tick 卡了 120 秒",
    "cov.2.b": "watchdog 杀掉 JVM，报告只留下它当时卡在哪，不告诉你谁把它卡住的。",
    "cov.3.t": "mixin 没打上",
    "cov.3.b": "两个模组改同一个类，先崩的是后来的那个——但先崩不等于先错。",
    "cov.4.t": "Metaspace 撑爆",
    "cov.4.b": "加 -Xmx 一点用都没有；撑爆的是类元数据，不是堆。",

    "rules.h2": "规则是数据，不是黑盒。",
    "rules.lead": "一条规则就是一段 YAML：什么时候触发、为什么、怎么修。加一条不用改 Python。",
    "rules.f1.t": "优先级执行",
    "rules.f1.s": "数字小的先判",
    "rules.f2.t": "证据权重写在规则里",
    "rules.f2.s": "不是运行时拍的",
    "rules.f3.t": "加规则只要两样",
    "rules.f3.s": "一个 YAML 加一份真实报告",
    "rules.link": "看 memory-performance.yaml",

    "faq.h2": "常见问题",
    "faq.q1": "日志会被上传吗？",
    "faq.a1": "不会。引擎是编译成 WebAssembly 的 CPython，规则在标签页内跑完：没有服务器，没有统计，也没有请求带着你的日志出去。",
    "faq.q2": "支持哪些加载器？",
    "faq.a2": "Forge、NeoForge、Fabric、Quilt。服务端和客户端的报告都能读，包括只写着“Ticking entity”的那种。",
    "faq.q3": "和 mclo.gs 有什么不同？",
    "faq.a3": "它擅长加载期的报错（缺依赖、模组重复、版本不对）。这里补的是内存与性能：堆 OOM、watchdog、mixin 冲突、Metaspace，并且按三处证据给模组打分。",
    "faq.q4": "能离线用吗？",
    "faq.a4": "页面首次要拉一次 Pyodide（约 10 MB），之后诊断不出网。完全离线就用 CLI：<code>pip install mc-crash-doctor</code>。",

    "foot.tag": "Minecraft 崩溃报告诊断：根因、嫌疑模组、修复步骤。MIT 许可。",
    "foot.col1": "项目",
    "foot.rules": "规则目录",
    "foot.issue": "报告没覆盖的崩溃",
    "foot.col2": "本地运行",
    "foot.cli": "CLI 安装",
    "foot.docs": "中文说明",
    "foot.legal": "开源许可，无服务器，与命令行同一套引擎",
    "foot.credit": "游戏截图：<a href=\"https://wallhaven.cc/w/qzjro7\" target=\"_blank\" rel=\"noopener\">HeianDeSuipian</a>、<a href=\"https://wallhaven.cc/w/7pe3xy\" target=\"_blank\" rel=\"noopener\">212112111zwl</a>，来自 Wallhaven",
    "photo.forest.alt": "游戏截图：日出穿过云杉林海，雾气从山谷里升起来。",
    "photo.bridge.line": "每一份日志，<br>都来自一个这样消失的世界。",
    "world.line": "村子还在原地。",
    "world.note": "崩掉的是进程，不是这个世界。存档还躺在硬盘里，日志只是它掉下来时留下的碎片。",
    "photo.villageA.alt": "游戏截图：山坡上的村庄，晨雾漫过屋顶和麦田。",
    "photo.villageB.alt": "游戏截图：秋色村庄与城堡，红色树冠围着木屋。",
    "close.line": "世界还在跑。<br>日志只是它留在磁盘上的痕迹。",
    "close.action": "粘一份报告",

    "sev.fatal": "致命",
    "sev.error": "错误",
    "sev.warning": "警告",
    "sev.hint": "提示",
    "sev.info": "信息",
  },

  en: {
    title: "mc-crash-doctor — diagnose Minecraft crashes in your browser",
    metaDesc: "Paste a Minecraft crash report or server log. Diagnosed entirely in your browser by the mc-crash-doctor rule engine — the log never leaves your machine.",
    sub: "Paste a Minecraft crash report or server log → root cause, fix steps, and the mod to blame.",
    privacy: "<b>Local only.</b> The log never leaves your browser.",
    privacyTitle: "Diagnosis runs in WebAssembly inside this tab. Nothing is uploaded, there is no server and no analytics.",
    fieldLabel: "Crash report or log",
    placeholder: "Paste crash-report.txt / latest.log here, or drop the file into this box…",
    hint: "The full report works best — the Mod List and System Details make attribution much stronger. Drop a <code>.txt</code>/<code>.log</code> file anywhere in this box, or use “Choose a file…”.",
    diagnose: "Diagnose",
    sample: "Try a sample",
    "out.empty.t": "This area is empty because it only shows results that were actually computed.",
    "out.empty.b": "Paste a crash report, or press “Try a sample” — the sample answers in about 0.2 s with what the same report produces in the browser, without waiting for the engine to download.",
    "sample.offline": "<b>The engine did not start.</b> This is the sample result precomputed by the same version; your own report still needs the engine.",
    pick: "Choose a file…",
    clear: "Clear",
    stepRuntime: "Python runtime",
    stepEngine: "Rule engine",
    stepReady: "Ready",
    footerTail: "· same engine as the CLI · rules are YAML, PRs welcome",

    "boot.idle": "the engine loads on first use: about 10 MB, once",
    "boot.runtime": "starting the Python runtime…",
    "boot.runtimeElapsed": (v) => `starting the Python runtime… ${v.s}s (first load pulls ~10 MB, once)`,
    "boot.engine": "installing the diagnosis engine…",
    "boot.ready": "engine ready — paste a crash report and hit Diagnose",
    "boot.failed": "engine failed to load",

    "bootErr": (v) => "<p><b>The diagnosis engine could not load.</b> It is fetched from " +
      "a CDN and installed in this tab; a blocked network is the usual reason.</p>" +
      `<details><summary>Every address tried</summary><pre>${v.msg}</pre></details>` +
      '<div class="row" style="margin-top:0">' +
      '<button id="retry">Retry</button>' +
      '<button class="ghost" id="copyerr">Copy error</button></div>' +
      '<p class="hint">Still stuck? The same engine runs locally: ' +
      "<code>pip install mc-crash-doctor</code> then " +
      "<code>mc-crash-doctor crash-report.txt</code>.</p>",

    "where.summary": "Just crashed — where is the file?",
    "where.lead": "Take the newest <code>.txt</code> in <code>crash-reports</code>; if there is none, <code>logs/latest.log</code> works too.",
    "where.vanilla": "Default launcher: <code>%APPDATA%\\.minecraft\\crash-reports\\</code>",
    "where.vanillaAlt": "macOS: <code>~/Library/Application Support/minecraft/crash-reports/</code> · Linux: <code>~/.minecraft/crash-reports/</code>",
    "where.prism": "Prism: right-click the instance → Open folder → <code>crash-reports\\</code>",
    "where.modrinth": "Modrinth App: <code>%APPDATA%\\ModrinthApp\\profiles\\&lt;profile&gt;\\crash-reports\\</code>",
    "where.server": "Server: <code>crash-reports\\</code> in the server directory; if empty, <code>logs\\latest.log</code>",
    "val.empty": "Paste a crash report first — or press “Try a sample”.",
    "val.hsErr": "<b>This is a JVM hs_err log, not a Minecraft crash report.</b> It records a native crash — usually the graphics driver, or a mod that ships native code — and the rules here cannot read it. Next: update the GPU driver; if it started after adding a shaders/voice/controller mod, remove that mod first. When asking for help, share the “Problematic frame” line only: the whole file contains your paths and user name.",
    "val.exitCode": "<b>An exit code alone is not enough.</b> It says the process died; the cause is in the log from the same run. Next: paste <code>logs/latest.log</code> (server) or <code>.minecraft/logs/latest.log</code> (client). No crash-reports folder usually means the game was killed or never started — latest.log still has the reason.",
    "val.link": () => "<b>That is a link, not the log.</b> Open it, copy the report and " +
      "paste it here — the browser cannot fetch another site's paste for you (cross-origin).",
    "val.prose": () => "<b>This does not look like a crash report or a log.</b> " +
      "Diagnosing anyway, but expect no useful match — a report usually contains stack " +
      "frames (<code>at …</code>) or a “Minecraft Crash Report” banner.",

    "st.blocked": "nothing diagnosed — see the note above",
    "st.diagnosing": "diagnosing…",
    "st.findings": (v) => `${v.n} finding${v.n > 1 ? "s" : ""} — the verdict is below`,
    "st.none": "done — no rule matched this report",
    "st.instant": "sample result · precomputed by the same version, identical to what the engine produces (it is starting in the background)",
    "st.notReport": "not a crash report — nothing diagnosable in the text",
    "weak.title": "This does not look like a crash report",
    "weak.body": "Nothing in the text looks like a crash report or a server log. Describing the problem does not help — the engine only reads files, so paste the report or the log.",
    "weak.li1": "Crash report: a .txt in .minecraft/crash-reports/ or the server's crash-reports/",
    "weak.li2": "Server log: logs/latest.log — a few dozen lines around the crash are enough",
    "weak.li3": "Launcher log: the launcher's Logs page, or launcher_log.txt",
    "st.failed": (v) => `diagnosis failed: ${v.msg}`,

    "diagErr": (v) => "<p><b>The engine threw while diagnosing.</b> The text was parsed, " +
      `but a rule crashed — please report this with the log attached.</p><pre>${v.msg}</pre>`,

    "verdict.rootCause": "root cause",
    "verdict.suspect": "most likely cause",
    "verdict.confidence": "evidence",
    "verdict.startHere": "start here",
    "verdict.noRule": "No rule matched this report. It parsed cleanly, but this failure mode is not covered yet — opening an issue with the report turns it into the next rule + test.",
    "verdict.parsed": "Crash report parsed",
    "verdict.failedBadge": "no match",

    "act.copyFix": "Copy fix",
    "act.copyMd": "Copy diagnosis",
    "act.issue": "Open an issue",
    "act.feedback": "Wrong result?",
    "act.feedbackFail": "Could not build the feedback link. Open an issue on the repo instead.",
    "fb.title": "Send this to GitHub?",
    "fb.lead": "Everything that leaves the page is below. The log body is not in it; redact anything you paste yourself.",
    "fb.open": "Open issue",
    "fb.cancel": "Cancel",

    "ov.findings": (v) => `${v.n} finding${v.n > 1 ? "s" : ""}`,
    "findings.title": "All findings",
    "findings.blame": "blame:",
    "findings.fixes": "fixes",
    "findings.copyFixes": "Copy these fixes",
    "findings.evidence": "evidence",

    "env.summary": "Environment",
    "raw.summary": "raw JSON",

    "copy.ok": "Copied to clipboard",
    "copy.fail": "Could not copy",
    "copy.btnOk": "Copied",
    "copy.btnFail": "Copy failed",

    "file.tooBig": (v) => `This is <b>${v.size}</b> — the box accepts up to 8 MB. Paste the crash report itself instead of the whole log archive.`,
    "file.notLog": "That file does not look like a crash report or log. Diagnosing anyway, but check you picked the right file.",
    "file.loaded": (v) => `Loaded <b>${v.name}</b> (${v.size}). Press Diagnose.`,
    "file.readFail": (v) => `Could not read that file. ${v.msg}`,

    "md.title": "## Minecraft crash diagnosis",
    "md.env": "**Environment**",
    "md.rootCause": "**Root cause**",
    "md.suspect": "**Suspect**",
    "md.fixes": "**Fixes**",
    "md.footer": "_Diagnosed locally by mc-crash-doctor — the log was never uploaded._",

    "env.root": "root cause",
    "env.loader": "loader",
    "env.minecraft": "minecraft",
    "env.java": "java",
    "env.mods": "mods",
    "env.heap": "heap",
    "env.side": "side",
    "env.server": "server",
    "env.client": "client",
    "env.modsCount": (v) => `${v.n} mods`,
    "env.heapLine": (v) => `heap ${v.used}/${v.max} MiB`,
    "env.mcVersion": (v) => `MC ${v.v}`,
    "env.javaMajor": (v) => `Java ${v.v}`,

    skip: "Skip to content",
    "nav.label": "Sections",
    "nav.verdict": "Verdict",
    "nav.evidence": "Evidence",
    "nav.coverage": "Coverage",
    "nav.rules": "Rules",
    "nav.faq": "FAQ",

    "hero.h1": "The server died.<br>Name the mod.",
    "hero.lead": "Paste a crash report. The rule engine runs in your browser and returns the root cause, the suspect mod and how strong the evidence is. The log never leaves the machine.",
    "hero.fact1.b": "Local WASM",
    "hero.fact1.s": "No upload, no server",
    "hero.fact2.b": "16 rules",
    "hero.fact2.s": "YAML, a PR adds one",
    "hero.fact3.b": "One engine",
    "hero.fact3.s": "Shared with the CLI",
    "hero.limit": "≤ 8 MB · .txt / .log",

    "verdict.h2": "The verdict first, the proof after.",
    "verdict.lead": "Press “Try a sample”: a real 266-mod server report produces its verdict in about 0.2 s — root cause, suspect mod, evidence strength, all from the same engine.",
    "verdict.source": "Read the rules",
    "verdict.strengthNote": "Evidence strength is a weighted score over the signals, not a calibrated chance of being right.",
    "tie.title": "Two mods score close together",
    "tie.body": "{a} ({pa}%) and {b} ({pb}%) are within 20 points, so the evidence does not pick one. To bisect, disable one at a time and restart between tries -- removing a batch tells you nothing about which one it was.",
    "noSuspect.note": "This rule names the failure, but not the mod. Do the steps above; do not delete mods for it.",
    "verdict.anchor": "Evidence",
    "verify.title": "How to check:",
    "verify.body": "Run the same scenario again (same world, same command). If {line} no longer appears in the log, it is fixed; if it does, this step did not solve it -- try the next one.",
    "verify.undoTitle": "How to undo:",
    "verify.undo": "If you changed one thing, put it back: the old version, the previous -Xmx, the mod you removed. This tool never edits your files.",
    "verify.anchorFallback": "the line this rule reports",

    "ev.h2": "The line it died on names the mod.",
    "ev.lead": "One report states mod provenance in three places. All three agree before 97% is printed.",
    "ev.s1.t": "Mixin ownership",
    "ev.s1.b": "A mixin crash is almost always its owner's fault. The strongest signal there is.",
    "ev.s2.t": "Mod-owned frames",
    "ev.s2.b": "The first non-vanilla, non-loader class in the root-cause trace, resolved against the report's own mod list.",
    "ev.s3.t": "Jar names",
    "ev.s3.b": "The jar and version at the end of the frame name the artifact, no acronym guessing.",
    "ev.ledger": "Parsed",
    "ev.root": "Root cause",
    "cov.h2": "Four ways servers die, and nobody covers them.",
    "cov.lead": "They hand you no clean exception, only a log that looks like a normal shutdown.",
    "cov.1.t": "Heap exhausted",
    "cov.1.b": "“Runs fine, dies on stop” is not a leak: the whole loaded region is encoded into memory at once.",
    "cov.2.t": "A 120-second tick",
    "cov.2.b": "The watchdog kills the JVM and the report keeps only where it was stuck, never who stuck it.",
    "cov.3.t": "Mixin not applied",
    "cov.3.b": "Two mods patch one class and the later one crashes first, which is not the same as being wrong first.",
    "cov.4.t": "Metaspace blown",
    "cov.4.b": "Raising -Xmx does nothing here; class metadata is what ran out.",
    "rules.h2": "Rules are data, not a black box.",
    "rules.lead": "A rule is a block of YAML: when it fires, why, and how to fix it. Adding one needs no Python.",
    "rules.f1.t": "Priority order",
    "rules.f1.s": "the low number judges first",
    "rules.f2.t": "Evidence weights live in the rule",
    "rules.f2.s": "not guessed at runtime",
    "rules.f3.t": "Adding a rule needs two things",
    "rules.f3.s": "one YAML and one real report",
    "rules.link": "Read memory-performance.yaml",
    "faq.h2": "Questions",
    "faq.q1": "Is my log uploaded?",
    "faq.a1": "No. The engine is CPython compiled to WebAssembly and the rules run inside the tab: no server, no analytics, no request carrying your log.",
    "faq.q2": "Which loaders are supported?",
    "faq.a2": "Forge, NeoForge, Fabric and Quilt, on both server and client reports, including the ones that only say “Ticking entity”.",
    "faq.q3": "How is this different from mclo.gs?",
    "faq.a3": "That engine is strong on load-time errors: missing dependencies, duplicate mods, wrong versions. This one covers memory and performance (heap OOM, watchdog, mixin conflicts, Metaspace) and scores the mod on three signals.",
    "faq.q4": "Does it work offline?",
    "faq.a4": "The first visit pulls Pyodide once (about 10 MB); diagnosis itself never goes to the network. For a fully offline run use the CLI: <code>pip install mc-crash-doctor</code>.",
    "foot.tag": "Minecraft crash diagnosis: root cause, suspect mod, fix steps. MIT licensed.",
    "foot.col1": "Project",
    "foot.rules": "Rule files",
    "foot.issue": "Report an uncovered crash",
    "foot.col2": "Run locally",
    "foot.cli": "Install the CLI",
    "foot.docs": "Chinese README",
    "foot.legal": "Open source, no server, same engine as the CLI",
    "foot.credit": "Game screenshots: <a href=\"https://wallhaven.cc/w/qzjro7\" target=\"_blank\" rel=\"noopener\">HeianDeSuipian</a>, <a href=\"https://wallhaven.cc/w/7pe3xy\" target=\"_blank\" rel=\"noopener\">212112111zwl</a>, via Wallhaven",
    "photo.forest.alt": "In-game screenshot: sunrise through a spruce forest, mist rising from the valley.",
    "photo.bridge.line": "Every log comes from<br>a world that ended like this.",
    "world.line": "The village is still there.",
    "world.note": "What crashed was the process, not the world. The save is still on disk; the log is only what fell off when it went down.",
    "photo.villageA.alt": "In-game screenshot: a village on a hillside, morning mist over roofs and fields.",
    "photo.villageB.alt": "In-game screenshot: an autumn village and castle ringed by red trees.",
    "close.line": "The world is still running.<br>The log is only what it left on disk.",
    "close.action": "Paste a report",

    "sev.fatal": "FATAL",
    "sev.error": "ERROR",
    "sev.warning": "WARNING",
    "sev.hint": "HINT",
    "sev.info": "INFO",
  },
};

let LANG = "zh";

function t(key, vars) {
  const pack = I18N[LANG] || I18N.zh;
  let v = pack[key];
  if (v === undefined) v = I18N.zh[key];      // a missing translation must
  if (v === undefined) return key;            // never blank the UI
  if (typeof v === "function") return v(vars || {});
  if (!vars) return v;
  return String(v).replace(/\{(\w+)\}/g, (m, k) =>
    (vars[k] === undefined ? m : String(vars[k])));
}

let pyodide = null;
let ready = false;
let booting = null;
let busy = false;
let LAST = null;            // the Incident document currently rendered
let LAST_ORIGIN = "";       // "engine" | "sample": the precomputed sample
                            // cannot be re-run before Pyodide is up, so a
                            // language switch has to fetch its other file
let LAST_TEXT = "";         // the input that produced LAST, so a language
                            // switch can re-run the engine instead of only
                            // re-labelling the chrome
let NOTICE = null;          // { key, vars, tone } so it survives a language switch
let BOOT_ERROR = "";        // last boot exception, for the "copy error" button
let STATUS = { key: "boot.runtime", vars: {}, kind: "" };

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- helpers */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setStatus(key, kind, vars) {
  STATUS = { key: key || "", vars: vars || {}, kind: kind || "" };
  paintStatus();
}

function paintStatus() {
  const el = $("status");
  el.textContent = STATUS.key ? t(STATUS.key, STATUS.vars) : "";
  // Keep the base class: assigning only the kind dropped "status" after the
  // first paint, so the line reverted to body size/colour and .status.ok /
  // .status.err could never match (they need both classes).
  el.className = "status" + (STATUS.kind ? " " + STATUS.kind : "");
}

function setBusy(b) {
  busy = b;
  if ($("go")) $("go").disabled = b;
  if ($("sample")) $("sample").disabled = b;
  if ($("pick")) $("pick").disabled = b;
  if ($("clear")) $("clear").disabled = b;
}

function showNotice(key, vars, tone) {
  NOTICE = { key, vars: vars || {}, tone: tone || "" };
  paintNotice();
}

function hideNotice() {
  NOTICE = null;
  paintNotice();
}

function paintNotice() {
  const el = $("notice");
  if (!NOTICE) { el.hidden = true; el.innerHTML = ""; return; }
  // NOTICE stores the KEY, never the rendered string: a language switch has to
  // be able to repaint a visible warning in the new language.
  el.innerHTML = t(NOTICE.key, NOTICE.vars);
  el.className = "notice" + (NOTICE.tone === "ok" ? " ok" : "");
  el.hidden = false;
  // Re-attached on every paint: a language switch replaces this subtree.
  const retry = $("retry");
  if (retry) retry.addEventListener("click", () => { hideNotice(); boot(); });
  const cerr = $("copyerr");
  if (cerr) cerr.addEventListener("click", (ev) => copyText(BOOT_ERROR, ev.currentTarget));
}

function syncClear() {
  $("clear").hidden = !$("log").value.length;
}

function fmtSize(bytes) {
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  return Math.max(1, Math.round(bytes / 1024)) + " KB";
}

function sevLabel(sev) {
  const k = String(sev || "").toLowerCase();
  return t("sev." + k);
}

/* --------------------------------------------------------------- i18n glue */

function setLang(lang, opts) {
  LANG = I18N[lang] ? lang : "zh";
  try { localStorage.setItem(STORE_KEY, LANG); } catch (e) { /* private mode */ }

  const html = document.documentElement;
  html.lang = LANG === "zh" ? "zh-CN" : "en";
  document.title = t("title");
  const meta = $("meta-desc");
  if (meta) meta.setAttribute("content", t("metaDesc"));

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
    el.setAttribute("alt", t(el.dataset.i18nAlt));
  });
  const privacy = $("privacy");
  if (privacy) privacy.title = t("privacyTitle");

  document.querySelectorAll(".lang button").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.lang === LANG ? "true" : "false");
  });

  paintStatus();
  paintNotice();
  // Re-render the existing result so its chrome (labels, buttons, environment
  // keys) switches too. Focus is deliberately NOT moved: the user is on the
  // toggle, and stealing focus from it would be hostile.
  // Re-run the engine rather than re-labelling: the finding copy lives in the
  // document, so a switch that only touched the chrome would leave English
  // findings under a Chinese UI.
  if (LAST && ready && LAST_TEXT) {
    try {
      const json = pyodide.globals.get("mcd_diagnose")(LAST_TEXT, LANG);
      render(JSON.parse(json), { focus: false });
    } catch (e) {
      render(LAST, { focus: false });
    }
  } else if (LAST && LAST_ORIGIN === "sample" && !ready) {
    // The precomputed sample does not go through the engine, so switching
    // language means fetching the other language's file.
    showPrecomputedSample().then((ok) => {
      if (!ok) render(LAST, { focus: false });
    });
  } else if (LAST) {
    render(LAST, { focus: false });
  }
  if (opts && opts.announce) {
    $("copystatus").textContent = LANG === "zh" ? "界面语言：中文" : "Interface language: English";
  }
  setupProgressLabel();
}

function setupProgressLabel() {
  const p = $("progress");
  if (p) p.setAttribute("aria-label", LANG === "zh" ? "引擎加载进度" : "Engine loading progress");
  const out = $("out");
  if (out) out.setAttribute("aria-label", LANG === "zh" ? "诊断结果" : "Diagnosis result");
}

function preferredLang() {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved && I18N[saved]) return saved;
  } catch (e) { /* ignore */ }
  // Default to Chinese: this deployment targets the zh-speaking Minecraft
  // server community. The toggle is right there for everyone else.
  return "zh";
}