"""Server Doctor: what a server directory already says about its next crash.

WHAT THIS IS NOT
  Not monitoring. It reads files that exist right now -- logs/latest.log,
  crash-reports/*.txt, mods/ -- and stops. There is no daemon, no polling, no
  connection to the server, and no invented TPS number. A risk list built from
  stale files is still useful; a dashboard pretending to be live is not, and
  faking one would be the exact failure this project argues against.

WHAT IT ANSWERS
  "It crashed twice this week, what do I fix first?" -- the same rule firing in
  several reports is the cheapest strong signal on disk, and it costs one pass
  over the reports. Around it: sustained tick lag in the log, a heap ceiling
  that is small for the mod count, and a pack that already contradicts itself.

READ-ONLY
  Nothing here writes, rotates, or touches the server. tests/test_server_doctor.py
  asserts the file mtimes are unchanged after a scan, so that stays true.
"""
from __future__ import annotations

import gzip
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO

from .model import Severity
from .pack.doctor import analyse as pack_analyse

__all__ = ["Risk", "ServerReport", "inspect", "render"]

_CRASH_NAME = re.compile(r"crash-(\d{4})-(\d{2})-(\d{2})_(\d{2})\.(\d{2})\.(\d{2})-server\.txt$")
_LAG = re.compile(r"Can't keep up|Running \d+ ?ms behind|Running \d+ms behind")

#: Below this many "can't keep up" lines the log is a hiccup, not a pattern.
#: Measured on a 266-mod server's logs: a healthy boot has none, a struggling
#: one has hundreds; 20 is comfortably inside the second group.
LAG_THRESHOLD = 20

#: 20 reports is ~2 weeks of a bad week, and keeps the scan under a second.
MAX_REPORTS = 20


@dataclass
class Risk:
    level: Severity
    code: str
    subject: str
    detail: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class ServerReport:
    root: str
    log: str | None = None
    log_bytes: int = 0
    crash_reports: int = 0
    newest_crash: str | None = None
    risks: list[Risk] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)

    @property
    def worst(self) -> Severity:
        return max((r.level for r in self.risks), default=Severity.INFO)

    def by_code(self, code: str) -> list[Risk]:
        return [r for r in self.risks if r.code == code]


def _crash_date(path: Path) -> datetime | None:
    m = _CRASH_NAME.match(path.name)
    if not m:
        return None
    try:
        return datetime(*[int(x) for x in m.groups()])
    except ValueError:
        return None


def _log_text(path: Path) -> tuple[str, int]:
    """latest.log, or latest.log.gz when the launcher rotated it."""
    if path.suffix == ".gz":
        raw = gzip.decompress(path.read_bytes())
        return raw.decode("utf-8", errors="replace"), len(raw)
    raw = path.read_bytes()
    return raw.decode("utf-8", errors="replace"), len(raw)


def _newest_log(logs: Path) -> Path | None:
    for name in ("latest.log", "latest.log.gz"):
        p = logs / name
        if p.is_file():
            return p
    return None


