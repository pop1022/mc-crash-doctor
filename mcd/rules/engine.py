"""Declarative rule engine.

Rules live in YAML so the community can add coverage via PR without touching
Python. Each rule declares *what to match* (conditions over the parsed report)
and *what to say* (title, explanation, fixes). The engine evaluates rules in
priority order and returns Findings.

Condition DSL (all keys AND together; a key matches if ANY entry matches):

    description:    [regex, ...]        report.description
    exception:      [regex, ...]        any exception kind in the chain
    exception_msg:  [regex, ...]        exception message
    caused_by:      [regex, ...]        any Caused-by exception+message
    frame:          [regex, ...]        any stack frame (class+method+jar text)
    frame_top:      [regex, ...]        top N frames of the root cause
    jar:            [regex, ...]        any frame's jar
    mixin:          [regex, ...]        any frame's mixin config
    text:           [regex, ...]        the full report text
    loader:         [exact, ...]        forge/neoforge/fabric/...
    java_major:     {lt: N, ge: N, ...} java version compare
    max_heap_mib:   {lt: N, ge: N, ...} max heap compare
    mod_count:      {lt: N, ge: N, ...} mod count compare
    has_mod:        [modid, ...]        mod present in the mod list
    kind:           [exact, ...]        crash-report/log

Fields with ``$name`` capture groups feed into the message templates, e.g.
``tick_seconds: {capture: "tick took ([\\d.]+) seconds"}``.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

from ..model import CrashReport, Finding, Severity

BUILTIN_DIR = Path(__file__).parent / "builtin"

_COMPARATORS = {
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
}


@dataclass
class Rule:
    id: str
    title: str
    severity: Severity = Severity.ERROR
    priority: int = 100          # lower runs first
    when: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    fixes: list[str] = field(default_factory=list)
    suspects_from: list[str] = field(default_factory=list)
    # suspects_from entries: 'mixin' | 'jar' | 'frame_mods' | 'mod:<id>'
    confidence: float = 0.7
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    source: str = ""             # yaml file it came from
    once: bool = True            # emit at most one finding

    @classmethod
    def from_dict(cls, d: dict[str, Any], source: str = "") -> "Rule":
        sev = d.get("severity", "error")
        return cls(
            id=d["id"],
            title=d["title"],
            severity=Severity[str(sev).upper()],
            priority=int(d.get("priority", 100)),
            when=d.get("when", {}),
            explanation=d.get("explanation", ""),
            fixes=list(d.get("fixes", [])),
            suspects_from=list(d.get("suspects_from", [])),
            confidence=float(d.get("confidence", 0.7)),
            tags=list(d.get("tags", [])),
            refs=list(d.get("refs", [])),
            source=source,
            once=bool(d.get("once", True)),
        )


class RuleSet:
    """All loaded rules, sorted by priority."""

    def __init__(self, rules: list[Rule]):
        self.rules = sorted(rules, key=lambda r: (r.priority, r.id))
        self.errors: list[str] = []   # load warnings (bad files, dup ids)

    @classmethod
    def load(cls, extra_dirs: list[str | Path] | None = None,
             *, strict: bool = False) -> "RuleSet":
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required: pip install mc-crash-doctor[rules] "
                "(or pip install pyyaml)"
            )
        rules: list[Rule] = []
        errors: list[str] = []
        dirs = [BUILTIN_DIR]
        for d in extra_dirs or []:
            dirs.append(Path(d))
        env = os.environ.get("MCD_RULES_PATH")
        if env:
            dirs.extend(Path(p) for p in env.split(os.pathsep) if p)
        seen_ids: set[str] = set()
        for d in dirs:
            d = Path(d)
            if not d.is_dir():
                if env and str(d) in env:
                    errors.append(f"{d}: directory does not exist")
                continue
            for f in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
                try:
                    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as e:
                    # One malformed user rule file must not take down diagnosis
                    # of unrelated reports. Report it and carry on.
                    first = str(e).splitlines()[0]
                    errors.append(f"{f.name}: {first}")
                    continue
                if not isinstance(doc, dict) or "rules" not in doc:
                    errors.append(f"{f.name}: missing top-level 'rules:' key")
                    continue
                for rd in doc.get("rules") or []:
                    try:
                        r = Rule.from_dict(rd, source=str(f))
                    except (KeyError, TypeError, ValueError) as e:
                        errors.append(f"{f.name}: bad rule {rd.get('id','?')!r}: {e}")
                        continue
                    if r.id in seen_ids:
                        errors.append(f"{f.name}: duplicate rule id {r.id!r} (skipped)")
                        continue
                    seen_ids.add(r.id)
                    rules.append(r)
        rs = cls(rules)
        rs.errors = errors
        if errors and not strict:
            for e in errors:
                print(f"mc-crash-doctor: rule warning: {e}", file=sys.stderr)
        if strict and errors:
            raise ValueError("; ".join(errors))
        return rs

    def ids(self) -> list[str]:
        return [r.id for r in self.rules]


# --- matching ---------------------------------------------------------------
@dataclass
class MatchCtx:
    """Pre-computed views of the report, built once per evaluation."""

    rep: CrashReport
    kinds: list[str]
    exc_texts: list[str]
    msgs: list[str]
    caused: list[str]
    frames_text: list[str]
    top_frames_text: list[str]
    jars: list[str]
    mixins: list[str]
    modids: set[str]
    text: str

    @classmethod
    def build(cls, rep: CrashReport) -> "MatchCtx":
        kinds, msgs, frames_text, jars, mixins = [], [], [], [], []
        for e in rep.exceptions:
            kinds.append(e.kind)
            msgs.append(e.message)
            for f in e.frames:
                frames_text.append(f"{f.cls}.{f.method} {f.jar} {f.mixin_config}"
                                   f" {f.mixin_owner_mod}".strip())
                if f.jar:
                    jars.append(f.jar)
                if f.mixin_config:
                    mixins.append(f.mixin_config)
        caused = [f"{e.kind}: {e.message}".strip(": ")
                  for e in rep.exceptions if e.is_caused_by]
        rc = rep.root_cause
        top = []
        if rc:
            top = [f"{f.cls}.{f.method}" for f in rc.frames[:12]]
        return cls(
            rep=rep,
            kinds=kinds,
            exc_texts=[f"{k}: {m}" for k, m in zip(kinds, msgs)],
            msgs=msgs,
            caused=caused,
            frames_text=frames_text,
            top_frames_text=top,
            jars=jars,
            mixins=mixins,
            modids={m.modid for m in rep.mods if m.modid},
            text=rep.full_text,
        )


def _any_regex(patterns: list[str], subjects: list[str]) -> re.Match | str | None:
    for p in patterns:
        rx = re.compile(p, re.I | re.M)
        for s in subjects:
            m = rx.search(s)
            if m:
                return m
    return None


def _compare(spec: dict | int | float | None, value: float | None) -> bool:
    if spec is None or value is None:
        return False
    if isinstance(spec, (int, float)):
        return value == spec
    return all(_COMPARATORS[op](value, num)
               for op, num in spec.items() if op in _COMPARATORS)


def evaluate_rule(rule: Rule, ctx: MatchCtx) -> dict[str, re.Match] | None:
    """Return capture dict if the rule matches, else None."""
    w = rule.when
    if not w:
        return None
    caps: dict[str, re.Match] = {}

    def need(key: str, subjects: list[str]) -> bool:
        pats = w.get(key)
        if not pats:
            return True
        m = _any_regex(pats, subjects)
        if m and hasattr(m, "groups"):
            caps[key] = m  # type: ignore[assignment]
        return bool(m)

    for key, subs in (
        ("description", [ctx.rep.description]),
        ("exception", ctx.kinds),
        ("exception_msg", ctx.msgs),
        ("exception_any", ctx.exc_texts),
        ("caused_by", ctx.caused + ctx.exc_texts),
        ("frame", ctx.frames_text),
        ("frame_top", ctx.top_frames_text),
        ("jar", ctx.jars),
        ("mixin", ctx.mixins),
        ("text", [ctx.text]),
    ):
        if not need(key, subs):
            return None

    # exact-match fields
    for key, values in (
        ("loader", [ctx.rep.system.loader]),
        ("kind", [ctx.rep.kind]),
    ):
        wanted = w.get(key)
        if wanted and not any(v in wanted for v in values if v):
            return None

    # comparators
    if "java_major" in w and not _compare(w["java_major"],
                                          ctx.rep.system.java_major):
        return None
    if "max_heap_mib" in w and not _compare(w["max_heap_mib"],
                                            ctx.rep.system.xmx_mib
                                            or ctx.rep.system.memory.max_mib):
        return None
    if "mod_count" in w and not _compare(w["mod_count"],
                                         ctx.rep.system.mod_count):
        return None

    # mod presence
    for key in ("has_mod", "not_has_mod"):
        wanted = w.get(key)
        if not wanted:
            continue
        hit = any(fnmatch.fnmatch(m.lower(), p.lower())
                  for p in wanted for m in ctx.modids)
        if key == "has_mod" and not hit:
            return None
        if key == "not_has_mod" and hit:
            return None

    return caps


def _render(template: str, ctx: MatchCtx, caps: dict[str, re.Match]) -> str:
    """Fill {{field}} placeholders from the report/captures."""
    sysd = ctx.rep.system
    values: dict[str, str] = {
        "description": ctx.rep.description,
        "loader": sysd.loader,
        "loader_version": sysd.loader_version,
        "mc_version": sysd.minecraft_version,
        "java_version": sysd.java_version,
        "java_major": str(sysd.java_major or ""),
        "xms_mib": str(sysd.xms_mib or ""),
        "xmx_mib": str(sysd.xmx_mib or ""),
        "heap_used_mib": str(sysd.memory.used_mib or ""),
        "heap_max_mib": str(sysd.memory.max_mib or ""),
        "mod_count": str(sysd.mod_count or len(ctx.rep.mods) or ""),
        "os": sysd.os_name,
        "time": ctx.rep.time,
        "root_exception": (ctx.rep.root_cause.kind if ctx.rep.root_cause else ""),
        "root_message": (ctx.rep.root_cause.message if ctx.rep.root_cause else ""),
    }
    # regex captures: {{cap:key}} or {{cap:key:1}}
    def _cap(m: re.Match) -> str:
        parts = m.group(1).split(":")
        key = parts[0]
        gi = int(parts[1]) if len(parts) > 1 else 1
        rx = caps.get(key)
        if rx is None:
            return ""
        try:
            return rx.group(gi) or ""
        except (IndexError, re.error):
            return ""

    out = re.sub(r"\{\{cap:([\w:]+)\}\}", _cap, template)
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def run_rules(rep: CrashReport, ruleset: RuleSet | None = None,
              suspect_fn=None) -> list[Finding]:
    """Evaluate all rules against a parsed report."""
    rs = ruleset or RuleSet.load()
    ctx = MatchCtx.build(rep)
    findings: list[Finding] = []
    for rule in rs.rules:
        caps = evaluate_rule(rule, ctx)
        if caps is None:
            continue
        evidence = _collect_evidence(rule, ctx, caps)
        suspects: list[str] = []
        if suspect_fn and rule.suspects_from:
            suspects = suspect_fn(rep, rule.suspects_from, caps)
        findings.append(Finding(
            rule_id=rule.id,
            title=_render(rule.title, ctx, caps),
            severity=rule.severity,
            summary=_render(rule.explanation, ctx, caps),
            explanation=_render(rule.explanation, ctx, caps),
            evidence=evidence,
            fixes=[_render(f, ctx, caps) for f in rule.fixes],
            suspects=suspects,
            confidence=rule.confidence,
            tags=list(rule.tags),
            refs=list(rule.refs),
        ))
    findings.sort(key=lambda f: (-f.severity, -f.confidence))
    return findings


def _collect_evidence(rule: Rule, ctx: MatchCtx,
                      caps: dict[str, re.Match]) -> list[str]:
    """Quoted evidence lines supporting the finding."""
    out: list[str] = []
    for key, m in caps.items():
        try:
            frag = m.group(0)
        except Exception:  # noqa: BLE001
            continue
        frag = frag.strip()
        if frag and frag not in out:
            out.append(frag[:220])
    if not out:
        # fall back to the matched line from the raw text for text-rules
        w = rule.when.get("text")
        if w:
            for p in w:
                mm = re.search(p, ctx.text, re.I | re.M)
                if mm:
                    out.append(mm.group(0).strip()[:220])
                    break
    return out[:4]
