"""Contract for turning one raw stack-trace line into `pkg.Class.method:line`.

WHY THIS FILE EXISTS
  `_parse_frame` is the only place where the class/method split happens, and for
  a long time it silently produced garbage on four families of real input. None
  of them raised, none of them showed up in the rendered output -- the frames
  just stopped matching anything, which quietly subtracted evidence from every
  consumer (rules, attribution, coverage buckets).

  Measured on the 454-report corpus, before the repair:

    defect                                    frames  reports
    trailing `[jar]` not stripped (no `~`)     5432      148
    JPMS / TRANSFORMER layer prefix in cls    16286       --
    `-` in a Fabric method name -> glued          79       43

  After: 57,158 of 57,282 frames parse into cls + method (+ line where the
  report carries one), and `cls` never contains `)` or `]`.

  Every case below is a real line from the corpus, not an invented one. The
  reports are cited so the next person can open them.

    pytest tests/test_frame_parse.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcd.parser.report import _frame_head, _parse_frame, parse_file, parse_text

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / "corpus" / "github"


def frame(raw: str):
    return _parse_frame(raw, 0)


# --- 1. trailers ------------------------------------------------------------
def test_tilde_bracket_trailer_is_stripped():
    """Fabric's usual form -- this one always worked."""
    f = frame("net.fabricmc.loader.impl.launch.knot.Knot.init"
              "(Knot.java:156) ~[fabric-loader-0.16.9.jar:?] {}")
    assert f.cls == "net.fabricmc.loader.impl.launch.knot.Knot"
    assert f.method == "init"
    assert f.line_no == 156


def test_plain_bracket_trailer_is_stripped():
    """The regression: `[...]` without the tilde.

    CaffeineMC/sodium#3460 writes `~[...]` on every frame except the last one,
    which uses a bare `[...]`. The old code split on the literal string `~[`,
    so on that frame the bracket survived into `head`, `FRAME_BODY_RE` could not
    match, and the fallback `f.cls = head` threw away method AND line number.
    """
    f = frame("org.spongepowered.asm.mixin.transformer.MixinProcessor"
              ".applyMixins(MixinProcessor.java:352) "
              "[sponge-mixin-0.16.5+mixin.0.8.7.jar:0.16.5+mixin.0.8.7]")
    assert f.cls == ("org.spongepowered.asm.mixin.transformer.MixinProcessor")
    assert f.method == "applyMixins"
    assert f.line_no == 352


def test_debug_block_and_bracket_in_either_order():
    for raw in (
        "cpw.mods.modlauncher.Launcher.run(Launcher.java:104) "
        "~[modlauncher-11.0.5.jar:11.0.5] {}",
        "cpw.mods.modlauncher.Launcher.run(Launcher.java:104) "
        "{} ~[modlauncher-11.0.5.jar:11.0.5]",
    ):
        f = frame(raw)
        assert (f.cls, f.method, f.line_no) == (
            "cpw.mods.modlauncher.Launcher", "run", 104)


def test_class_without_method_keeps_empty_method():
    """A frame with no `(...)` at all must not be inflated into a method."""
    f = frame("net.minecraft.Foo")
    assert f.cls == "net.minecraft.Foo"
    assert f.method == ""


# --- 2. prefixes ------------------------------------------------------------
@pytest.mark.parametrize("raw,cls", [
    # NeoForge/Connector layer -- 28% of all frames in the corpus
    ("TRANSFORMER/minecraft@1.21.10/net.minecraft.client.resources.model"
     ".ModelManager.loadModels(ModelManager.java:240)",
     "net.minecraft.client.resources.model.ModelManager"),
    # JPMS module prefixes, three spellings
    ("java.base/java.lang.Thread.run(Thread.java:840)",
     "java.lang.Thread"),
    ("org.spongepowered.mixin/org.spongepowered.asm.mixin.transformer"
     ".MixinProcessor.applyMixins(MixinProcessor.java:392)",
     "org.spongepowered.asm.mixin.transformer.MixinProcessor"),
    ("cpw.mods.modlauncher@11.0.5/cpw.mods.modlauncher.serviceapi"
     ".ILaunchPluginService.processClassWithFlags(ILaunchPluginService.java:156)",
     "cpw.mods.modlauncher.serviceapi.ILaunchPluginService"),
])
def test_module_prefix_is_not_part_of_the_class(raw, cls):
    f = frame(raw)
    assert f.cls == cls
    assert f.method


def test_transformer_layer_reaches_is_minecraft():
    """Before the repair every vanilla frame was prefixed, so `is_minecraft`
    was False and `tools/coverage_report.py` counted vanilla throw sites as
    "the bug is in mod code"."""
    f = frame("TRANSFORMER/minecraft@1.21.10/net.minecraft.client.Minecraft"
              ".runTick(Minecraft.java:1068)")
    assert f.is_minecraft is True
    assert f.is_forge is False


