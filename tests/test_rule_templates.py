"""Optional template fragments: {{#key}} ... {{/key}}.

A crash log without System Details has no heap ceiling, and the OOM rule used to
print "Max heap was  MiB at crash time" -- a sentence with a hole in it. The
block is kept only when the value exists; nothing is invented to fill it.
"""
from __future__ import annotations

from pathlib import Path

from mcd.parser.report import parse_file, parse_text
from mcd.rules.engine import RuleSet, _config_warnings, _fill_conditionals, run_rules

GT = Path(__file__).resolve().parent / "fixtures" / "ground-truth"

BARE_OOM = (
    "---- Minecraft Crash Report ----\n"
    "Description: Ticking entity\n\n"
    "java.lang.OutOfMemoryError: Java heap space\n"
    "\tat a.b.C.d(C.java:1)\n\tat a.b.C.e(C.java:2)\n"
)

WITH_DETAILS = BARE_OOM + """
-- System Details --
Details:
\tMinecraft Version: 1.20.1
\tJava Version: 17.0.8, Microsoft
\tMemory: 1000 MiB / 2048 MiB (48.8%)/ 8192 MiB
"""


def test_a_block_disappears_when_the_value_is_missing() -> None:
    findings = run_rules(parse_text(BARE_OOM), RuleSet.load())
    oom = next(f for f in findings if f.rule_id == "oom.heap")
    assert "MiB" not in oom.explanation
    assert "{{" not in oom.explanation


def test_a_block_appears_when_the_value_exists() -> None:
    # The real fixture carries "Memory: ... 2048 MiB" under System Details.
    rep = parse_file(str(GT / "crash-2026-09-08_18.01.19-server.txt"))
    findings = run_rules(rep, RuleSet.load())
    oom = next(f for f in findings if f.rule_id == "oom.heap")
    assert "2048 MiB" in oom.explanation


def test_no_template_marker_reaches_any_finding() -> None:
    rs = RuleSet.load()
    for path in GT.glob("*.txt"):
        for f in run_rules(parse_text(path.read_text(encoding="utf-8")), rs):
            assert "{{" not in f.explanation, (path.name, f.rule_id)
            for fx in f.fixes:
                assert "{{" not in fx, (path.name, f.rule_id)


def test_an_unbalanced_block_is_named_at_load_time() -> None:
    errs = _config_warnings("r.yaml", {
        "id": "x", "explanation": "before {{#heap_max_mib}} after"})
    assert any("unbalanced" in e for e in errs)


def test_unbalanced_markers_are_stripped_not_printed() -> None:
    assert _fill_conditionals("a {{#k}} b", {"k": "1"}) == "a  b"


def test_nested_or_repeated_blocks_all_resolve() -> None:
    text = "{{#a}}A{{/a}}{{#b}}B{{/b}}{{#c}}C{{/c}}"
    assert _fill_conditionals(text, {"a": "1", "b": "", "c": "1"}) == "AC"

# --- the sweep: every rule, every field, no report data at all --------------
class _FakeMatch:
    def group(self, i: int = 0) -> str:
        return "X"


class _AnyCaps(dict):
    def get(self, key, default=None):
        return _FakeMatch()


def _rendered_fields() -> list[tuple[str, str, str]]:
    from mcd.model import CrashReport
    from mcd.rules.engine import MatchCtx, _render

    ctx = MatchCtx.build(CrashReport())        # every report field empty
    rs = RuleSet.load()
    rows: list[tuple[str, str, str]] = []
    for rule in rs.rules:
        fields = [(n, getattr(rule, n, None))
                  for n in ("title", "title_zh", "explanation", "explanation_zh")]
        fields += [(f"fix{i}", f) for i, f in enumerate(rule.fixes or [])]
        fields += [(f"fixzh{i}", f) for i, f in enumerate(rule.fixes_zh or [])]
        for name, value in fields:
            if isinstance(value, str) and value:
                rows.append((rule.id, name, _render(value, ctx, _AnyCaps())))
    return rows


def test_no_rendered_copy_has_a_hole() -> None:
    rows = _rendered_fields()
    assert len(rows) > 200, len(rows)
    for rule_id, field, out in rows:
        assert "{{" not in out, (rule_id, field, out)
        assert "  " not in out, (rule_id, field, out)
        assert "()" not in out and "（）" not in out, (rule_id, field, out)
        assert out == out.strip(), (rule_id, field, out)


def test_tidy_only_touches_what_an_empty_field_left_behind() -> None:
    from mcd.rules.engine import _tidy

    assert _tidy("was  MiB") == "was MiB"
    assert _tidy("x ( ) y") == "x y"
    assert _tidy("a ，b") == "a，b"
    assert _tidy("  kept  ")
    assert _tidy("normal sentence, with punctuation.") == \
        "normal sentence, with punctuation."
