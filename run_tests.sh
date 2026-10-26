#!/usr/bin/env bash
# Run every gate in this repo. Usage: bash run_tests.sh
#
# Exits non-zero if any gate fails, so it can back a CI workflow.
set -u
cd "$(dirname "$0")"

PY="${PYTHON:-python}"
fail=0

echo "════════════════════════════════════════════════"
echo " mc-crash-doctor test suite"
echo "════════════════════════════════════════════════"

echo
echo "── [1/6] redaction (privacy boundary) ──"
if ! "$PY" tests/test_redaction.py; then fail=1; fi

echo
echo "── [2/6] parser accuracy vs upstream expectations ──"
if ! "$PY" tests/eval_parser.py --strict; then fail=1; fi

echo
echo "── [3/6] end-to-end + ground truth ──"
# Ground-truth reports ship in-repo, so this runs on any machine / in CI.
if ! "$PY" tests/test_e2e.py; then fail=1; fi

echo
echo "── [4/6] pytest suite (per-file corpus + gap pinning) ──"
if "$PY" -m pytest --version >/dev/null 2>&1; then
  # --basetemp inside the repo: pytest otherwise leaves ~80 scratch dirs in the
  # system temp, and a sandbox/CI hook that rate-limits bulk deletes can turn a
  # fully green run into a non-zero exit at cleanup time. Keeping the scratch
  # tree in tmp/ (gitignored) makes the gate's result depend on the tests only.
  if ! "$PY" -m pytest tests/ -q --basetemp=tmp/.pytest-tmp; then fail=1; fi
else
  echo "  (pytest not installed -- skipping; pip install pytest)"
fi

echo
echo "── [5/6] import + CLI smoke ──"
if ! "$PY" -c "import mcd; assert mcd.__version__; mcd.RuleSet.load()"; then fail=1; fi
if ! "$PY" -m mcd --rules >/dev/null 2>&1; then fail=1; fi
echo "  ✓ import mcd + rule load + CLI --rules"

echo
echo "── [6/6] lint (correctness rules only) ──"
# Optional tool: the gate must not fail because a contributor has no ruff.
# Config lives in pyproject.toml under [tool.ruff]; select = F, E9, B.
if "$PY" -m ruff --version >/dev/null 2>&1; then
  if ! "$PY" -m ruff check mcd/ tools/ tests/; then fail=1; fi
elif command -v ruff >/dev/null 2>&1; then
  if ! ruff check mcd/ tools/ tests/; then fail=1; fi
else
  echo "  (ruff not installed -- skipping; pip install ruff)"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "════════ ✓ ALL GATES PASSED ════════"
else
  echo "════════ ✗ SOME GATES FAILED ════════"
fi
exit $fail
