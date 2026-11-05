#!/usr/bin/env bash
# check_m3.sh - Milestone 3: Break the couplings.
# Layer 1 - artifact check. Whether utils.py was meaningfully decomposed by
# responsibility (not just renamed) is judged by Layer 2 in check_all.sh -
# this script only checks whether a monolithic "utils.py" still exists.
#
# INPUT (env vars):
#   REPO_DIR    Team repo root (default .)
#   PYTHON_BIN  Python interpreter to use (default: python3)
# OUTPUT: M3_NO_CYCLES, M3_DEAD_CODE_REMOVED, M3_BONUS_TESTS_OK (0=PASS, 1=FAIL)
#         M3_UTILS_STILL_MONOLITHIC (0=still one dumping-ground file, 1=not found as-is)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"
REPO_DIR="${REPO_DIR:-.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

PASS=0
FAIL=1
M3_NO_CYCLES=$FAIL
M3_DEAD_CODE_REMOVED=$FAIL
M3_BONUS_TESTS_OK=$FAIL
M3_UTILS_STILL_MONOLITHIC=$FAIL

log()  { echo "[M3] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

# The package may sit deeper after refactoring (e.g. wareflow/app/) or be renamed: same lookup as M1/M2.
APP_DIR="$(lib_app_dir "$REPO_DIR")"
APP_PKG_NAME=""
[[ -n "$APP_DIR" ]] && APP_PKG_NAME="$(basename "$APP_DIR")"

log "--- 3.1 no residual circular imports ---"
if [[ -z "$APP_DIR" ]]; then
    fail "no app package found under $REPO_DIR"
else
    CYCLES_OUTPUT=$("$PYTHON_BIN" "$SCRIPT_DIR/detect_cycles.py" "$APP_DIR" "$APP_PKG_NAME" 2>&1)
    CYCLES_EXIT=$?
    if [[ $CYCLES_EXIT -eq 0 ]]; then
        M3_NO_CYCLES=$PASS
        pass "$CYCLES_OUTPUT"
    else
        fail "cycle(s) found:"
        echo "$CYCLES_OUTPUT" | while IFS= read -r line; do log "    $line"; done
    fi
fi

log "--- 3.3 dead code (legacy_fax) removed ---"
APP_ROOT=$(dirname "${APP_DIR:-$REPO_DIR/app}")
LEGACY_FILE=$(find "$REPO_DIR" -iname "legacy_fax.py" -not -path "*/.git/*" 2>/dev/null | head -1 || echo "")
# Only a real reference counts (import, attribute, name, dynamic import): not a comment, a docstring or a
# path in an assert. See lib_count_module_references.
LEGACY_REFS=$(lib_count_module_references "$REPO_DIR" legacy_fax)
LEGACY_REFS="${LEGACY_REFS:-0}"
if [[ -z "$LEGACY_FILE" ]] && [[ "$LEGACY_REFS" -eq 0 ]]; then
    M3_DEAD_CODE_REMOVED=$PASS
    pass "legacy_fax.py absent, no residual references"
else
    fail "legacy_fax.py present (${LEGACY_FILE:-none}) or still referenced ($LEGACY_REFS files)"
fi

log "--- 3.2 (context for Layer 2) utils.py dumping-ground check ---"
UTILS_FILE=$(find "$REPO_DIR" -iname "utils.py" -not -path "*/.git/*" 2>/dev/null | head -1 || echo "")
if [[ -n "$UTILS_FILE" ]]; then
    RESP_COUNT=$(grep -cE '^def ' "$UTILS_FILE" 2>/dev/null || true); RESP_COUNT="${RESP_COUNT:-0}"
    log "  utils.py still exists ($UTILS_FILE, $RESP_COUNT top-level functions) - Layer 2 will judge whether responsibilities were actually split out"
    M3_UTILS_STILL_MONOLITHIC=$PASS
    export M3_UTILS_CONTENT="$(cat "$UTILS_FILE" 2>/dev/null || echo "")"
else
    log "  no utils.py found - likely decomposed, Layer 2 will confirm against the real module list"
    export M3_UTILS_CONTENT=""
fi

log "--- 3.BONUS M2 characterization tests still pass after refactoring ---"
if [[ -n "$APP_DIR" ]]; then
    # Same dependency install and PYTHONPATH as check_m2.sh.
    for REQ in "$APP_ROOT/requirements.txt" "$APP_ROOT/requirements-dev.txt" \
               "$REPO_DIR/requirements.txt" "$REPO_DIR/requirements-dev.txt"; do
        [[ -f "$REQ" ]] && "$PYTHON_BIN" -m pip install -q -r "$REQ" >/dev/null 2>&1 || true
    done
    if ( cd "$APP_ROOT" && PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$PYTHON_BIN" -m pytest -q ) >${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m3-pytest.log 2>&1; then
        M3_BONUS_TESTS_OK=$PASS
        pass "pytest exit 0 - behavior preserved"
    else
        fail "pytest failed - log in ${TMPDIR:-/tmp}/techrace-track2-${TEAM:-local}-m3-pytest.log"
    fi
else
    fail "SKIP: no app package to test"
fi

log ""
log "=== M3 SUMMARY ==="
log "  3.1 no circular imports : $([ $M3_NO_CYCLES -eq 0 ] && echo PASS || echo FAIL)"
log "  3.3 dead code removed   : $([ $M3_DEAD_CODE_REMOVED -eq 0 ] && echo PASS || echo FAIL)"
log "  BONUS tests still pass  : $([ $M3_BONUS_TESTS_OK -eq 0 ] && echo PASS || echo FAIL)"
log "  (3.2 utils.py decomposition quality is judged by Layer 2)"

export M3_NO_CYCLES M3_DEAD_CODE_REMOVED M3_BONUS_TESTS_OK M3_UTILS_STILL_MONOLITHIC
