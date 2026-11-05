#!/usr/bin/env bash
# check_golden_master.sh - Layer 3 (regression): behavior preservation.
#
# Runs a fixed sequence of requests against a freshly started app instance
# (seed data intact, nothing posted yet) and either saves the responses as a
# golden master (capture mode, run once by the organizers on the original app)
# or compares them against a captured one (verify mode, run on each team's app).
# No milestone touches these flows, so any mismatch is a regression.
#
# Both modes need a fresh instance; this script does not restart the app.
# check_all.sh runs it right after starting its eval container, before
# anything else touches it.
#
# Usage:
#   check_golden_master.sh capture <BASE_URL> [OUTFILE]   (default OUTFILE: golden_master.json)
#   check_golden_master.sh verify  <BASE_URL> [GOLDEN_FILE]
#
# OUTPUT (verify mode, exported): M_GOLDEN_MASTER_OK (0=PASS, 1=FAIL)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
BASE_URL="${2:-http://127.0.0.1:8080}"
FILE_ARG="${3:-golden_master.json}"

PASS=0
FAIL=1
M_GOLDEN_MASTER_OK=$FAIL

log()  { echo "[GOLDEN] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

# No "exit": check_all.sh sources this script, and an exit would end the calling
# shell. Bad usage just skips the run.
if [[ "$MODE" != "capture" && "$MODE" != "verify" ]]; then
    echo "usage: check_golden_master.sh capture|verify <BASE_URL> [FILE]" >&2
else
    python3 "$SCRIPT_DIR/golden_master_runner.py" "$MODE" "$BASE_URL" "$FILE_ARG"
    RUNNER_EXIT=$?

    if [[ "$MODE" == "capture" ]]; then
        if [[ $RUNNER_EXIT -eq 0 ]]; then
            pass "golden master captured to $FILE_ARG"
        else
            fail "capture failed - see output above"
        fi
    else
        if [[ $RUNNER_EXIT -eq 0 ]]; then
            M_GOLDEN_MASTER_OK=$PASS
            pass "all flows match the golden master - behavior preserved"
        else
            fail "one or more flows diverge from the golden master - see diff above"
        fi
        export M_GOLDEN_MASTER_OK
    fi
fi
