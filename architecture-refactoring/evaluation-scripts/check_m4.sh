#!/usr/bin/env bash
# check_m4.sh - Milestone 4: The stock count bug.
# Layer 1 - functional check against a RUNNING instance of the app (local or
# containerized - the caller is responsible for starting it and passing
# BASE_URL). Whether the fix addresses the root cause (synchronization)
# rather than a surface patch (e.g. random retry) is judged by Layer 2.
#
# INPUT (env vars):
#   BASE_URL       Base URL of the running app (default: http://127.0.0.1:8080)
#   REPO_DIR       Team repo root, used only for the bonus regression-test check (default .)
#   TEST_SKU       SKU to hammer concurrently (default: PALLET-BOX - seeded with 500 units)
#   CONCURRENCY    Number of concurrent confirm requests (default: 50)
# OUTPUT: M4_LOAD, M4_BONUS_REGRESSION_TEST (0=PASS, 1=FAIL)
#         M4_STOCK_BEFORE, M4_STOCK_AFTER, M4_STOCK_EXPECTED (numeric, for reporting)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
REPO_DIR="${REPO_DIR:-.}"
TEST_SKU="${TEST_SKU:-PALLET-BOX}"
CONCURRENCY="${CONCURRENCY:-50}"

PASS=0
FAIL=1
M4_LOAD=$FAIL
M4_BONUS_REGRESSION_TEST=$FAIL
M4_STOCK_BEFORE=0
M4_STOCK_AFTER=0
M4_STOCK_EXPECTED=0

log()  { echo "[M4] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

log "--- 4.1 ${CONCURRENCY} concurrent stock decrements on $TEST_SKU, exact final result ---"

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "$BASE_URL/warehouses" 2>/dev/null || echo "000")
if [[ "$HEALTH" != "200" ]]; then
    fail "app not reachable at $BASE_URL (GET /warehouses -> HTTP $HEALTH)"
    export M4_LOAD M4_BONUS_REGRESSION_TEST M4_STOCK_BEFORE M4_STOCK_AFTER M4_STOCK_EXPECTED
    # Sourced by check_all.sh: no "exit" (see check_m2.sh).
    return 0 2>/dev/null || exit 0
fi

# Top up the SKU first so the test is self-contained regardless of what ran before it.
curl -sf --connect-timeout 5 --max-time 10 -X POST "$BASE_URL/stock/$TEST_SKU/restock" \
    -H "Content-Type: application/json" -d "{\"quantity\": $CONCURRENCY}" >/dev/null 2>&1 || true

M4_STOCK_BEFORE=$(curl -sf --connect-timeout 5 --max-time 10 "$BASE_URL/stock/$TEST_SKU" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('quantity', 0))" 2>/dev/null || echo 0)
log "  stock before: $M4_STOCK_BEFORE"

log "  creating $CONCURRENCY draft orders (qty=1 each)..."
TMPDIR_M4=$(mktemp -d)
for i in $(seq 1 "$CONCURRENCY"); do
    curl -sf --connect-timeout 5 --max-time 10 -X POST "$BASE_URL/orders" \
        -H "Content-Type: application/json" \
        -d "{\"customer_name\":\"m4-load-$i\",\"lines\":[{\"sku\":\"$TEST_SKU\",\"quantity\":1}]}" \
        2>/dev/null > "$TMPDIR_M4/create_$i.json" &
done
wait

ORDER_IDS=()
for i in $(seq 1 "$CONCURRENCY"); do
    OID=$(python3 -c "
import json
try:
    with open('$TMPDIR_M4/create_$i.json') as f:
        print(json.load(f).get('id', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
    [[ -n "$OID" ]] && ORDER_IDS+=("$OID")
done
log "  orders created: ${#ORDER_IDS[@]}/${CONCURRENCY}"

if [[ "${#ORDER_IDS[@]}" -lt "$CONCURRENCY" ]]; then
    fail "could not create all $CONCURRENCY draft orders - got ${#ORDER_IDS[@]}"
    rm -rf "$TMPDIR_M4"
    export M4_LOAD M4_BONUS_REGRESSION_TEST M4_STOCK_BEFORE M4_STOCK_AFTER M4_STOCK_EXPECTED
    return 0 2>/dev/null || exit 0
fi

log "  confirming all $CONCURRENCY orders concurrently..."
for OID in "${ORDER_IDS[@]}"; do
    curl -s -o /dev/null \
        --connect-timeout 10 --max-time 30 \
        -X POST "$BASE_URL/orders/$OID/confirm" >/dev/null 2>&1 &
done
wait
rm -rf "$TMPDIR_M4"

M4_STOCK_EXPECTED=$(( M4_STOCK_BEFORE - CONCURRENCY ))
M4_STOCK_AFTER=$(curl -sf --connect-timeout 5 --max-time 10 "$BASE_URL/stock/$TEST_SKU" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('quantity', 0))" 2>/dev/null || echo 0)

log "  stock after: $M4_STOCK_AFTER (expected: $M4_STOCK_EXPECTED)"
if [[ "$M4_STOCK_AFTER" -eq "$M4_STOCK_EXPECTED" ]]; then
    M4_LOAD=$PASS
    pass "final stock exact: $M4_STOCK_AFTER"
else
    LOST=$(( M4_STOCK_AFTER - M4_STOCK_EXPECTED ))
    fail "lost update(s) detected: final stock $M4_STOCK_AFTER, expected $M4_STOCK_EXPECTED (drift: $LOST)"
fi

log "--- 4.BONUS regression test specific to this bug ---"
if lib_test_files_mention_stock_and_concurrency "$REPO_DIR"; then
    M4_BONUS_REGRESSION_TEST=$PASS
    pass "found a test file exercising concurrent stock updates"
else
    fail "no regression test found for the concurrency bug"
fi

log ""
log "=== M4 SUMMARY ==="
log "  4.1 ${CONCURRENCY} concurrent confirms, exact stock : $([ $M4_LOAD -eq 0 ] && echo PASS || echo FAIL)"
log "  BONUS regression test                  : $([ $M4_BONUS_REGRESSION_TEST -eq 0 ] && echo PASS || echo FAIL)"
log "  (4.2 root-cause vs surface patch is judged by Layer 2)"

export M4_LOAD M4_BONUS_REGRESSION_TEST M4_STOCK_BEFORE M4_STOCK_AFTER M4_STOCK_EXPECTED
