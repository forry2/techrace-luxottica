#!/usr/bin/env bash
# check_all.sh - 3-layer evaluation orchestrator.
# Tech Race - Track 2: WareFlow architecture refactoring.
#
# Runs all 3 layers and produces a final scoring JSON.
#
# USAGE:
#   export TEAM="team-alpha"
#   export REPO_DIR="/path/to/team/repo"
#   export NAMESPACE="team-alpha-ns"          # optional, for M5B only
#   export GOLDEN_MASTER_FILE="/path/to/golden_master.json"
#   ./check_all.sh > scoring-team-alpha.json
#
# REQUIRED: TEAM, REPO_DIR
# OPTIONAL:
#   NAMESPACE           team's OpenShift namespace (M5B PipelineRun check)
#   GOLDEN_MASTER_FILE  path to the pre-captured golden master (default: skip)
#   WATSONX_API_KEY / WATSONX_PROJECT_ID   for Layer 2 (LLM analysis)
#   SKIP_LAYER2         (default: true) true = Layer 1 stands in for the LLM judge and layer2.available
#                       is false; the batch then runs run-layer2.sh afterwards and patches the JSON.
#                       false = call 'bob run' inline (single-team scoring).
#   CONTAINER_RUNTIME   "docker" or "podman" (default: auto-detect)
#   EVAL_PORT           host port for the long-lived eval container
#                       (default: a free port picked at run time)
#   OUTPUT_FILE         if set, write JSON there (default: stdout)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"

