#!/usr/bin/env bash
# check_m2.sh - Milestone 2: Safety net - characterization tests.
# Layer 1 - artifact check. Whether the tests are "meaningful" (not trivially
# empty assertions) is judged by Layer 2 (LLM) in check_all.sh.
#
# INPUT (env vars):
#   REPO_DIR            Team repo root (default .)
#   BASELINE_COVERAGE   Coverage % of the unmodified starter app (default 8 -
#                        matches challenge-starter/tests/test_basic.py as shipped)
#   PYTHON_BIN          Python interpreter to use (default: python3)
# OUTPUT: M2_COVERAGE, M2_TESTS_OK, M2_BONUS_CONCURRENCY_TEST (0=PASS, 1=FAIL)
#         M2_COVERAGE_CURRENT, M2_COVERAGE_DELTA (numeric, for reporting)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"

REPO_DIR="${REPO_DIR:-.}"
BASELINE_COVERAGE="${BASELINE_COVERAGE:-8}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIRED_DELTA=30

PASS=0
FAIL=1
M2_COVERAGE=$FAIL
M2_TESTS_OK=$FAIL
M2_BONUS_CONCURRENCY_TEST=$FAIL
M2_COVERAGE_CURRENT=0
M2_COVERAGE_DELTA=0

log()  { echo "[M2] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

# The package may sit deeper after refactoring (e.g. wareflow/app/) or be renamed: same lookup as M1/M3.
APP_DIR_FOUND="$(lib_app_dir "$REPO_DIR")"
APP_ROOT=""
if [[ -n "$APP_DIR_FOUND" ]]; then
    APP_ROOT="$(dirname "$APP_DIR_FOUND")"
fi
if [[ -z "$APP_ROOT" ]]; then
    fail "no 'app' package found under $REPO_DIR - cannot run tests/coverage"
    export M2_COVERAGE M2_TESTS_OK M2_BONUS_CONCURRENCY_TEST M2_COVERAGE_CURRENT M2_COVERAGE_DELTA
    # check_all.sh sources this script, so "exit" would end check_all.sh itself (no JSON
    # output). "return" leaves only this script; the "exit" fallback is for direct runs.
    return 0 2>/dev/null || exit 0
fi
log "app root: $APP_ROOT"

# Best-effort dependency install; failures are ignored.
for REQ in "$APP_ROOT/requirements.txt" "$APP_ROOT/requirements-dev.txt" \
           "$REPO_DIR/requirements.txt" "$REPO_DIR/requirements-dev.txt"; do
    [[ -f "$REQ" ]] && "$PYTHON_BIN" -m pip install -q -r "$REQ" >/dev/null 2>&1 || true
done

# So that 'from app.xxx import ...' resolves.
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

log "--- 2.2 pytest passes ---"
if ( cd "$APP_ROOT" && PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m pytest -q ) \
    >${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m2-pytest.log 2>&1; then
    M2_TESTS_OK=$PASS
    pass "pytest exit 0"
else
    fail "pytest failed - log in ${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m2-pytest.log"
fi

log "--- 2.1 coverage increased by >= ${REQUIRED_DELTA} points over baseline (${BASELINE_COVERAGE}%) ---"
COV_JSON="${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m2-coverage.json"
if ( cd "$APP_ROOT" && PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" -m coverage run -m pytest -q ) >${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m2-coverage-run.log 2>&1; then
    ( cd "$APP_ROOT" && "$PYTHON_BIN" -m coverage json -o "$COV_JSON" ) >/dev/null 2>&1 || true
fi

if [[ -f "$COV_JSON" ]]; then
    M2_COVERAGE_CURRENT=$("$PYTHON_BIN" -c "
import json
with open('$COV_JSON') as f:
    d = json.load(f)
print(round(d['totals']['percent_covered'], 1))
" 2>/dev/null || echo "0")
else
    M2_COVERAGE_CURRENT=0
fi

M2_COVERAGE_DELTA=$("$PYTHON_BIN" -c "print(round($M2_COVERAGE_CURRENT - $BASELINE_COVERAGE, 1))" 2>/dev/null || echo "0")

if "$PYTHON_BIN" -c "exit(0 if $M2_COVERAGE_DELTA >= $REQUIRED_DELTA else 1)" 2>/dev/null; then
    M2_COVERAGE=$PASS
    pass "coverage ${M2_COVERAGE_CURRENT}% (+${M2_COVERAGE_DELTA} vs baseline ${BASELINE_COVERAGE}%)"
else
    fail "coverage ${M2_COVERAGE_CURRENT}% (+${M2_COVERAGE_DELTA} vs baseline ${BASELINE_COVERAGE}%, need +${REQUIRED_DELTA})"
fi

log "--- 2.BONUS test covers concurrent requests on stock ---"
# Any test_*.py / *_test.py in the repo (tests may live in tests/, test/ or next to the code).
if lib_test_files_mention_stock_and_concurrency "$REPO_DIR"; then
    M2_BONUS_CONCURRENCY_TEST=$PASS
    pass "found a test file referencing both stock and concurrency"
else
    fail "no test found exercising concurrent requests on stock"
fi

log ""
log "=== M2 SUMMARY ==="
log "  2.1 coverage +${REQUIRED_DELTA}pt : $([ $M2_COVERAGE -eq 0 ] && echo PASS || echo FAIL) (current: ${M2_COVERAGE_CURRENT}%)"
log "  2.2 pytest passes      : $([ $M2_TESTS_OK -eq 0 ] && echo PASS || echo FAIL)"
log "  BONUS concurrency test : $([ $M2_BONUS_CONCURRENCY_TEST -eq 0 ] && echo PASS || echo FAIL)"
log "  (2.3 test quality is judged by Layer 2)"

export M2_COVERAGE M2_TESTS_OK M2_BONUS_CONCURRENCY_TEST M2_COVERAGE_CURRENT M2_COVERAGE_DELTA
