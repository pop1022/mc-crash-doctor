#!/usr/bin/env python
"""Re-derive `corpus/index.jsonl` from the crash text already on disk (1D.4).

Two measured defects, both fixed here **offline** -- every record's text is
already under `corpus/github/`, so neither operation touches the network:

DEFECT 1 -- 34 duplicate rows
    The index holds 488 rows but only 454 distinct `(repo, number)` pairs.
    33 pairs are byte-identical; the remaining one differs only in `comments`
    (6 vs 7), i.e. two harvest passes. Anything that counts rows over-counts by
    7%: `corpus/MODRINTH_MAPPING.json` reports `"reports": 488`, and a sample
    drawn by iterating rows wastes slots on repeats.

DEFECT 2 -- `mod_ids` is a dead field (0/488)
    `MODID_RE` looks for the Forge-1.4-era `from mod (<id>)` marker. In this
    corpus that marker appears 480 times and is `unknown` **every single time**,
    so the filter `!= "unknown"` removes all 480 and the field is empty in every
    record. Meanwhile the reliable source -- the `-- Mod List --` section, which
    `mcd.parser.report` already parses properly for both the Forge pipe table
    and the Fabric indented tree -- is present in 123 records and yields 13,841
    ids (112.5 per populated report).

WHY RE-DERIVE INSTEAD OF DELETE
    The roadmap said "fix the rule (and re-harvest) or drop the field". Dropping
    would throw away the 13,841 ids that are already sitting on disk; re-harvesting
    would hit the GitHub API for data we already have. Re-deriving is the third
    option and the cheapest one.

    python tools/rederive_index.py --dry-run     # report only
    python tools/rederive_index.py               # dedupe, then fill mod_ids
    python tools/rederive_index.py --dedupe      # one operation at a time
    python tools/rederive_index.py --mod-ids

Both operations are idempotent: running twice changes nothing the second time.
Rows that yield no mod list keep their existing value rather than being
overwritten with an empty list -- "we could not read it" and "it has none" are
different facts, and the index should not conflate them.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcd.metadata.jars import is_loader_artifact         # noqa: E402
from mcd.parser.report import parse_file                    # noqa: E402

INDEX = os.path.join(ROOT, "corpus", "index.jsonl")
GITHUB = os.path.join(ROOT, "corpus", "github")

#: The index caps every list field at 60; keep the same ceiling so `mod_ids`
#: stays the same shape as `jars` and `mixin_configs`.
MAX_IDS = 60


def _is_platform_id(modid: str) -> bool:
    """True for Mod List rows that describe the platform, not a mod.

    Reuses `LOADER_ARTIFACTS` instead of a second platform list: it already
    holds `minecraft`, `forge`, `fabricloader`, `quiltloader` and friends, and a
    modid is just a platform artifact name without a version suffix.
    """
    return is_loader_artifact(modid)


# --------------------------------------------------------------------------
# corpus lookup
# --------------------------------------------------------------------------
def crash_paths() -> dict[tuple[str, str], str]:
    """(repo short name, issue number) -> path of the on-disk crash text."""
    out: dict[tuple[str, str], str] = {}
    for path in sorted(glob.glob(os.path.join(GITHUB, "**", "*.crash.txt"),
                                 recursive=True)):
        rel = path.replace("\\", "/").split("corpus/github/", 1)[-1]
        repo_dir, num = rel.split("/", 1)
        issue = num[: -len(".crash.txt")] if num.endswith(".crash.txt") else num
        out[(repo_dir.split("__")[-1], issue)] = path
    return out


def key_of(rec: dict) -> tuple[str, str]:
    return rec["repo"].split("/")[-1], str(rec["number"])


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------
def dedupe(records: list[dict]) -> tuple[list[dict], int]:
    """Drop duplicate `(repo, number)` rows, keeping the most-complete one.

    "Most complete" = highest `comments`, which is the only field that differed
    between harvest passes (6 vs 7 for mekanism/Mekanism#8633). Position of the
    first occurrence is preserved so the file's ordering does not shuffle.
    """
    first_at: dict[tuple[str, str], int] = {}
    best: dict[tuple[str, str], dict] = {}
    for rec in records:
        key = key_of(rec)
        if key not in first_at:
            first_at[key] = len(first_at)
            best[key] = rec
            continue
        if int(rec.get("comments") or 0) > int(best[key].get("comments") or 0):
            best[key] = rec
    kept = sorted(best.items(), key=lambda kv: first_at[kv[0]])
    return [rec for _k, rec in kept], len(records) - len(kept)


def fill_mod_ids(records: list[dict], paths: dict[tuple[str, str], str]) -> dict:
    """Populate `mod_ids` from the parsed Mod List. Never clears a non-empty field."""
    stats = {
        "filled": 0, "already": 0, "no_text": 0, "no_modlist": 0,
        "platform_only": 0, "ids_written": 0, "platform_dropped": 0,
    }
    for rec in records:
        path = paths.get(key_of(rec))
        if not path:
            stats["no_text"] += 1
            continue
        if rec.get("mod_ids"):
            stats["already"] += 1
            continue
        try:
            rep = parse_file(path)
        except Exception:                      # noqa: BLE001 - one bad file
            stats["no_text"] += 1
            continue
        ids = sorted({m.modid.strip() for m in rep.mods if m.modid.strip()})
        if not ids:
            # Leave the existing (empty) value alone rather than writing a
            # sentinel: the field's absence is itself the finding.
            stats["no_modlist"] += 1
            continue
        keep = [i for i in ids if not _is_platform_id(i)]
        stats["platform_dropped"] += len(ids) - len(keep)
        if not keep:
            # A Mod List that names only the platform tells us nothing about
            # installed mods; record that fact instead of writing an empty list
            # that looks like "we did not look".
            stats["platform_only"] += 1
            continue
        rec["mod_ids"] = keep[:MAX_IDS]
        stats["filled"] += 1
        stats["ids_written"] += len(rec["mod_ids"])
    return stats


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def load(path: str) -> tuple[list[str], list[dict]]:
    """Return (raw lines, parsed rows). Blank lines are preserved verbatim."""
    with open(path, encoding="utf-8") as fh:
        raw = fh.read().splitlines()
    return raw, [json.loads(line) for line in raw if line.strip()]


def save(path: str, records: list[dict], *, had_trailing_newline: bool) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body + ("\n" if had_trailing_newline else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default=INDEX)
    ap.add_argument("--dedupe", action="store_true", help="drop duplicate rows")
    ap.add_argument("--mod-ids", action="store_true", help="fill mod_ids from Mod List")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)

    do_all = not (args.dedupe or args.mod_ids)
    with open(args.index, encoding="utf-8") as fh:
        had_nl = fh.read().endswith("\n")
    _raw, records = load(args.index)
    before = [json.dumps(r, ensure_ascii=False) for r in records]
    print(f"index: {len(records)} rows", file=sys.stderr)

    if do_all or args.dedupe:
        records, dropped = dedupe(records)
        print(f"dedupe: -{dropped} rows -> {len(records)}", file=sys.stderr)

    if do_all or args.mod_ids:
        stats = fill_mod_ids(records, crash_paths())
        print("mod_ids: " + ", ".join(f"{k}={v}" for k, v in stats.items()),
              file=sys.stderr)

    if args.dry_run:
        print("dry run: nothing written", file=sys.stderr)
        return 0
    after = [json.dumps(r, ensure_ascii=False) for r in records]
    if after == before:
        print("no change: file left untouched", file=sys.stderr)
        return 0
    save(args.index, records, had_trailing_newline=had_nl)
    print(f"wrote {len(records)} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