# set -a exports every variable the credentials file defines.
if [[ -f "${HOME}/.WATSONX_ENVIRONMENT" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${HOME}/.WATSONX_ENVIRONMENT"
    set +a
fi

TEAM="${TEAM:?'TEAM not set'}"
REPO_DIR="${REPO_DIR:-.}"
NAMESPACE="${NAMESPACE:-}"
GOLDEN_MASTER_FILE="${GOLDEN_MASTER_FILE:-}"
SKIP_LAYER2="${SKIP_LAYER2:-true}"
EVAL_PORT="${EVAL_PORT:-}"   # empty = pick a free port at each run
OUTPUT_FILE="${OUTPUT_FILE:-}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

PASS=0
FAIL=1

# Not named "log": every sourced check_*.sh defines its own log(), and sourcing
# (no subshell, to keep their exports) would overwrite a same-named function here.
elog() { echo "[EVAL] $*" >&2; }

if [[ -z "${CONTAINER_RUNTIME:-}" ]]; then
    command -v podman >/dev/null 2>&1 && CONTAINER_RUNTIME="podman"
    [[ -z "${CONTAINER_RUNTIME:-}" ]] && command -v docker >/dev/null 2>&1 && CONTAINER_RUNTIME="docker"
fi
export REPO_DIR NAMESPACE CONTAINER_RUNTIME

elog "=========================================="
elog " LAYER 1 - Artifact checks"
elog "=========================================="

# Redirect, never pipe, a sourced script: the left side of a pipe runs in a
# subshell and the exports it makes would be lost.
source "$SCRIPT_DIR/check_setup.sh" >&2 || true
source "$SCRIPT_DIR/check_m1.sh" >&2 || true
source "$SCRIPT_DIR/check_m2.sh" >&2 || true
source "$SCRIPT_DIR/check_m3.sh" >&2 || true

# HTTP-dependent checks run against one fresh long-lived container built from the
# team's Containerfile, shared by the golden master, the M4 load test and the M5A.3 check.
_TEAM_TAG="$(printf '%s' "$TEAM" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9_.\n-' '-')"
EVAL_IMAGE_TAG="techrace-track2-eval-${_TEAM_TAG}:latest"
EVAL_CONTAINER_NAME="techrace-track2-eval-${_TEAM_TAG}-$$"
EVAL_BUILD_LOG="$(mktemp "${TMPDIR:-/tmp}/techrace-track2-eval-build-${_TEAM_TAG}-XXXXXX.log")"
if [[ -z "$EVAL_PORT" ]]; then
    EVAL_PORT="$(python3 -I -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
fi
BASE_URL="http://127.0.0.1:${EVAL_PORT}"

cleanup_eval_container() {
    [[ -n "${CONTAINER_RUNTIME:-}" ]] || return 0
    "$CONTAINER_RUNTIME" rm -f "$EVAL_CONTAINER_NAME" >/dev/null 2>&1 || true
    "$CONTAINER_RUNTIME" rmi -f "$EVAL_IMAGE_TAG" >/dev/null 2>&1 || true
}
trap cleanup_eval_container EXIT

M_GOLDEN_MASTER_OK=$FAIL
GOLDEN_MASTER_RAN=false
EVAL_APP_UP=$FAIL

if [[ -z "${CONTAINER_RUNTIME:-}" ]]; then
    elog "no container runtime available - skipping HTTP-dependent checks (M4, M5A.3, golden master)"
elif [[ "${SETUP_CONTAINERFILE:-$FAIL}" -ne 0 ]]; then
    elog "no Containerfile found - skipping HTTP-dependent checks (M4, M5A.3, golden master)"
else
    # Prefer the Containerfile Setup verified (it builds and serves), else the best candidate: the one
    # whose folder holds the app first, then the least nested (same ranking as check_setup.sh).
    CONTAINERFILE="${SETUP_CF_USED:-}"
    if [[ -z "$CONTAINERFILE" ]]; then
        CONTAINERFILE=$(lib_find_containerfiles "$REPO_DIR" | lib_rank_containerfiles "$REPO_DIR" | head -1)
    fi
    BUILD_CONTEXT="$(dirname "$CONTAINERFILE")"
    EVAL_CPORT="$(grep -iE '^[[:space:]]*EXPOSE[[:space:]]' "$CONTAINERFILE" 2>/dev/null | grep -oE '[0-9]+' | head -1)"
    EVAL_CPORT="${EVAL_CPORT:-8080}"
    elog "building long-lived eval image from $CONTAINERFILE ..."
    if "$CONTAINER_RUNTIME" build -t "$EVAL_IMAGE_TAG" -f "$CONTAINERFILE" "$BUILD_CONTEXT" \
        >"$EVAL_BUILD_LOG" 2>&1; then
        "$CONTAINER_RUNTIME" rm -f "$EVAL_CONTAINER_NAME" >/dev/null 2>&1 || true
        RUN_ENV=()
        if [[ -n "${EVAL_WATSONX_API_KEY:-}" && -n "${EVAL_WATSONX_PROJECT_ID:-}" ]]; then
            RUN_ENV=(-e "WATSONX_API_KEY=${EVAL_WATSONX_API_KEY}" -e "WATSONX_PROJECT_ID=${EVAL_WATSONX_PROJECT_ID}"
                     -e "WATSONX_URL=${EVAL_WATSONX_URL:-${WATSONX_URL:-https://us-south.ml.cloud.ibm.com}}")
        else
            # No team credentials: placeholders, so an app that reads them at import time still starts and
            # the golden master and M4 (which do not need the LLM) are not lost. Only 5A.3 then fails.
            RUN_ENV=(-e "WATSONX_API_KEY=eval-placeholder" -e "WATSONX_PROJECT_ID=eval-placeholder"
                     -e "WATSONX_URL=${WATSONX_URL:-https://us-south.ml.cloud.ibm.com}")
        fi
        "$CONTAINER_RUNTIME" run -d --rm --name "$EVAL_CONTAINER_NAME" -p "${EVAL_PORT}:${EVAL_CPORT}" "${RUN_ENV[@]}" "$EVAL_IMAGE_TAG" \
            >/dev/null 2>&1

        HTTP_STATUS="000"
        for _ in $(seq 1 60); do
            HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 \
                "$BASE_URL/warehouses" 2>/dev/null || echo "000")
            [[ "$HTTP_STATUS" == "200" ]] && break
            sleep 1
        done

        if [[ "$HTTP_STATUS" == "200" ]]; then
            EVAL_APP_UP=$PASS
            elog "eval container up at $BASE_URL"

            # Golden master first, while the container is still pristine: the exact-value
            # comparison only holds on a freshly started instance.
            if [[ -n "$GOLDEN_MASTER_FILE" ]]; then
                elog "--- Layer 3 (regression) - golden master verification ---"
                # "source", not "bash": a child's export never reaches this shell,
                # so M_GOLDEN_MASTER_OK would silently stay at FAIL.
                GOLDEN_MASTER_RAN=true
                source "$SCRIPT_DIR/check_golden_master.sh" verify "$BASE_URL" "$GOLDEN_MASTER_FILE" >&2
            else
                elog "GOLDEN_MASTER_FILE not set - skipping regression check"
            fi

            BASE_URL="$BASE_URL" source "$SCRIPT_DIR/check_m4.sh" >&2 || true
            BASE_URL="$BASE_URL" source "$SCRIPT_DIR/check_m5.sh" >&2 || true
        else
            elog "eval container did not become healthy (HTTP $HTTP_STATUS) - skipping M4, M5A.3, golden master"
        fi
    else
        elog "eval image build failed - log in $EVAL_BUILD_LOG"
    fi
fi

if [[ "${EVAL_APP_UP:-$FAIL}" -ne 0 ]]; then
    # M5B does not need the eval container; run it here so its file-based
    # criteria still score when the app cannot start.
    source "$SCRIPT_DIR/check_m5.sh" >&2 || true
fi

export M_GOLDEN_MASTER_OK

elog "=========================================="
elog " LAYER 2 - LLM analysis"
elog "=========================================="

L2_M1_MAP_ACCURATE="false"
L2_M1_TEMPORAL_COUPLING_FOUND="false"
L2_M2_TESTS_MEANINGFUL="false"
L2_M3_UTILS_DECOMPOSED="false"
L2_M4_ROOT_CAUSE_FIXED="false"
L2_NOTES="Layer 2 not run"
L2_AVAILABLE="true"

if [[ "$SKIP_LAYER2" == "true" ]]; then
    elog "SKIP_LAYER2=true - using Layer 1 as a proxy"
    [[ "${M1_ARCH_DOC:-$FAIL}" -eq 0 ]] && L2_M1_MAP_ACCURATE="true"
    [[ "${M1_ARCH_DOC:-$FAIL}" -eq 0 ]] && L2_M1_TEMPORAL_COUPLING_FOUND="true"
    [[ "${M2_TESTS_OK:-$FAIL}" -eq 0 ]] && L2_M2_TESTS_MEANINGFUL="true"
    [[ "${M3_UTILS_STILL_MONOLITHIC:-$PASS}" -ne 0 ]] && L2_M3_UTILS_DECOMPOSED="true"
    [[ "${M4_LOAD:-$FAIL}" -eq 0 ]] && L2_M4_ROOT_CAUSE_FIXED="true"
    L2_NOTES="Layer 2 skipped - values derived from Layer 1"
    L2_AVAILABLE="false"
else
    elog "sending repo context to bob run for qualitative analysis..."
    elog "  workspace: $REPO_DIR"

    FULL_PROMPT="$(lib_layer2_prompt "${M1_STARTER_GRAPH:-}" "${M1_REAL_GRAPH:-}")"

    # Up to 2 attempts inside the helper: a transient bob run failure must not silently zero the
    # 34 Layer 2 points (M1.2/M1.3/M2.3/M3.2/M4.2).
    LLM_JSON="$(lib_layer2_judge "$REPO_DIR" "$FULL_PROMPT" 2 "${BOB_TIMEOUT:-900}")"

    elog "  LLM response JSON: $LLM_JSON"

    L2_M1_MAP_ACCURATE=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('m1_map_accurate',False)).lower())" 2>/dev/null || echo "false")
    L2_M1_TEMPORAL_COUPLING_FOUND=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('m1_temporal_coupling_found',False)).lower())" 2>/dev/null || echo "false")
    L2_M2_TESTS_MEANINGFUL=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('m2_tests_meaningful',False)).lower())" 2>/dev/null || echo "false")
    L2_M3_UTILS_DECOMPOSED=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('m3_utils_decomposed',False)).lower())" 2>/dev/null || echo "false")
    L2_M4_ROOT_CAUSE_FIXED=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('m4_root_cause_fixed',False)).lower())" 2>/dev/null || echo "false")
    L2_NOTES=$(echo "$LLM_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('notes',''))" 2>/dev/null || echo "")
    if [[ "$LLM_JSON" == "{}" ]]; then
        # Judge unavailable: same Layer 1 proxy as SKIP_LAYER2, but flagged in the notes
        # instead of silently zeroing the LLM-judged criteria.
        [[ "${M1_ARCH_DOC:-$FAIL}" -eq 0 ]] && L2_M1_MAP_ACCURATE="true"
        [[ "${M1_ARCH_DOC:-$FAIL}" -eq 0 ]] && L2_M1_TEMPORAL_COUPLING_FOUND="true"
        [[ "${M2_TESTS_OK:-$FAIL}" -eq 0 ]] && L2_M2_TESTS_MEANINGFUL="true"
        [[ "${M3_UTILS_STILL_MONOLITHIC:-$PASS}" -ne 0 ]] && L2_M3_UTILS_DECOMPOSED="true"
        [[ "${M4_LOAD:-$FAIL}" -eq 0 ]] && L2_M4_ROOT_CAUSE_FIXED="true"
        L2_NOTES="LAYER 2 NON DISPONIBILE (bob run fallito 2 volte): criteri giudicati dall'LLM derivati dal Layer 1 - rivedere a mano"
        L2_AVAILABLE="false"
        elog "!! LAYER 2 NON DISPONIBILE: bob run non ha dato un verdetto valido - i 34 punti dei criteri giudicati dall'LLM"
        elog "!! (1.2, 1.3, 2.3, 3.2, 4.2) sono derivati dal Layer 1: PUNTEGGIO PROVVISORIO, da rivedere a mano"
    fi
