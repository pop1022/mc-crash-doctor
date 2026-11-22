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

# Rule lifecycle states (VISION §4.4). from_dict rejects anything else, so a
# typo'd status fails at load time instead of silently meaning "unmanaged".
LIFECYCLE_STATES = frozenset({
    "draft", "experimental", "verified", "stable", "deprecated", "retired",
})

#: Every top-level rule key `Rule.from_dict` reads. Anything else in a rule
#: mapping is ignored in silence, which is how `fix:` (for `fixes:`) ships a
#: diagnosis with no repair steps and no error. Same role as WHEN_KEYS, one
#: level up -- see `_config_warnings`.
RULE_KEYS = frozenset({
    "id", "title", "severity", "priority", "when", "explanation", "fixes",
    "suspects_from", "confidence", "tags", "refs", "once", "lifecycle_status",
    "provenance", "commands", "expect",
    # Chinese copy (optional, per rule; falls back to the English fields)
    "title_zh", "explanation_zh", "fixes_zh",
})

#: Commands a rule may suggest. The tool never runs them: these are printed for
#: the user to copy. So the allowlist is about *advice* safety -- a diagnostic a
#: user can ignore harmlessly, never a step that touches their files. A rule that
#: wants `rm mods/foo.jar` can say so in `fixes`; it cannot dress it as a command.
SAFE_COMMAND_PREFIXES = (
    "java -version", "java -XshowSettings", "jps", "jcmd", "nvidia-smi",
)


def is_safe_command(cmd: str) -> bool:
    """True for the read-only diagnostics above, and nothing else."""
    c = " ".join((cmd or "").split())
    if not c:
        return False
    return any(c == p or c.startswith(p + " ") or c.startswith(p + ":")
               for p in SAFE_COMMAND_PREFIXES)

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
    #: Chinese copy, authored per rule and optional. A rule without it falls
    #: back to the English text rather than printing an empty finding -- the
    #: translator's backlog is visible in tools/i18n_status.py, not in the UI.
    title_zh: str = ""
    explanation_zh: str = ""
    fixes_zh: list[str] = field(default_factory=list)
    #: Read-only diagnostics printed under the fixes. Filtered by
    #: `safe_commands` at emission time; unsafe entries are also warned about at
    #: load time, so nothing is dropped quietly.
    commands: list[str] = field(default_factory=list)
    suspects_from: list[str] = field(default_factory=list)
    # suspects_from entries: 'mixin' | 'jar' | 'frame_mods' | 'mod:<id>'
    confidence: float = 0.7
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    source: str = ""             # yaml file it came from
    once: bool = True            # emit at most one finding
    # Rule lifecycle: draft -> experimental -> verified -> stable ->
    # deprecated -> retired (VISION §4.4). Only verified/stable rules count
    # toward the published diagnosis-rate numbers.
    lifecycle_status: str = "verified"
    # Where this rule came from -- the real report(s) that motivated it and/or
    # the synthetic fixture that proves it. This is the in-YAML single source
    # of truth for what tests/test_gaps.py used to hardcode; see ROADMAP 1A.3.
    # Shape: {"fixtures": ["sodium/3711", ...], "notes": "..."} where a
    # fixture key is either "repo/issue" (harvested corpus, gitignored) or a
    # bare filename under tests/fixtures/synthetic/.
    provenance: dict[str, Any] = field(default_factory=dict)
    #: Per-rule fixture assertions: {"fires": [ref], "quiet": [ref]}.
    #: provenance.fixtures is the historical "which report motivated this"
    #: (checked by tests/test_gaps.py against the gitignored corpus); expect
    #: travels with the rule and is checked by --validate-rules, which is the
    #: only self-test a third-party pack can carry.
    expect: dict[str, Any] = field(default_factory=dict)

    @property
    def safe_commands(self) -> tuple[str, ...]:
        return tuple(c for c in self.commands if is_safe_command(c))

    @classmethod
    def from_dict(cls, d: dict[str, Any], source: str = "") -> "Rule":
        sev = d.get("severity", "error")
        status = str(d.get("lifecycle_status", "verified"))
        if status not in LIFECYCLE_STATES:
            raise ValueError(
                f"lifecycle_status {status!r} not one of "
                f"{sorted(LIFECYCLE_STATES)}")
        prov = d.get("provenance", {})
        if not isinstance(prov, dict):
            raise ValueError("provenance must be a mapping")
        return cls(
            id=d["id"],
            title=d["title"],
            severity=Severity[str(sev).upper()],
            priority=int(d.get("priority", 100)),
            when=d.get("when", {}),
            explanation=d.get("explanation", ""),
            fixes=list(d.get("fixes", [])),
            title_zh=d.get("title_zh", ""),
            explanation_zh=d.get("explanation_zh", ""),
            fixes_zh=list(d.get("fixes_zh", [])),
            commands=[str(c) for c in (d.get("commands") or [])],
            suspects_from=list(d.get("suspects_from", [])),
            confidence=float(d.get("confidence", 0.7)),
            tags=list(d.get("tags", [])),
            refs=list(d.get("refs", [])),
            source=source,
            once=bool(d.get("once", True)),
            lifecycle_status=status,
            expect=d.get("expect", {}) if isinstance(d.get("expect"), dict) else {},
            provenance=prov,
        )


