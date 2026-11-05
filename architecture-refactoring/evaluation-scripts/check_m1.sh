#!/usr/bin/env bash
# check_m1.sh - Milestone 1: Map the real architecture.
# Layer 1 - artifact check. Map accuracy and the shipping/warehouse temporal
# coupling are judged by Layer 2 (LLM) in check_all.sh; this script only checks
# that the doc exists and extracts the real dependency graph for the judge.
#
# INPUT (env vars): REPO_DIR (default .)
# OUTPUT: M1_ARCH_DOC, M1_BONUS_DIAGRAM (0=PASS, 1=FAIL), M1_REAL_GRAPH (text)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"
REPO_DIR="${REPO_DIR:-.}"

PASS=0
FAIL=1
M1_ARCH_DOC=$FAIL
M1_BONUS_DIAGRAM=$FAIL

log()  { echo "[M1] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

log "--- 1.1 ARCHITECTURE.md present ---"
ARCH_DOC=$(find "$REPO_DIR" -iname "ARCHITECTURE.md" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null \
    | awk '{ p = $0; n = gsub("/", "/", p); print n "\t" $0 }' | sort -t $'\t' -k1,1n -k2,2 | cut -f2- | head -1 || echo "")
if [[ -n "$ARCH_DOC" ]]; then
    M1_ARCH_DOC=$PASS
    pass "found: $ARCH_DOC"
else
    fail "no ARCHITECTURE.md found in $REPO_DIR"
fi

log "--- 1.BONUS diagram in architecture doc ---"
if [[ -n "$ARCH_DOC" ]] && grep -qE '```mermaid|```dot|```plantuml|!\[.*\]\(.*\.(png|svg|jpg|jpeg)\)' "$ARCH_DOC" 2>/dev/null; then
    M1_BONUS_DIAGRAM=$PASS
    pass "diagram block or embedded image found in $ARCH_DOC"
else
    fail "no mermaid/dot/plantuml block or embedded image found"
fi

log "--- Extracting real dependency graph (app package) ---"
APP_DIR="$(lib_app_dir "$REPO_DIR")"
if [[ -n "$APP_DIR" ]]; then
    M1_REAL_GRAPH=$(python3 -I "$SCRIPT_DIR/detect_cycles.py" "$APP_DIR" "$(basename "$APP_DIR")" --graph 2>/dev/null || echo "")
    log "  graph extracted ($(echo "$M1_REAL_GRAPH" | wc -l) modules)"
else
    M1_REAL_GRAPH=""
    fail "no 'app' package found under $REPO_DIR - cannot extract dependency graph"
fi

# Graph of the starter app: teams map the code before touching it, so an
# ARCHITECTURE.md faithful to the starter is still correct after M3 changes the
# modules. The judge gets both graphs and accepts a map faithful to either.
M1_STARTER_GRAPH=""
STARTER_APP="$SCRIPT_DIR/../challenge-starter/app"
if [[ -d "$STARTER_APP" ]]; then
    M1_STARTER_GRAPH=$(python3 "$SCRIPT_DIR/detect_cycles.py" "$STARTER_APP" "app" --graph 2>/dev/null || echo "")
    log "  starter graph extracted ($(echo "$M1_STARTER_GRAPH" | wc -l) modules)"
fi

log ""
log "=== M1 SUMMARY ==="
log "  1.1 ARCHITECTURE.md : $([ $M1_ARCH_DOC -eq 0 ] && echo PASS || echo FAIL)"
log "  BONUS diagram        : $([ $M1_BONUS_DIAGRAM -eq 0 ] && echo PASS || echo FAIL)"
log "  (1.2 map accuracy and 1.3 temporal coupling are judged by Layer 2)"

export M1_ARCH_DOC M1_BONUS_DIAGRAM M1_REAL_GRAPH M1_STARTER_GRAPH