fi

pts() { [[ "${1:-1}" -eq 0 ]] && echo "$2" || echo 0; }
b()   { [[ "${1:-1}" -eq 0 ]] && echo "true" || echo "false"; }
lb()  { [[ "$1" == "true" ]] && echo 0 || echo 1; }  # L2 "true"/"false" string -> 0/1

# Setup: 2+2+1 = 5
SETUP_SCORE=$(( \
    $(pts "${SETUP_CONTAINERFILE:-$FAIL}" 2) + \
    $(pts "${SETUP_BUILD:-$FAIL}" 2) + \
    $(pts "${SETUP_RUN:-$FAIL}" 1) \
))

# M1: doc 8 + L2 accuracy 10 + L2 temporal coupling 7 = 25
M1_SCORE=$(( \
    $(pts "${M1_ARCH_DOC:-$FAIL}" 8) + \
    $(pts "$(lb "$L2_M1_MAP_ACCURATE")" 10) + \
    $(pts "$(lb "$L2_M1_TEMPORAL_COUPLING_FOUND")" 7) \
))
M1_BONUS=0
[[ "${M1_BONUS_DIAGRAM:-$FAIL}" -eq 0 ]] && M1_BONUS=5

# M2: coverage 10 + pytest 8 + L2 meaningful 7 = 25
M2_SCORE=$(( \
    $(pts "${M2_COVERAGE:-$FAIL}" 10) + \
    $(pts "${M2_TESTS_OK:-$FAIL}" 8) + \
    $(pts "$(lb "$L2_M2_TESTS_MEANINGFUL")" 7) \
))
M2_BONUS=0
[[ "${M2_BONUS_CONCURRENCY_TEST:-$FAIL}" -eq 0 ]] && M2_BONUS=5