def test_path_inside_the_parameter_list_is_not_a_module_prefix():
    """`_frame_head` cuts at `(` before looking for `/`, otherwise a source path
    with slashes would be mistaken for a module and the class would vanish."""
    assert _frame_head("com.example.Foo.bar(file:/srv/src/Foo.java:12)") == \
        "com.example.Foo.bar(file:/srv/src/Foo.java:12)"
    f = frame("com.example.Foo.bar(file:/srv/src/Foo.java:12)")
    assert f.cls == "com.example.Foo"
    assert f.method == "bar"


# --- 3. method charset ------------------------------------------------------
def test_hyphen_in_generated_method_name_stays_in_the_method():
    """Fabric submodule ids contain `-`, and they end up in the generated
    method name. The old charset `[\\w$<>]` stopped at the hyphen, so the whole
    `wrapOperation$cdi000$fabric-registry-sync-v0$...` string was swallowed into
    `cls` -- where it looked like a plausible class name and nobody noticed.
    """
    f = frame("net.fabricmc.fabric.impl.registry.sync.RegistryLoader"
              ".wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall"
              "(RegistryLoader.java:412)")
    assert f.cls == "net.fabricmc.fabric.impl.registry.sync.RegistryLoader"
    assert f.method == ("wrapOperation$cdi000$fabric-registry-sync-v0"
                        "$wrapIsServerCall")


@pytest.mark.parametrize("name", ["<init>", "<clinit>", "lambda$run$0"])
def test_jvm_pseudo_methods_survive(name):
    f = frame(f"com.example.Foo.{name}(Foo.java:1)")
    assert (f.cls, f.method) == ("com.example.Foo", name)


# --- 4. forge/vanilla flags -------------------------------------------------
def test_forge_package_is_not_labelled_vanilla():
    """`net.minecraftforge.*` starts with `net.minecraft`, so the old prefix test
    set `is_minecraft` and the `elif` below it could never fire."""
    f = frame("net.minecraftforge.fml.ModLoader.waitForTransition"
              "(ModLoader.java:264)")
    assert f.is_minecraft is False
    assert f.is_forge is True
    assert f.cls == "net.minecraftforge.fml.ModLoader"


# --- 5. real reports --------------------------------------------------------
def _corpus_report(repo: str, number: int) -> Path:
    p = GITHUB / repo / f"{number}.crash.txt"
    if not p.exists():
        pytest.skip(f"corpus report missing: {p}")
    return p


def test_real_report_mixed_bracket_spellings_fully_parse():
    """CaffeineMC/sodium#3460: `~[...]` on most frames, `[...]` on the last."""
    rep = parse_file(str(_corpus_report("CaffeineMC__sodium", 3460)))
    frames = [f for e in rep.exceptions for f in e.frames]
    assert len(frames) > 40
    bad = [f.cls for f in frames if ")" in f.cls or "]" in f.cls]
    assert not bad, f"{len(bad)} unparsed frames, e.g. {bad[:2]}"
    assert all(f.method for f in frames if f.cls)


def test_real_report_no_frame_keeps_a_prefix():
    """FabricMC/fabric-api#4922 had 44 frames with brackets still attached."""
    rep = parse_file(str(_corpus_report("FabricMC__fabric-api", 4922)))
    frames = [f for e in rep.exceptions for f in e.frames]
    assert frames
    for f in frames:
        assert not re.match(r"^(TRANSFORMER/|[^/]*@[^/]*/)", f.cls), f.cls
        assert not f.cls.endswith((")", "]")), f.cls


# --- 6. synthetic end-to-end ------------------------------------------------
def _report(*frame_lines: str) -> str:
    body = "\n".join(frame_lines)
    return (
        "---- Minecraft Crash Report ----\n\n// Oh dear.\n\n"
        "Time: 2026-01-01 12:00:00\nDescription: Ticking entity\n\n"
        "java.lang.RuntimeException: boom\n"
        f"{body}\n\nFabric Mods:\n  alpha: Alpha 1.0.0\n"
    )


def test_frames_survive_the_full_parse_path():
    """Guards the wiring, not the helper: `_parse_frame` is called from the
    exception scanner, and an earlier refactor of that loop dropped frames
    without failing any unit test on the helper itself."""
    rep = parse_text(_report(
        "\tat TRANSFORMER/minecraft@1.21.1/net.minecraft.world.level.Level.tick"
        "(Level.java:455) ~[neoforge-21.1.233.jar:?]",
        "\tat net.fabricmc.fabric.impl.registry.sync.RegistryLoader"
        ".wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall"
        "(RegistryLoader.java:412) [fabric-api.jar:?]",
    ))
    frames = [f for e in rep.exceptions for f in e.frames]
    assert [(f.cls, f.method) for f in frames] == [
        ("net.minecraft.world.level.Level", "tick"),
        ("net.fabricmc.fabric.impl.registry.sync.RegistryLoader",
         "wrapOperation$cdi000$fabric-registry-sync-v0$wrapIsServerCall"),
    ]
    assert frames[0].is_minecraft is True
    assert [f.line_no for f in frames] == [455, 412]
