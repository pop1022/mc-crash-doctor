"""Evaluate the parser against the aternosorg/codex-minecraft expectations.

Each corpus file ships with a ``.json`` describing what mclo.gs would detect
(``name`` = platform, ``version`` = Minecraft version). We map their platform
names onto our loader ids (which are finer-grained: spigot/paper/craftbukkit
are separate, hybrids like Mohist/Magma/Arclight are separate) and score.

Run::

    python tests/eval_parser.py            # human report
    python tests/eval_parser.py --strict   # exit 1 if below thresholds
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcd.parser.report import parse_file  # noqa: E402

# aternos platform name -> set of our loader ids that count as correct
EQUIV: dict[str, set[str]] = {
    "Forge": {"forge"},
    "NeoForge": {"neoforge"},
    "Fabric": {"fabric"},
    "Quilt": {"quilt"},
    "Spigot": {"spigot", "paper", "purpur", "craftbukkit", "bukkit"},
    "Paper": {"paper", "purpur", "spigot"},
    "CraftBukkit": {"craftbukkit", "spigot", "paper", "bukkit"},
    "Purpur": {"purpur", "paper"},
    "Folia": {"folia", "paper"},
    "Glowstone": {"glowstone", "bukkit"},
    "Bukkit": {"bukkit", "craftbukkit", "spigot", "paper"},
    "Mohist": {"mohist"},
    "Magma": {"magma"},
    "Arclight": {"arclight"},
    "Bedrock": {"bedrock", "bedrock-content"},
    "Pocketmine": {"pocketmine"},
    "Velocity": {"velocity"},
    "BungeeCord": {"bungeecord", "waterfall"},
    "Waterfall": {"waterfall", "bungeecord"},
    "Geyser": {"geyser"},
    "Prism Launcher": {"prism-launcher", "multimc"},
    "MultiMC": {"multimc", "prism-launcher"},
    "Minecraft Launcher": {"minecraft-launcher"},
    "CustomSkinLoader": {"custom-skin-loader"},
    "Vanilla": {"vanilla"},
}

# Platforms whose aternos "version" field is the SOFTWARE version, not the
# Minecraft version -- compare those against system.software_version.
SOFTWARE_VERSION_PLATFORMS = {
    "Bedrock", "Pocketmine", "CustomSkinLoader", "Geyser", "Velocity",
    "BungeeCord", "Waterfall", "Prism Launcher", "MultiMC",
    "Minecraft Launcher",
}

# thresholds we must not regress below
MIN_PLATFORM_ACC = 0.95
MIN_VERSION_ACC = 0.98


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--show-errors", type=int, default=25)
    args = ap.parse_args()

    corpus = ROOT / "corpus" / "aternos"
    n = ok_plat = ok_ver = ver_n = 0
    mism: list[tuple[str, str, str]] = []
    vers: list[tuple[str, str, str]] = []
    kinds: Counter[str] = Counter()

    for jf in sorted(glob.glob(str(corpus / "**" / "*.json"), recursive=True)):
        lf = jf[:-5] + ".log"
        if not os.path.exists(lf):
            continue
        exp = json.load(open(jf, encoding="utf-8"))
        r = parse_file(lf)
        n += 1
        kinds[r.kind] += 1

        want_name = (exp.get("name") or "").strip()
        accept = EQUIV.get(want_name, {want_name.lower().replace(" ", "-")})
        # A launcher-wrapped log satisfies either axis: aternos labels a
        # Prism-wrapped Fabric client "Fabric", but a bare launcher log
        # "Prism Launcher".
        got_axes = {r.system.loader, r.system.launcher}
        if got_axes & accept:
            ok_plat += 1
        elif len(mism) < 60:
            mism.append((os.path.relpath(lf, ROOT)[:70], want_name,
                         f"{r.system.loader}/{r.system.launcher or '-'}"))

        wv = str(exp.get("version") or "").strip()
        # For bedrock-side platforms the expectation is the SOFTWARE version,
        # not the Minecraft version -- compare against the right field.
        if want_name in SOFTWARE_VERSION_PLATFORMS:
            gv = r.system.software_version or r.system.loader_version
        else:
            gv = r.system.minecraft_version
        if wv:
            ver_n += 1
            if gv and (gv == wv or gv.startswith(wv) or wv.startswith(gv)):
                ok_ver += 1
            elif len(vers) < 20:
                vers.append((os.path.relpath(lf, ROOT)[:70], wv, gv or "(none)"))

    plat_acc = ok_plat / n if n else 0.0
    ver_acc = ok_ver / ver_n if ver_n else 0.0

    print(f"corpus files          : {n}")
    print(f"parsed kinds          : {dict(kinds)}")
    print(f"platform accuracy     : {ok_plat}/{n} = {plat_acc:.1%}"
          f"   (threshold {MIN_PLATFORM_ACC:.0%})")
    print(f"version accuracy      : {ok_ver}/{ver_n} = {ver_acc:.1%}"
          f"   (threshold {MIN_VERSION_ACC:.0%})")

    if mism:
        print(f"\nplatform mismatches ({len(mism)} shown):")
        for f, want, got in mism[: args.show_errors]:
            print(f"  {f:<70} want={want:<18} got={got}")
    if vers:
        print(f"\nversion mismatches ({len(vers)} shown):")
        for f, want, got in vers[: args.show_errors]:
            print(f"  {f:<70} want={want:<14} got={got}")

    if args.strict:
        if plat_acc < MIN_PLATFORM_ACC or ver_acc < MIN_VERSION_ACC:
            print("\n✗ below threshold", file=sys.stderr)
            return 1
        print("\n✓ thresholds met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