# M3: no cycles 6 + L2 utils decomposed 5 + dead code removed 4 = 15
M3_SCORE=$(( \
    $(pts "${M3_NO_CYCLES:-$FAIL}" 6) + \
    $(pts "$(lb "$L2_M3_UTILS_DECOMPOSED")" 5) + \
    $(pts "${M3_DEAD_CODE_REMOVED:-$FAIL}" 4) \
))
M3_BONUS=0
[[ "${M3_BONUS_TESTS_OK:-$FAIL}" -eq 0 ]] && M3_BONUS=5

# M4: load 10 + L2 root cause 5 = 15
M4_SCORE=$(( \
    $(pts "${M4_LOAD:-$FAIL}" 10) + \
    $(pts "$(lb "$L2_M4_ROOT_CAUSE_FIXED")" 5) \
))
M4_BONUS=0
[[ "${M4_BONUS_REGRESSION_TEST:-$FAIL}" -eq 0 ]] && M4_BONUS=5

# M5A: 2+3+5 = 10; M5B: 2+5+1+2 = 10
M5A_SCORE=$(( \
    $(pts "${M5A_DEP:-$FAIL}" 2) + \
    $(pts "${M5A_MODEL_CONFIG:-$FAIL}" 3) + \
    $(pts "${M5A_ENDPOINT:-$FAIL}" 5) \
))
M5B_SCORE=$(( \
    $(pts "${M5B_YAML:-$FAIL}" 2) + \
    $(pts "${M5B_GATE_LOGIC:-$FAIL}" 5) + \
    $(pts "${M5B_RUN_SUCCEEDED:-$FAIL}" 1) + \
    $(pts "${M5B_EMAIL:-$FAIL}" 2) \
))
M5_SCORE=$(( M5A_SCORE + M5B_SCORE ))
M5_BONUS=0
[[ "${M5_BONUS_BOTH:-$FAIL}" -eq 0 ]] && M5_BONUS=5

