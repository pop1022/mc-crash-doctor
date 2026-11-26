#!/usr/bin/env bash
# Run every gate in this repo. Usage: bash run_tests.sh
#
# Exits non-zero if any gate fails, so it can back a CI workflow.
set -u
cd "$(dirname "$0")"

PY="${PYTHON:-python}"
fail=0

# GitHub renders these as annotations on the failed check, which is the only
# part of a CI failure that can be read without admin rights on the repo.
FAILED_GATES=()
mark_fail() {
  FAILED_GATES+=("$1")
  fail=1
  echo "::error title=Gate $1 failed::$1 - see the log above for the failing assertion"
}

echo "════════════════════════════════════════════════"
echo " mc-crash-doctor test suite"
echo "════════════════════════════════════════════════"

echo
echo "── [1/8] redaction (privacy boundary) ──"
if ! "$PY" tests/test_redaction.py; then mark_fail "1/8 redaction"; fi

echo
echo "── [2/8] parser accuracy vs upstream expectations ──"
if ! "$PY" tests/eval_parser.py --strict; then mark_fail "2/8 parser accuracy"; fi

echo
echo "── [3/8] end-to-end + ground truth ──"
# Ground-truth reports ship in-repo, so this runs on any machine / in CI.
if ! "$PY" tests/test_e2e.py; then mark_fail "3/8 end-to-end"; fi

echo
echo "── [4/8] pytest suite (per-file corpus + gap pinning) ──"
# A FIXED --basetemp is a trap: pytest wipes it before each run, and the suite
# creates ~233 tmp_path dirs. On the second run that wipe is a bulk delete and
# the environment's safe-delete guard kills the process at setup -- 98 errors
# that have nothing to do with the tests. Unique basetemps per gate avoid the
# wipe entirely; the scratch trees stay in tmp/ (gitignored) and can be pruned
# by hand. Gate [7] gets its own tree so it cannot wipe gate [4]'s.
STAMP="$(date +%Y%m%d%H%M%S)-$$"
PYTEST_TMP_SUITE="tmp/.pytest-tmp-suite-$STAMP"
PYTEST_TMP_DOCS="tmp/.pytest-tmp-docs-$STAMP"
if "$PY" -m pytest --version >/dev/null 2>&1; then
  PYTEST_LOG="tmp/.pytest-log-$STAMP.txt"
  "$PY" -m pytest tests/ -q --basetemp="$PYTEST_TMP_SUITE" 2>&1 | tee "$PYTEST_LOG"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then
    # One annotation per failing test: the job log needs repo admin rights,
    # the annotations do not, so a red run still says which test broke.
    grep -E "^(FAILED|ERROR) " "$PYTEST_LOG" | head -20 |
      sed -e 's/^/::error title=pytest::/' || true
    mark_fail "4/8 pytest"
  fi
else
  echo "  (pytest not installed -- skipping; pip install pytest)"
fi

echo
echo "── [5/8] import + CLI smoke ──"
# The tick used to print unconditionally, so a failing import still showed a
# green check above a red gate summary. Both checks now guard it.
if "$PY" -c "import mcd; assert mcd.__version__; mcd.RuleSet.load()" \
   && "$PY" -m mcd --rules >/dev/null 2>&1 \
   && "$PY" -m mcd --validate-rules >/dev/null 2>&1; then
  echo "  ✓ import mcd + rule load + CLI --rules + --validate-rules"
else
  mark_fail "5/8 CLI smoke"
fi

echo
echo "── [6/8] lint (correctness rules only) ──"
# Optional tool: the gate must not fail because a contributor has no ruff.
# Config lives in pyproject.toml under [tool.ruff]; select = F, E9, B.
if "$PY" -m ruff --version >/dev/null 2>&1; then
  if ! "$PY" -m ruff check mcd/ tools/ tests/; then mark_fail "6/8 lint"; fi
elif command -v ruff >/dev/null 2>&1; then
  if ! ruff check mcd/ tools/ tests/; then mark_fail "6/8 lint"; fi
else
  echo "  (ruff not installed -- skipping; pip install ruff)"
fi

echo
echo "── [7/8] docs quote the numbers in corpus/*.json ──"
# Prose is not compiled: ROADMAP once cited 45.8% while its own later section
# said 50.8%, and README advertised two shipped features as in-progress for a
# quarter. This gate recomputes each ratio from its JSON source and fails if the
# doc stopped matching -- it cannot catch a wrong sentence, only a stale number,
# which is the drift that actually happened.
if ! "$PY" -m pytest tests/test_doc_numbers.py -q --basetemp="$PYTEST_TMP_DOCS"; then
  mark_fail "7/8 docs numbers"
fi

echo
echo "── [8/8] coverage floors (per package, measured) ──"
# Floors live in tools/coverage_gate.py with a reason per number. The gate runs
# the suite under coverage itself, so it does not depend on gate [4]'s artifacts;
# without coverage installed it prints a skip and passes, which is why CI
# installs .[test].
if ! "$PY" tools/coverage_gate.py --run; then mark_fail "8/8 coverage"; fi

echo
if [ "$fail" -eq 0 ]; then
  echo "════════ ✓ ALL GATES PASSED ════════"
else
  echo "════════ ✗ SOME GATES FAILED ════════"
  echo "failed: ${FAILED_GATES[*]}"
fi
exit $fail