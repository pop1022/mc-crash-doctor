"""Tests for the redactor in tools/harvest_corpus.py.

The redactor is the privacy boundary between harvested issue text and what gets
committed, so its behaviour is pinned by explicit cases -- including the ones
that are easy to get wrong: mod jar filenames contain four-segment version
numbers that look exactly like IPv4 addresses.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from harvest_corpus import redact  # noqa: E402

# (input, expected substring that MUST be present, substring that MUST NOT)
KEEP_CASES = [
    # mod jar version numbers look like IPs but are attribution data
    ("Mekanism-1.21.1-10.7.13.78.jar", "Mekanism-1.21.1-10.7.13.78.jar", "<IP>"),
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
    # home directories
    (r"C:\Users\Steve\AppData\mc", "<HOME>", r"Users\Steve"),
    ("/home/julian/.minecraft/config", "<HOME>", "/home/julian"),
    # instance names in .minecraft paths
    (r"C:\Users\Bob\.minecraft\MyPack\mods", "<INSTANCE>", "MyPack"),
    # player names on the Player: line
    ("Player: Steve (12345678-1234-1234-1234-123456789012)",
     "<PLAYER>", "Steve"),
    # UUIDs anywhere
    ("uuid 6bf1dc583d744e28b18a385fd6b27f67 and "
     "12345678-1234-1234-1234-123456789012", "<UUID>",
     "12345678-1234-1234-1234-123456789012"),
]


def check() -> int:
    failures: list[str] = []

    print("═══ must NOT be redacted (attribution data) ═══")
    for src, must_have, must_not in KEEP_CASES:
        out = redact(src)
        ok = (must_have in out) and (must_not not in out)
        print(f"  {'✓' if ok else '✗'} {src[:56]}")
        if not ok:
            print(f"      got: {out}")
            failures.append(f"KEEP: {src!r} -> {out!r}")

    print("\n═══ must be redacted (PII) ═══")
    for src, must_have, must_not in REDACT_CASES:
        out = redact(src)
        ok = (must_have in out) and (must_not not in out)
        print(f"  {'✓' if ok else '✗'} {src[:56]}")
        if not ok:
            print(f"      got: {out}")
            failures.append(f"REDACT: {src!r} -> {out!r}")

    # idempotence: redacting twice must not change the result
    print("\n═══ idempotence ═══")
    sample = ("Player: Steve at C:\\Users\\Steve\\.minecraft\\pack from "
              "192.168.0.5 using Mekanism-1.21.1-10.7.13.78.jar "
              "uuid 12345678-1234-1234-1234-123456789012")
    once = redact(sample)
    twice = redact(once)
    idem = once == twice
    print(f"  {'✓' if idem else '✗'} redact(redact(x)) == redact(x)")
    if not idem:
        print(f"      once : {once}")
        print(f"      twice: {twice}")
        failures.append("not idempotent")

    print(f"\n{'✓ ALL PASS' if not failures else f'✗ {len(failures)} FAILURES'}")
    for f in failures:
        print("   ", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check())
