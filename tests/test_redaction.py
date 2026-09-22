"""Tests for the redactor in tools/harvest_corpus.py.

The redactor is the privacy boundary between harvested issue text and what gets
committed, so its behaviour is pinned by explicit cases -- especially the ones
that are easy to get wrong: four-segment version numbers look exactly like IPv4
addresses and appear constantly in a crash report's Mod List, driver info, and
jar filenames. Blanking them destroys the mod attribution this project exists
to produce.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from harvest_corpus import redact  # noqa: E402

# (input, substring that MUST survive, substring that MUST NOT appear)
KEEP_CASES = [
    # Mod List version column: separators are spaces and pipes, not hyphens
    ("\t\t|jei                           |15.20.0.129         |DONE",
     "15.20.0.129", "<IP>"),
    ("prefab                        |1.10.0.1            |DONE", "1.10.0.1", "<IP>"),
    ("chickenchunks                 |2.10.0.100          |DONE", "2.10.0.100", "<IP>"),
    ("lootr                         |0.7.35.94           |DONE", "0.7.35.94", "<IP>"),
    ("carryon                       |2.1.2.7             |DONE", "2.1.2.7", "<IP>"),
    # graphics driver version
    ("Graphics card #0 versionInfo: DriverVersion=15.6.5.199",
     "15.6.5.199", "<IP>"),
    ("Graphics card #3 versionInfo: DriverVersion=10.0.19041.3636",
     "10.0.19041.3636", "<IP>"),
    # jar filenames
    ("Mekanism-1.21.1-10.7.13.78.jar", "10.7.13.78.jar", "<IP>"),
    ("minecraft-client-patched-26.1.2.75.jar", "26.1.2.75.jar", "<IP>"),
    ("Draconic-Evolution-1.18.2-3.0.31.531-universal.jar", "3.0.31.531", "<IP>"),
    ("reoccuring in Mekanism-1.21.1-10.7.13.78", "10.7.13.78", "<IP>"),
    # out-of-range octets can never be an IP
    ("build 999.999.999.999", "999.999.999.999", "<IP>"),
]

REDACT_CASES = [
    # genuine IPs in network context
    ("Connecting to 192.168.1.100:25565", "<IP>", "192.168.1.100"),
    ("server ip = 8.8.8.8", "<IP>", "8.8.8.8"),
    ("Bound to 0.0.0.0:25565", "<IP>", "0.0.0.0"),
    ("remote address 203.0.113.7 disconnected", "<IP>", "203.0.113.7"),
    ("Connection from 198.51.100.23:51000", "<IP>", "198.51.100.23"),
    ("hostname 192.0.2.1 rejected", "<IP>", "192.0.2.1"),
    # home directories
    (r"C:\Users\Steve\AppData\mc", "<HOME>", r"Users\Steve"),
    ("/home/julian/.minecraft/config", "<HOME>", "/home/julian"),
    # instance names in .minecraft paths
    (r"C:\Users\Bob\.minecraft\MyPack\mods", "<INSTANCE>", "MyPack"),
    # player names on the Player: line
    ("Player: Steve (12345678-1234-1234-1234-123456789012)", "<PLAYER>", "Steve"),
    # UUIDs anywhere
    ("uuid 12345678-1234-1234-1234-123456789012", "<UUID>",
     "12345678-1234-1234-1234-123456789012"),
]


def check() -> int:
    failures: list[str] = []

    print("═══ must NOT be redacted (version numbers / attribution) ═══")
    for src, must_have, must_not in KEEP_CASES:
        out = redact(src)
        ok = (must_have in out) and (must_not not in out)
        print(f"  {'✓' if ok else '✗'} {src.strip()[:58]}")
        if not ok:
            print(f"      got: {out.strip()}")
            failures.append(f"KEEP: {src!r} -> {out!r}")

    print("\n═══ must be redacted (PII / real addresses) ═══")
    for src, must_have, must_not in REDACT_CASES:
        out = redact(src)
        ok = (must_have in out) and (must_not not in out)
        print(f"  {'✓' if ok else '✗'} {src.strip()[:58]}")
        if not ok:
            print(f"      got: {out.strip()}")
            failures.append(f"REDACT: {src!r} -> {out!r}")

    # idempotence: redacting twice must not change the result
    print("\n═══ idempotence ═══")
    sample = ("Player: Steve at C:\\Users\\Steve\\.minecraft\\pack from "
              "ip 192.168.0.5:25565 using jei |15.20.0.129| and "
              "DriverVersion=15.6.5.199 uuid 12345678-1234-1234-1234-123456789012")
    once = redact(sample)
    twice = redact(once)
    idem = once == twice
    print(f"  {'✓' if idem else '✗'} redact(redact(x)) == redact(x)")
    if not idem:
        print(f"      once : {once}")
        print(f"      twice: {twice}")
        failures.append("not idempotent")

    # the hard mixed case: a real IP and a version number on the same line
    print("\n═══ mixed line (IP + version together) ═══")
    mixed = "Connected from ip 10.0.0.5 to server running jei 15.20.0.129"
    out = redact(mixed)
    ip_gone = "10.0.0.5" not in out
    ver_kept = "15.20.0.129" in out
    ok = ip_gone and ver_kept
    print(f"  {'✓' if ok else '✗'} {mixed}")
    print(f"      got: {out}")
    if not ok:
        failures.append(f"MIXED: {mixed!r} -> {out!r}")

    print(f"\n{'✓ ALL PASS' if not failures else f'✗ {len(failures)} FAILURES'}")
    for f in failures:
        print("   ", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check())