TOTAL=$(( SETUP_SCORE + M1_SCORE + M1_BONUS + M2_SCORE + M2_BONUS + M3_SCORE + M3_BONUS + \
          M4_SCORE + M4_BONUS + M5_SCORE + M5_BONUS ))

if   [[ "$TOTAL" -ge 105 ]]; then TIER="Platinum"
elif [[ "$TOTAL" -ge 80  ]]; then TIER="Gold"
elif [[ "$TOTAL" -ge 55  ]]; then TIER="Silver"
else                                TIER="Bronze"
fi

export JSON_TEAM="$TEAM" JSON_NAMESPACE="$NAMESPACE" JSON_TIMESTAMP="$TIMESTAMP" JSON_L2_NOTES="$L2_NOTES"

JSON=$(python3 - <<PYEOF
import json, os

result = {
    "team": os.environ["JSON_TEAM"],
    "namespace": os.environ["JSON_NAMESPACE"],
    "timestamp": os.environ["JSON_TIMESTAMP"],
    "layer1": {
        "setup_containerfile": json.loads("$(b "${SETUP_CONTAINERFILE:-$FAIL}")"),
        "setup_build": json.loads("$(b "${SETUP_BUILD:-$FAIL}")"),
        "setup_run": json.loads("$(b "${SETUP_RUN:-$FAIL}")"),
        "m1_arch_doc": json.loads("$(b "${M1_ARCH_DOC:-$FAIL}")"),
        "m1_bonus_diagram": json.loads("$(b "${M1_BONUS_DIAGRAM:-$FAIL}")"),
        "m2_coverage": json.loads("$(b "${M2_COVERAGE:-$FAIL}")"),
        "m2_tests_pass": json.loads("$(b "${M2_TESTS_OK:-$FAIL}")"),
        "m2_coverage_current": $M2_COVERAGE_CURRENT,
        "m2_bonus_concurrency_test": json.loads("$(b "${M2_BONUS_CONCURRENCY_TEST:-$FAIL}")"),
        "m3_no_cycles": json.loads("$(b "${M3_NO_CYCLES:-$FAIL}")"),
        "m3_dead_code_removed": json.loads("$(b "${M3_DEAD_CODE_REMOVED:-$FAIL}")"),
        "m3_bonus_tests_pass": json.loads("$(b "${M3_BONUS_TESTS_OK:-$FAIL}")"),
        "m4_load": json.loads("$(b "${M4_LOAD:-$FAIL}")"),
        "m4_bonus_regression_test": json.loads("$(b "${M4_BONUS_REGRESSION_TEST:-$FAIL}")"),
        "m5a_dep": json.loads("$(b "${M5A_DEP:-$FAIL}")"),
        "m5a_model_config": json.loads("$(b "${M5A_MODEL_CONFIG:-$FAIL}")"),
        "m5a_no_hardcoded_key": json.loads("$(b "${M5A_NO_HARDCODED_KEY:-$FAIL}")"),
        "m5a_endpoint": json.loads("$(b "${M5A_ENDPOINT:-$FAIL}")"),
        "m5b_yaml": json.loads("$(b "${M5B_YAML:-$FAIL}")"),
        "m5b_gate_logic": json.loads("$(b "${M5B_GATE_LOGIC:-$FAIL}")"),
        "m5b_run_succeeded": json.loads("$(b "${M5B_RUN_SUCCEEDED:-$FAIL}")"),
        "m5b_email": json.loads("$(b "${M5B_EMAIL:-$FAIL}")"),
        "golden_master_ok": json.loads("$(b "${M_GOLDEN_MASTER_OK:-$FAIL}")"),
        "golden_master_status": "$( [[ "$GOLDEN_MASTER_RAN" != "true" ]] && echo not_run || { [[ "${M_GOLDEN_MASTER_OK:-$FAIL}" -eq 0 ]] && echo pass || echo fail; } )"
    },
    "layer2": {
        "m1_map_accurate": json.loads("$L2_M1_MAP_ACCURATE"),
        "m1_temporal_coupling_found": json.loads("$L2_M1_TEMPORAL_COUPLING_FOUND"),
        "m2_tests_meaningful": json.loads("$L2_M2_TESTS_MEANINGFUL"),
        "m3_utils_decomposed": json.loads("$L2_M3_UTILS_DECOMPOSED"),
        "m4_root_cause_fixed": json.loads("$L2_M4_ROOT_CAUSE_FIXED"),
        "available": json.loads("$L2_AVAILABLE"),
        "notes": os.environ["JSON_L2_NOTES"]
    },
    "milestones": {
        "setup": {"score": $SETUP_SCORE, "bonus": 0, "max": 5},
        "m1": {"score": $M1_SCORE, "bonus": $M1_BONUS, "max": 30},
        "m2": {"score": $M2_SCORE, "bonus": $M2_BONUS, "max": 30},
        "m3": {"score": $M3_SCORE, "bonus": $M3_BONUS, "max": 20},
        "m4": {"score": $M4_SCORE, "bonus": $M4_BONUS, "max": 20},
        "m5a": {"score": $M5A_SCORE, "bonus": 0, "max": 10},
        "m5b": {"score": $M5B_SCORE, "bonus": 0, "max": 10},
        "m5_bonus": $M5_BONUS
    },
    "total": $TOTAL,
    "tier": "$TIER"
}

print(json.dumps(result, indent=2, ensure_ascii=False))
PYEOF
)

if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$JSON" > "$OUTPUT_FILE"
    elog "JSON saved to: $OUTPUT_FILE"
else
    echo "$JSON"
fi

elog ""
elog "=========================================="
elog " FINAL SCORE: $TOTAL points - $TIER"
elog "=========================================="
