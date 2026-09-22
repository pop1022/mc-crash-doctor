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
echo "── [1/4] redaction (privacy boundary) ──"
if ! "$PY" tests/test_redaction.py; then fail=1; fi

echo
echo "── [2/4] parser accuracy vs upstream expectations ──"
if ! "$PY" tests/eval_parser.py --strict; then fail=1; fi

echo
echo "── [3/4] end-to-end + ground truth ──"
# --corpus when the local ground-truth dir is absent (CI has no Minecraft server)
if [ -n "${MCD_MC_DIR:-}" ] || [ -d "/c/Users/Administrator/Desktop/mc" ]; then
  if ! "$PY" tests/test_e2e.py; then fail=1; fi
else
  echo "   (no ground-truth MC dir; running corpus groups only)"
  if ! "$PY" tests/test_e2e.py --corpus; then fail=1; fi
fi

echo
echo "── [4/4] import + CLI smoke ──"
if ! "$PY" -c "import mcd; assert mcd.__version__; mcd.RuleSet.load()"; then fail=1; fi
if ! "$PY" -m mcd --rules >/dev/null 2>&1; then fail=1; fi
echo "  ✓ import mcd + rule load + CLI --rules"

echo
if [ "$fail" -eq 0 ]; then
  echo "════════ ✓ ALL GATES PASSED ════════"
else
  echo "════════ ✗ SOME GATES FAILED ════════"
fi
exit $fail