class RuleSet:
    """All loaded rules, sorted by priority."""

    def __init__(self, rules: list[Rule]):
        self.rules = sorted(rules, key=lambda r: (r.priority, r.id))
        self.errors: list[str] = []   # load warnings (bad files, dup ids)

    # Parsed YAML is immutable after load: nothing in run_rules() writes to a
    # Rule, and the sorted list belongs to the wrapper, not the cache. So the
    # expensive half (24.9 ms of YAML parsing for 41 rules) can be shared while
    # every caller still gets its own mutable RuleSet and its own `errors`.
    #
    # Measured before this cache: 67% of a single diagnosis was re-parsing the
    # same three builtin files -- 120 reports cost 5.91 s, of which ~3.0 s was
    # loading rules 120 times.
    _cache: dict[tuple[str, ...], tuple[list["Rule"], list[str]]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Drop the parsed-rule cache.

        Only needed by long-lived processes that rewrite rule YAML in place;
        the CLI is one-shot, so it never has to call this.
        """
        cls._cache.clear()

    @classmethod
    def _cache_key(cls, extra_dirs) -> tuple[str, ...]:
        dirs = [os.path.abspath(str(d)) for d in (extra_dirs or ())]
        # MCD_RULES_PATH participates in the key: a changed environment must
        # not silently reuse a rule set assembled from the old one.
        return tuple(dirs) + ("env=" + (os.environ.get("MCD_RULES_PATH") or ""),)

    @classmethod
    def load(cls, extra_dirs: list[str | Path] | None = None,
             *, strict: bool = False, report: bool = True) -> "RuleSet":
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required: pip install mc-crash-doctor[rules] "
                "(or pip install pyyaml)"
            )
        key = cls._cache_key(extra_dirs)
        cached = cls._cache.get(key)
        if cached is None:
            cached = cls._read(extra_dirs)
            cls._cache[key] = cached
        rules, errors = cached[0], list(cached[1])
        # A fresh wrapper per call: `errors` is per-caller mutable, and
        # __init__ re-sorts into its own list, so a caller cannot corrupt the
        # shared parse.
        rs = cls(rules)
        rs.errors = errors
        # `report=False` exists for --validate-rules, which prints the same
        # strings itself in a grouped form. Two printers would show each warning
        # twice, and a gate that double-reports is one people learn to ignore.
        if errors and not strict and report:
            for e in errors:
                print(f"mc-crash-doctor: rule warning: {e}", file=sys.stderr)
        if strict and errors:
            raise ValueError("; ".join(errors))
        return rs

    @classmethod
    def _read(cls, extra_dirs) -> tuple[list["Rule"], list[str]]:
        """Parse every rule directory. The cacheable, side-effect-free half."""
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
                # Never silent: a directory the caller asked for that is not
                # there means their rules did NOT load. Warning beats guessing.
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
                    if not isinstance(rd, dict):
                        # `- just a string` under `rules:` used to escape the
                        # per-rule handler below (AttributeError is not in its
                        # except tuple) and take down the whole load.
                        errors.append(f"{f.name}: rule entry is not a mapping")
                        continue
                    errors.extend(_config_warnings(f.name, rd))
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
        return rules, errors

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
    triage: object | None = None   # TriageResult, set by run_rules

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


#: Every `when` key `evaluate_rule` actually honours.
#:
#: Unknown keys are silently ignored -- there is no schema. That is the same
#: failure shape as the frame parser dropping half the stack without raising
#: (ROADMAP 1E.5). `WHEN_KEYS` exists so a test can walk the shipped packs and
#: refuse a key the engine does not read, and so `_config_warnings` can tell a
#: rule author what load ignored.
#:
#: Correction, measured on tmp/unknown_key_probe.py: an earlier version of this
#: note claimed a typo "produces a rule that never fires". That is the harmless
#: half. A `when` block whose keys are ALL unknown keeps `w` non-empty, so it
#: passes the emptiness check at the top of `evaluate_rule` with no conditions
#: left to fail -- the rule becomes a catch-all. A rule written to match
#: `exceptions: [OutOfMemoryError]` fired on 4/4 synthetic fixtures, including
#: ones with no OOM in them. Silent, and a false positive on every report.
WHEN_KEYS = frozenset({
    # regex conditions (positive)
    "description", "exception", "exception_msg", "exception_any", "caused_by",
    "frame", "frame_top", "jar", "mixin", "text",
    # regex conditions (negative) -- see the loop in evaluate_rule
    "not_exception",
    # exact / comparator conditions
    "loader", "kind", "java_major", "max_heap_mib", "mod_count", "mc_version",
    # mod-presence and attribution gates
    "has_mod", "not_has_mod", "has_suspect",
    # disjunction: a list of condition blocks, any one of which may match.
    # Keys outside it are still ANDed, so a rule can say "always require this,
    # and accept either of those".
    "when_any",
})


def _config_warnings(fname: str, rd: dict[str, Any]) -> list[str]:
    """Warn about rule keys that the loader or the engine will not read.

    Warn, never raise: breaking a user's working rule directory to catch a typo
    is the wrong trade (see WHEN_KEYS). These land in `RuleSet.errors`, which
    the CLI prints to stderr, and `--strict` still promotes them to a failure --
    which is what strict is for.

    Builtin packs cannot regress through this path: tests/test_rule_metadata.py
    already fails on an unknown `when` key, and the top-level sibling of that
    assertion lives in tests/test_rule_config_warnings.py.
    """
    rid = rd.get("id", "?")
    out: list[str] = []
    unknown = sorted(set(rd) - RULE_KEYS)
    if unknown:
        out.append(f"{fname}: rule {rid!r}: unknown key(s) {unknown} "
                   f"-- not read by the loader")
    raw_cmds = rd.get("commands") or []
    if not isinstance(raw_cmds, list):
        out.append(f"{fname}: rule {rid!r}: commands must be a list")
    else:
        unsafe = [c for c in raw_cmds if not is_safe_command(str(c))]
        if unsafe:
            out.append(
                f"{fname}: rule {rid!r}: command(s) {unsafe} are not read-only "
                f"diagnostics -- dropped. The tool prints commands for the user "
                f"to run, so only {list(SAFE_COMMAND_PREFIXES)} are accepted; "
                f"put anything else in `fixes` as prose")
    when = rd.get("when")
    if isinstance(when, dict) and when:
        unknown_when = sorted(set(when) - WHEN_KEYS)
        if unknown_when:
            tail = ("the other conditions still apply"
                    if set(when) & WHEN_KEYS
                    else "nothing is left to match on, so it matches EVERY report")
            out.append(f"{fname}: rule {rid!r}: unknown condition(s) "
                       f"{unknown_when} -- ignored by the engine; {tail}")
        if "when_any" in when:
            out.extend(_when_any_warnings(fname, rid, when["when_any"]))
    if "expect" in rd:
        # Imported here, not at module scope: expect.py imports this module for
        # Rule/RuleSet/run_rules, so a top-level import would be circular.
        from .expect import warnings_for
        out.extend(warnings_for(fname, rid, rd.get("expect")))
    texts = [("explanation", rd.get("explanation", "")),
             ("explanation_zh", rd.get("explanation_zh", ""))]
    texts += [(f"fixes[{i}]", fx) for i, fx in enumerate(rd.get("fixes") or [])]
    for label, text in texts:
        if not isinstance(text, str):
            continue
        opens = re.findall(r"\{\{#(\w+)\}\}", text)
        closes = re.findall(r"\{\{/(\w+)\}\}", text)
        if sorted(opens) != sorted(closes):
            out.append(f"{fname}: rule {rid!r}: {label} has an unbalanced "
                       f"conditional block -- it is stripped at render time")
    return out


def _when_any_warnings(fname: str, rid: str, clauses: object) -> list[str]:
    """Shape checks for when_any. Each message says what the engine will do."""
    out: list[str] = []
    if not isinstance(clauses, list):
        return [f"{fname}: rule {rid!r}: when_any must be a list of condition "
                f"blocks -- the rule matches nothing as written"]
    if not clauses:
        return [f"{fname}: rule {rid!r}: when_any is empty -- the rule matches "
                f"nothing"]
    for i, clause in enumerate(clauses):
        if not isinstance(clause, dict):
            out.append(f"{fname}: rule {rid!r}: when_any[{i}] is not a block "
                       f"of conditions -- skipped")
        elif "when_any" in clause:
            out.append(f"{fname}: rule {rid!r}: nested when_any inside "
                       f"when_any[{i}] is not supported -- that block never "
                       f"matches; flatten it")
        elif not (set(clause) & WHEN_KEYS):
            out.append(f"{fname}: rule {rid!r}: when_any[{i}] has no condition "
                       f"the engine reads -- it matches every report")
    return out


#: A version clause: optional operator, then digits and dots.
_VERSION_CLAUSE = re.compile(r"^(>=|<=|>|<|=)?\s*v?(\d+(?:\.\d+)*)$")


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


def _version_ok(spec: str, version: str) -> bool:
    """Does `version` satisfy `spec`?

    Spec grammar: clauses separated by spaces, each `<op><version>` with op in
    >=, <=, >, < or = (default =, meaning a prefix match: "1.20" matches
    1.20.1 but not 1.201). Every clause must hold, so ">=1.20 <1.21" is a
    range.

    A report that never states its Minecraft version satisfies no version
    gate: the rule cannot prove it applies, and guessing is the failure mode
    this project exists to avoid. 30% of the corpus has no version line, so a
    gate is a real narrowing -- use it only where the version is the point.
    """
    if not version:
        return False
    got = _version_tuple(version)
    for clause in str(spec).split():
        m = _VERSION_CLAUSE.match(clause)
        if not m:
            return False
        op, want_raw = m.group(1) or "=", m.group(2)
        want = _version_tuple(want_raw)
        if op == "=":
            if not (version == want_raw or version.startswith(want_raw + ".")):
                return False
        elif op == ">=":
            ok = got >= want
        elif op == "<=":
            ok = got <= want
        elif op == ">":
            ok = got > want
        else:
            ok = got < want
        if op != "=" and not ok:
            return False
    return True


def _evaluate_all(w: dict, ctx: MatchCtx) -> dict[str, re.Match] | None:
    """AND every key in one condition block. Returns its captures or None."""
    # Nesting is not supported: a clause that itself says when_any has no
    # meaning the engine can explain, so it matches nothing instead of
    # half-applying. _config_warnings names it at load time.
    if "when_any" in w:
        return None
    # A `when` block containing no key the engine reads matches nothing, exactly
    # like an empty one. Without the second half of this test, `exceptions:`
    # (typo for `exception:`) leaves a non-empty dict with no conditions in it,
    # so the emptiness check passes and there is nothing left to fail -- the
    # rule becomes a catch-all. Measured before the fix: such a rule fired on
    # 4/4 synthetic fixtures, including reports with no OOM in them, and said
    # nothing. `_config_warnings` names the typo at load time; this stops it
    # from also producing a finding.
    if not w or not (w.keys() & WHEN_KEYS):
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

    # Negative regex conditions: the condition is satisfied by a report the
    # patterns do NOT match, i.e. by an empty match set.
    #
    # `not_exception` exists because a catch-all is a legitimate rule shape.
    # `crash.runtime-mod` wants "a java exception, and attribution found
    # someone", and `.lang.<something>Error` is the honest way to say that --
    # but it also swallows OutOfMemoryError, which has its own rule and its own
    # advice. Without this key the choice is a catch-all that contradicts the
    # OOM rule, or a hand-maintained negative-lookahead regex. The first is
    # wrong (dogfood issue #1) and the second is unreadable.
    for key, subs in (("not_exception", ctx.kinds),):
        pats = w.get(key)
        if pats and _any_regex(pats, subs):
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
    if "mc_version" in w:
        spec = w["mc_version"]
        specs = [str(s) for s in spec] if isinstance(spec, (list, tuple)) else [str(spec)]
        if not any(_version_ok(s, ctx.rep.system.minecraft_version) for s in specs):
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

    # attribution gate: rules that say "mod X crashed at runtime" are only
    # honest when the triage layer actually resolved a suspect mod. Without
    # this gate a catch-all rule fires on vanilla crashes and blames nothing.
    if w.get("has_suspect"):
        if ctx.triage is None or not ctx.triage.suspects:
            return None

    return caps


def evaluate_rule(rule: Rule, ctx: MatchCtx) -> dict[str, re.Match] | None:
    """Return capture dict if the rule matches, else None.

    Two shapes:
      * a plain block -- every key must hold (AND), a list inside a key is
        any-of (that is what _any_regex does);
      * `when_any: [block, block, ...]` -- keys beside it are still required,
        and then any one block may satisfy the rest.

    Captures are merged from the keys outside when_any plus the block that
    matched, so a template can use either. When two blocks set the same capture
    key, the matching block wins: it is the one that describes this report.
    """
    w = rule.when
    clauses = w.get("when_any") if isinstance(w, dict) else None
    if not clauses:
        return _evaluate_all(w, ctx)

    rest = {k: v for k, v in w.items() if k != "when_any"}
    base = _evaluate_all(rest, ctx) if rest else {}
    if base is None:
        return None
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        caps = _evaluate_all(clause, ctx)
        if caps is not None:
            return {**base, **caps}
    return None


#: Optional fragments: {{#key}} ... {{/key}} keeps the body only when the value
#: is non-empty. A crash log without System Details has no heap ceiling, and
#: "Max heap was  MiB at crash time" is worse than saying nothing.
_COND = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.S)


#: Artifacts of an empty placeholder, removed after substitution. The rules
#: already guard most of these with when: conditions, but a log without System
#: Details can still reach copy that assumed a value was there.
_TIDY = (
    # Empty parens first: removing them leaves two spaces behind, which the
    # collapse below then cleans up.
    (re.compile(r"\(\s*\)|（\s*）"), ""),
    (re.compile(r"[ \t]+([,.;:!?，。；：！？、])"), r"\1"),
    (re.compile(r"([（(])[ \t]+"), r"\1"),
    (re.compile(r"[ \t]+([）)])"), r"\1"),
    (re.compile(r"[ \t]{2,}"), " "),
)


def _tidy(text: str) -> str:
    """Collapse what an empty field leaves behind: "was  MiB", "( )", " ，".

    Wording can still read oddly ("for / fabric" when the version is unknown),
    but it never prints a hole or a double space in the middle of a sentence.
    """
    for pattern, repl in _TIDY:
        text = pattern.sub(repl, text)
    return text.strip()


def _fill_conditionals(template: str, values: dict[str, str]) -> str:
    """Resolve optional blocks, then strip any marker that is left over."""
    def one(m: re.Match) -> str:
        key, body = m.group(1), m.group(2)
        return body if values.get(key) else ""

    out = template
    prev = None
    # A loop because re.sub does not rescan the replacement text, and two
    # sibling blocks in one sentence both have to resolve.
    while prev != out:
        prev = out
        out = _COND.sub(one, out)
    # Unbalanced or unknown markers are removed instead of being printed to a
    # user. _config_warnings names the file so the author can fix it.
    return re.sub(r"\{\{#[^}]+\}\}|\{\{/[^}]+\}\}", "", out)


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
    if ctx.triage is not None and getattr(ctx.triage, "suspects", None):
        top = ctx.triage.suspects[0]
        values["suspect_top"] = top.name or top.modid
        values["suspect_top_id"] = top.modid
        values["suspect_top_conf"] = f"{top.confidence:.0%}"
    else:
        values["suspect_top"] = values["suspect_top_id"] = ""
        values["suspect_top_conf"] = ""
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

    out = _fill_conditionals(template, values)
    out = re.sub(r"\{\{cap:([\w:]+)\}\}", _cap, out)
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v)
    return _tidy(out)


def _localised(rule: Rule, lang: str) -> tuple[str, str, list[str]]:
    """Pick the copy for the requested language: zh when translated, else English.

    Localisation happens before the Finding is built, so every consumer
    (terminal, Markdown, JSON, the browser) receives one already-localised
    document and no consumer needs its own fallback table.
    """
    if lang.lower().startswith("zh") and rule.title_zh:
        return (rule.title_zh,
                rule.explanation_zh or rule.explanation,
                rule.fixes_zh or rule.fixes)
    return rule.title, rule.explanation, rule.fixes


def run_rules(rep: CrashReport, ruleset: RuleSet | None = None,
              suspect_fn=None, lang: str = "en") -> list[Finding]:
    """Evaluate all rules against a parsed report."""
    rs = ruleset or RuleSet.load()
    ctx = MatchCtx.build(rep)
    # Run attribution once so rules can gate on it (has_suspect) and name the
    # top mod ({{suspect_top}}) without recomputing.
    try:
        from ..triage.attribution import triage as _triage

        ctx.triage = _triage(rep)
    except Exception:  # noqa: BLE001 - attribution must never break diagnosis
        ctx.triage = None
    findings: list[Finding] = []
    for rule in rs.rules:
        caps = evaluate_rule(rule, ctx)
        if caps is None:
            continue
        evidence = _collect_evidence(rule, ctx, caps)
        suspects: list[str] = []
        if suspect_fn and rule.suspects_from:
            suspects = suspect_fn(rep, rule.suspects_from, caps)
        r_title, r_expl, r_fixes = _localised(rule, lang)
        findings.append(Finding(
            rule_id=rule.id,
            title=_render(r_title, ctx, caps),
            severity=rule.severity,
            summary=_render(r_expl, ctx, caps),
            explanation=_render(r_expl, ctx, caps),
            evidence=evidence,
            fixes=[_render(f, ctx, caps) for f in r_fixes],
            commands=[_render(c, ctx, caps) for c in rule.safe_commands],
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
    for m in caps.values():
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
