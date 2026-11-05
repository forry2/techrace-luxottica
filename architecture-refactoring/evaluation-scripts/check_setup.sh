#!/usr/bin/env bash
# check_setup.sh - Setup: containerize and verify the starter app.
# Layer 1 - artifact check.
#
# INPUT (env vars):
#   REPO_DIR               team repo root (default .)
#   SETUP_PORT             host port for the probe (default: a free port picked at run time,
#                          so two teams scored in parallel never fight over the same port)
#   SETUP_MAX_CANDIDATES   how many Containerfiles to try at most (default 6)
#   SETUP_STARTUP_TIMEOUT  seconds to wait for the app to answer (default 60)
#   SETUP_RUN_ENV          space-separated NAME=value variables given to the test container
#                          (default: placeholder WATSONX_API_KEY/WATSONX_PROJECT_ID/WATSONX_URL, so
#                          an app that reads them at startup can still come up)
#   CONTAINER_RUNTIME      docker | podman (default: autodetect)
# OUTPUT: SETUP_CONTAINERFILE, SETUP_BUILD, SETUP_RUN (0=PASS, 1=FAIL)
#         SETUP_CF_USED  the Containerfile that built and served (reused by check_all.sh)
#
# Generic by design:
#  - any file named Containerfile*/Dockerfile*/*.Containerfile/*.Dockerfile counts, in any folder;
#  - the ones whose folder holds the app (main.py, requirements.txt, an app/ package) come first,
#    then the least nested; Setup passes if at least one builds and serves, so a stray secondary
#    Containerfile (docs example, other tool) cannot cost points;
#  - the container port comes from EXPOSE (default 8080);
#  - the app counts as alive on HTTP 200 + valid JSON from GET /warehouses.
#
# No "exit" and no "trap ... EXIT": check_all.sh sources this script, so an exit would end
# check_all.sh and a trap would be replaced by its own. Cleanup is explicit instead.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"

REPO_DIR="${REPO_DIR:-.}"
SETUP_PORT="${SETUP_PORT:-}"
SETUP_MAX_CANDIDATES="${SETUP_MAX_CANDIDATES:-6}"
SETUP_STARTUP_TIMEOUT="${SETUP_STARTUP_TIMEOUT:-60}"
SETUP_RUN_ENV="${SETUP_RUN_ENV-WATSONX_API_KEY=setup-check WATSONX_PROJECT_ID=setup-check WATSONX_URL=https://us-south.ml.cloud.ibm.com}"
_SETUP_TEAM_TAG="$(printf '%s' "${TEAM:-local}" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9_.\n-' '-')"
IMAGE_TAG="techrace-track2-setup-check-${_SETUP_TEAM_TAG}:tmp"

if [[ -z "${CONTAINER_RUNTIME:-}" ]]; then
    command -v podman >/dev/null 2>&1 && CONTAINER_RUNTIME="podman"
    [[ -z "${CONTAINER_RUNTIME:-}" ]] && command -v docker >/dev/null 2>&1 && CONTAINER_RUNTIME="docker"
fi

PASS=0
FAIL=1
SETUP_CONTAINERFILE=$FAIL
SETUP_BUILD=$FAIL
SETUP_RUN=$FAIL
SETUP_CF_USED=""