def inspect(root: str | Path, *, max_reports: int = MAX_REPORTS) -> ServerReport:
    base = Path(root)
    if not base.is_dir():
        raise FileNotFoundError(f"not a directory: {base}")
    logs_dir = base / "logs"
    log = _newest_log(logs_dir) if logs_dir.is_dir() else None
    cr_dir = base / "crash-reports"
    reports = sorted(cr_dir.glob("*.txt")) if cr_dir.is_dir() else []
    reports = reports[-max_reports:]

    rep = ServerReport(root=str(base),
                       log=str(log) if log else None,
                       crash_reports=len(reports))

    # --- the log: sustained lag only -------------------------------------
    if log is not None:
        text, rep.log_bytes = _log_text(log)
        lags = len(_LAG.findall(text))
        if lags >= LAG_THRESHOLD:
            rep.risks.append(Risk(
                level=Severity.WARNING,
                code="server.tick-lag",
                subject=f"{lags} lag warnings",
                detail=(f"{lags} lines say the server fell behind its 50 ms tick "
                        f"budget. Sustained lag is a symptom, not a cause: "
                        f"profile before changing anything."),
                evidence=[log.name]))
    else:
        rep.not_checked.append(
            "logs/latest.log -- not found, so tick lag was not measured")

    # --- the reports: repeats, heap --------------------------------------
    from .cli import diagnose            # local: cli imports this module

    per_rule: Counter[str] = Counter()
    first_seen: dict[str, str] = {}
    heap_tight: list[str] = []
    for path in reports:
        try:
            parsed, findings, _ = diagnose(str(path))
        except Exception:                # noqa: BLE001 - one bad report is data too
            rep.not_checked.append(f"{path.name}: could not be parsed")
            continue
        for f in findings:
            per_rule[f.rule_id] += 1
            first_seen.setdefault(f.rule_id, path.name)
        xmx = parsed.system.xmx_mib
        mods = parsed.system.mod_count or len(parsed.mods)
        if xmx and xmx <= 2048 and (mods or 0) > 100:
            heap_tight.append(f"{path.name}: -Xmx{xmx}M with {mods} mods")

    dates = [d for d in (_crash_date(p) for p in reports) if d]
    if dates:
        newest = max(dates)
        rep.newest_crash = newest.strftime("%Y-%m-%d %H:%M")

    repeats = [(rid, n) for rid, n in per_rule.most_common() if n >= 2]
    for rid, n in repeats[:5]:
        rep.risks.append(Risk(
            level=Severity.ERROR,
            code="server.repeat-crash",
            subject=rid,
            detail=(f"{rid} fired in {n} of the {len(reports)} crash reports "
                    f"read. A rule that repeats is the closest thing to a "
                    f"reproduction this tool can see; fix it before the next "
                    f"one."),
            evidence=[first_seen[rid]]))

    if heap_tight:
        rep.risks.append(Risk(
            level=Severity.WARNING,
            code="server.heap-tight",
            subject=f"{len(heap_tight)} report(s)",
            detail=("The heap ceiling is small for the mod count in these "
                    "reports: this is the shape that ends in "
                    "OutOfMemoryError under load."),
            evidence=heap_tight[:3]))

    if not reports:
        rep.risks.append(Risk(
            level=Severity.INFO,
            code="server.no-crash-reports",
            subject="crash-reports/",
            detail=("No crash report on disk. Either the server has not crashed "
                    "yet, or it writes them somewhere else -- this is not "
                    "evidence that it is healthy.")))

    # --- the pack: already broken before the next boot --------------------
    mods_dir = base / "mods"
    if mods_dir.is_dir():
        try:
            pack = pack_analyse(base, side="server")
        except FileNotFoundError:
            rep.not_checked.append("mods/: no jar files, so the pack was not checked")
        else:
            bad = [f for f in pack.findings
                   if f.severity in (Severity.FATAL, Severity.ERROR)]
            if len(bad) > 5:
                rep.not_checked.append(
                    f"{len(bad) - 5} more pack finding(s) not listed")
            for f in bad[:5]:
                rep.risks.append(Risk(
                    level=f.severity, code=f.kind,
                    subject=f.subject, detail=f.detail, evidence=f.evidence))
    else:
        rep.not_checked.append("mods/ -- not found, so the pack was not checked")

    rep.not_checked.extend([
        "whether the server is up, its real TPS, or anything only a running "
        "process knows -- this scan reads files and stops",
        "rotated logs (logs/*.log.gz older than latest.log)",
    ])
    return rep


_MARK = {Severity.FATAL: "!!", Severity.ERROR: "x ", Severity.WARNING: "! ",
         Severity.HINT: "- ", Severity.INFO: "  "}


def render(rep: ServerReport, out: IO[str]) -> None:
    head = f"Server Doctor: {rep.root}"
    out.write(head + "\n" + "=" * len(head) + "\n")
    out.write("read-only snapshot -- files on disk now, not a live monitor\n")
    out.write(f"log: {rep.log or 'none'} ({rep.log_bytes:,} B)  crash reports: "
              f"{rep.crash_reports}"
              + (f"  newest: {rep.newest_crash}" if rep.newest_crash else "") + "\n\n")

    if rep.risks:
        out.write(f"risks ({len(rep.risks)}):\n")
        for r in rep.risks:
            out.write(f"{_MARK.get(r.level, '  ')} {r.subject}\n")
            out.write(f"    {r.detail}\n")
            if r.evidence:
                out.write(f"    evidence: {', '.join(r.evidence)}\n")
    else:
        out.write("no risks found in the files that were read\n")
    out.write("\nnot checked:\n")
    for line in rep.not_checked:
        out.write(f"  - {line}\n")