log()  { echo "[SETUP] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

SETUP_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/techrace-track2-setup-${_SETUP_TEAM_TAG}-XXXXXX")"

_setup_free_port() {
    python3 -I -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

_setup_try_candidate() {
    local CF="$1" IDX="$2" CTX NAME CPORT HPORT BUILD_ARGS=() code body deadline
    CTX="$(dirname "$CF")"
    NAME="techrace-track2-setup-check-${_SETUP_TEAM_TAG}-$$-${IDX}"
    log "  candidate #${IDX}: $CF"

    [[ "$CONTAINER_RUNTIME" == "podman" ]] && BUILD_ARGS+=(--tls-verify=false)
    if "$CONTAINER_RUNTIME" build "${BUILD_ARGS[@]}" -t "$IMAGE_TAG" -f "$CF" "$CTX" \
            >"$SETUP_LOG_DIR/build-${IDX}.log" 2>&1; then
        SETUP_BUILD=$PASS
        pass "$CONTAINER_RUNTIME build succeeded ($CF)"
    else
        fail "$CONTAINER_RUNTIME build failed ($CF) - last lines:"
        tail -n 4 "$SETUP_LOG_DIR/build-${IDX}.log" | cut -c1-200 | sed 's/^/      /'
        return
    fi

    CPORT="$(grep -iE '^[[:space:]]*EXPOSE[[:space:]]' "$CF" 2>/dev/null | grep -oE '[0-9]+' | head -1)"
    CPORT="${CPORT:-8080}"
    HPORT="${SETUP_PORT:-$(_setup_free_port)}"
    "$CONTAINER_RUNTIME" rm -f "$NAME" >/dev/null 2>&1 || true
    local RUN_ENV_ARGS=() _kv
    for _kv in $SETUP_RUN_ENV; do RUN_ENV_ARGS+=(-e "$_kv"); done
    if ! "$CONTAINER_RUNTIME" run -d --name "$NAME" -p "${HPORT}:${CPORT}" "${RUN_ENV_ARGS[@]}" "$IMAGE_TAG" >/dev/null 2>&1; then
        fail "could not start the container (host port $HPORT -> $CPORT)"
        "$CONTAINER_RUNTIME" rmi -f "$IMAGE_TAG" >/dev/null 2>&1 || true
        return
    fi

    deadline=$(( SECONDS + SETUP_STARTUP_TIMEOUT ))
    while (( SECONDS < deadline )); do
        body="$(curl -s --connect-timeout 2 --max-time 5 -w $'\n%{http_code}' \
            "http://127.0.0.1:${HPORT}/warehouses" 2>/dev/null || true)"
        code="${body##*$'\n'}"; body="${body%$'\n'*}"
        # Fallback: curl from inside the container (rootless podman without a host port mapping)
        if [[ "$code" != "200" && "$CONTAINER_RUNTIME" == "podman" ]]; then
            body="$(podman exec "$NAME" sh -c "curl -s --connect-timeout 2 --max-time 5 -w '\n%{http_code}' http://127.0.0.1:${CPORT}/warehouses" 2>/dev/null || true)"
            code="${body##*$'\n'}"; body="${body%$'\n'*}"
        fi
        if [[ "$code" == "200" ]] && printf '%s' "$body" | python3 -I -c 'import sys, json; json.load(sys.stdin)' 2>/dev/null; then
            SETUP_RUN=$PASS
            SETUP_CF_USED="$CF"
            pass "GET /warehouses -> HTTP 200 + valid JSON"
            break
        fi
        if [[ "$("$CONTAINER_RUNTIME" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
            log "    the container exited before answering - last log lines:"
            "$CONTAINER_RUNTIME" logs --tail 5 "$NAME" 2>&1 | cut -c1-200 | sed 's/^/      /'
            break
        fi
        sleep 1
    done
    [[ "$SETUP_RUN" -ne 0 ]] && fail "GET /warehouses -> HTTP ${code:-000} (expected 200 + JSON)"

    "$CONTAINER_RUNTIME" stop -t 3 "$NAME" >/dev/null 2>&1 || true
    "$CONTAINER_RUNTIME" rm -f "$NAME" >/dev/null 2>&1 || true
    "$CONTAINER_RUNTIME" rmi -f "$IMAGE_TAG" >/dev/null 2>&1 || true
}

log "--- S.1 Containerfile present ---"
SETUP_CANDIDATES=()
while IFS= read -r _line; do
    [[ -n "$_line" ]] && SETUP_CANDIDATES+=("$_line")
done < <(lib_find_containerfiles "$REPO_DIR" | lib_rank_containerfiles "$REPO_DIR" | head -n "$SETUP_MAX_CANDIDATES")

if [[ ${#SETUP_CANDIDATES[@]} -gt 0 ]]; then
    SETUP_CONTAINERFILE=$PASS
    pass "found ${#SETUP_CANDIDATES[@]} (app Containerfiles first, then least nested): ${SETUP_CANDIDATES[0]}"
else
    fail "no Containerfile/Dockerfile found in $REPO_DIR"
fi

log "--- S.2 Image build / S.3 Container start, endpoint responds ---"
if [[ -z "${CONTAINER_RUNTIME:-}" ]]; then
    fail "no container runtime (docker/podman) available"
elif [[ ${#SETUP_CANDIDATES[@]} -eq 0 ]]; then
    fail "SKIP: no Containerfile to build"
else
    _setup_idx=0
    for _cf in "${SETUP_CANDIDATES[@]}"; do
        _setup_idx=$(( _setup_idx + 1 ))
        _setup_try_candidate "$_cf" "$_setup_idx"
        [[ "$SETUP_RUN" -eq 0 ]] && break
    done
fi

log ""
log "=== SETUP SUMMARY ==="
log "  S.1 Containerfile : $([ $SETUP_CONTAINERFILE -eq 0 ] && echo PASS || echo FAIL)"
log "  S.2 Image build   : $([ $SETUP_BUILD -eq 0 ] && echo PASS || echo FAIL)"
log "  S.3 Container+http: $([ $SETUP_RUN -eq 0 ] && echo PASS || echo FAIL)"

if [[ "$SETUP_BUILD" -eq 0 && "$SETUP_RUN" -eq 0 ]]; then
    rm -rf "$SETUP_LOG_DIR"
else
    log "  (build/start logs kept in: $SETUP_LOG_DIR)"
fi

export SETUP_CONTAINERFILE SETUP_BUILD SETUP_RUN SETUP_CF_USED
