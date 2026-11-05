#!/usr/bin/env bash
# check_m5.sh - Milestone 5: Observability and AI.
# Layer 1 - artifact + functional check. Challenge 5A (AI assistant) and
# Challenge 5B (Tekton pipeline with IBM Bob security gate) are independent,
# 10 points each - same structure as Track 1's check_m5.sh.
#
# Canonical 5A endpoint (fixed in track2-brief.md so this check is
# deterministic): POST /assistant {"question": "<text>"} -> {"answer": "<text>"}
#
# INPUT (env vars):
#   REPO_DIR    Team repo root (default .)
#   BASE_URL    Base URL of the running app, for the 5A.3 endpoint check (default: http://127.0.0.1:8080)
#   NAMESPACE   Team's OpenShift namespace, for the 5B.3 PipelineRun check
# OUTPUT: M5A_DEP, M5A_MODEL_CONFIG, M5A_NO_HARDCODED_KEY, M5A_ENDPOINT,
#         M5B_YAML, M5B_GATE_LOGIC, M5B_RUN_SUCCEEDED, M5B_EMAIL, M5_BONUS_BOTH (0=PASS, 1=FAIL)
# Sourced by check_all.sh, so it must not call "exit".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib_common.sh"

REPO_DIR="${REPO_DIR:-.}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
NAMESPACE="${NAMESPACE:-}"

PASS=0
FAIL=1
M5A_DEP=$FAIL
M5A_MODEL_CONFIG=$FAIL
M5A_NO_HARDCODED_KEY=$FAIL
M5A_ENDPOINT=$FAIL
M5B_YAML=$FAIL
M5B_GATE_LOGIC=$FAIL
M5B_RUN_SUCCEEDED=$FAIL
M5B_EMAIL=$FAIL
M5_BONUS_BOTH=$FAIL

log()  { echo "[M5] $*"; }
pass() { log "  OK - $*"; }
fail() { log "  FAIL - $*"; }

HAVE_OC=true
command -v oc >/dev/null 2>&1 || HAVE_OC=false

log "--- 5A.1 watsonx.ai dependency (Python SDK or LangChain) ---"
DEP_PATTERN='ibm[-_]watsonx[-_]ai|langchain[-_]ibm|ibm[-_]watson[-_]machine[-_]learning'
if grep -rliE "$DEP_PATTERN" "$REPO_DIR" \
        --include="requirements*.txt" --include="pyproject.toml" --include="Pipfile" \
        --include="setup.py" --include="setup.cfg" --include="constraints*.txt" \
        --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv 2>/dev/null | grep -q . \
   || grep -rhiE "pip[0-9]* install.*($DEP_PATTERN)" "$REPO_DIR" \
        --include="Containerfile*" --include="Dockerfile*" --exclude-dir=.git 2>/dev/null | grep -q .; then
    M5A_DEP=$PASS
    pass "watsonx.ai dependency found"
else
    fail "no watsonx.ai / LangChain-IBM dependency declared (requirements*.txt, pyproject, Pipfile, setup.*, or pip install in the Containerfile)"
fi

log "--- 5A.2 model-id openai/gpt-oss-120b configured ---"
# Anywhere the team can legitimately set it: Python source, config files, env files or a manifest.
if grep -rlE 'gpt-oss-120b' "$REPO_DIR" \
        --include='*.py' --include='*.env' --include='*.yaml' --include='*.yml' --include='*.json' \
        --include='*.toml' --include='*.ini' --include='*.cfg' --include='*.properties' --include='*.conf' \
        --exclude-dir=.git --exclude-dir=venv --exclude-dir=.venv --exclude-dir=node_modules 2>/dev/null | grep -q .; then
    M5A_MODEL_CONFIG=$PASS
    pass "model-id gpt-oss-120b found (source / config / env / manifest)"
else
    fail "model-id gpt-oss-120b not found in any source or config file of the repo"
fi

log "--- 5A.2b no hardcoded API key ---"
# A long literal assigned to an api-key name, in code, config, .env (quoted or not), shell scripts,
# manifests or the ENV/ARG of a Containerfile; environment lookups, references and placeholders do not
# count. See lib_count_hardcoded_secrets.
HARDCODED_KEY=$(lib_count_hardcoded_secrets "$REPO_DIR")
HARDCODED_KEY="${HARDCODED_KEY:-0}"
if [[ "$HARDCODED_KEY" -eq 0 ]]; then
    M5A_NO_HARDCODED_KEY=$PASS
    pass "no hardcoded API key found"
else
    fail "possible hardcoded API key found ($HARDCODED_KEY occurrence(s)) - disqualification criterion"
fi

log "--- 5A.3 POST /assistant responds in natural language (> 50 chars) ---"
# The LLM can take well over a minute when several callers use it at once, and the first call after a
# cold start is the slowest. Each attempt waits up to 150 s; a 502/503/504, a timeout or an empty answer
# is retried instead of costing the team the step.
LIB_MAX_TIME=150 lib_http_retry POST "${BASE_URL%/}/assistant" '{"question":"Which warehouses are running low on stock?"}' 3
ANSWER_TEXT=$(printf '%s' "$LIB_BODY" | python3 -I -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("answer", "") if isinstance(d, dict) else "")
except Exception:
    print("")
' 2>/dev/null)
ANSWER_LEN=${#ANSWER_TEXT}
log "  HTTP $LIB_CODE, response: $ANSWER_LEN characters"
if [[ "$LIB_CODE" == "200" && "$ANSWER_LEN" -gt 50 ]]; then
    M5A_ENDPOINT=$PASS
    pass "POST /assistant -> $ANSWER_LEN characters"
elif [[ "$LIB_CODE" != "200" ]]; then
    fail "endpoint unreachable or error (HTTP $LIB_CODE)"
elif [[ "$ANSWER_LEN" -eq 0 ]]; then
    fail "response missing or empty 'answer' field"
else
    fail "response too short ($ANSWER_LEN chars, expected > 50)"
fi

# Challenge 5B is checked through oc, independent of resource names. Same logic as Track 1's
# check_m5.sh; keep the two in sync.
#   5B.1 (2pt): a Pipeline uses the bob-vulnerability-scan Task as a taskRef
#   5B.2 (5pt): ... with a BOB_API_KEY param plus a task that sends mail over SMTP
#   5B.3 (1pt): at least one PipelineRun Succeeded
#   5B.4 (2pt): at least one message received in Mailpit

# Repo files that declare a Pipeline: "kind: Pipeline" must be the whole value, so a PipelineRun
# (or any other kind starting with "Pipeline") is not taken for one.
_find_pipeline_files() {
    find "${REPO_DIR:-.}" \( -name "*.yaml" -o -name "*.yml" \) \
        -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null \
        | xargs -r grep -lE '^[[:space:]]*kind:[[:space:]]*Pipeline[[:space:]]*(#.*)?$' 2>/dev/null
}

# Repo fallback (Pipeline not applied to the namespace): prints "<file>|<bob>|<key>|<smtp>" for the
# file meeting most criteria. Only real content counts, so full-line comments are dropped first (a
# "TODO: send via SMTP" comment must not look like an email task), and the SMTP signal is an actual
# way of sending mail, never the NAME of a task: a task called send-report-email that only echoes
# something earns nothing. Mirrors _analyze_pipelines, which reads the applied Pipelines.
_analyze_repo_pipelines() {
    local f body bob key smtp score best_score=-1 best=""
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        body="$(grep -vE '^[[:space:]]*#' "$f" 2>/dev/null)"
        bob=no; key=no; smtp=no
        printf '%s\n' "$body" | grep -q "bob-vulnerability-scan" && bob=yes
        printf '%s\n' "$body" | grep -q "BOB_API_KEY" && key=yes
        printf '%s\n' "$body" | grep -qiE 'smtplib|smtp_ssl|SMTP_HOST|MAILPIT_SMTP|smtps?://|sendmail|swaks|mailx' && smtp=yes
        score=0
        [[ "$bob" == yes ]] && score=$(( score + 2 ))
        [[ "$key" == yes ]] && score=$(( score + 1 ))
        [[ "$smtp" == yes ]] && score=$(( score + 1 ))
        if (( score > best_score )); then best_score=$score; best="$f|$bob|$key|$smtp"; fi
    done < <(_find_pipeline_files)
    [[ -n "$best" ]] && printf '%s\n' "$best"
    return 0
}

# Analyse the Pipeline JSON of a namespace. Prints "<name>|<uses_bob_scan>|<has_BOB_API_KEY>|<has_SMTP>"
# for the best Pipeline (the one meeting most criteria), following referenced Tasks too: the email task
# may be inline (taskSpec) or a separate Task of the namespace called with taskRef.
_analyze_pipelines() {
    local ns="$1" pj tj
    pj="$(oc get pipeline -n "$ns" -o json 2>/dev/null || echo '{"items":[]}')"
    tj="$(oc get task -n "$ns" -o json 2>/dev/null || echo '{"items":[]}')"
    PIPE_JSON="$pj" TASK_JSON="$tj" python3 -I -c '
import os, json
def load(k):
    try: return json.loads(os.environ[k]).get("items", [])
    except Exception: return []
tasks = {t["metadata"]["name"]: t for t in load("TASK_JSON")}
def steps_of(spec):
    return (spec or {}).get("steps", []) or []
def smtp_in(steps):
    for s in steps:
        blob = (s.get("script", "") or "") + " " + " ".join(s.get("args", []) or []) + " " + " ".join(s.get("command", []) or [])
        envs = [e.get("name", "") for e in (s.get("env") or [])]
        if any(k in blob.lower() for k in ("smtp", "smtplib", "sendmail", "mailpit")) or any("smtp" in e.lower() for e in envs):
            return True
    return False
best = None
for p in load("PIPE_JSON"):
    spec = p.get("spec", {})
    allt = (spec.get("tasks") or []) + (spec.get("finally") or [])
    bob_scan = any((t.get("taskRef") or {}).get("name") == "bob-vulnerability-scan" for t in allt)
    params = {x.get("name") for x in (spec.get("params") or [])}
    for t in allt:
        for x in (t.get("params") or []):
            params.add(x.get("name"))
    has_key = "BOB_API_KEY" in params
    has_smtp = False
    for t in allt:
        ref = (t.get("taskRef") or {}).get("name")
        if t.get("taskSpec") and smtp_in(steps_of(t["taskSpec"])):
            has_smtp = True
        elif ref and ref in tasks and ref != "bob-vulnerability-scan" and smtp_in(steps_of(tasks[ref].get("spec"))):
            has_smtp = True
    score = int(bob_scan) * 2 + int(has_key) + int(has_smtp)
    row = (score, p["metadata"]["name"], bob_scan, has_key, has_smtp)
    if best is None or row[0] > best[0]:
        best = row
if best:
    print("{}|{}|{}|{}".format(best[1], "yes" if best[2] else "no", "yes" if best[3] else "no", "yes" if best[4] else "no"))
'
}

log "--- 5B.1 / 5B.2 Pipeline nel namespace ---"
PIPE_NAME=""; PIPE_BOB="no"; PIPE_KEY="no"; PIPE_SMTP="no"; PIPE_SRC=""
if $HAVE_OC && [[ -n "$NAMESPACE" ]]; then
    _row="$(_analyze_pipelines "$NAMESPACE")"
    if [[ -n "$_row" ]]; then
        IFS='|' read -r PIPE_NAME PIPE_BOB PIPE_KEY PIPE_SMTP <<< "$_row"
        PIPE_SRC="namespace"
    fi
fi
# Repo fallback, only when the namespace has nothing usable.
if [[ "$PIPE_BOB" != "yes" ]]; then
    _repo_row="$(_analyze_repo_pipelines)"
    if [[ -n "$_repo_row" ]]; then
        IFS='|' read -r _pf _rb _rk _rs <<< "$_repo_row"
        [[ "$_rb" == "yes" ]] && { PIPE_BOB="yes"; PIPE_SRC="repo (non applicata)"; PIPE_NAME="${PIPE_NAME:-$(basename "$_pf")}"; }
        [[ "$_rk" == "yes" ]] && PIPE_KEY="yes"
        [[ "$_rs" == "yes" ]] && PIPE_SMTP="yes"
    fi
fi
log "  Pipeline: ${PIPE_NAME:-—} (${PIPE_SRC:-nessuna}) | bob-vulnerability-scan=$PIPE_BOB | BOB_API_KEY=$PIPE_KEY | SMTP=$PIPE_SMTP"

if [[ "$PIPE_BOB" == "yes" ]]; then
    M5B_YAML=$PASS
    pass "Pipeline '$PIPE_NAME' usa il Task bob-vulnerability-scan"
else
    fail "Nessuna Pipeline usa il Task bob-vulnerability-scan"
fi
if [[ "$PIPE_KEY" == "yes" && "$PIPE_SMTP" == "yes" ]]; then
    M5B_GATE_LOGIC=$PASS
    pass "Pipeline con parametro BOB_API_KEY + task di invio email SMTP"
elif [[ "$PIPE_KEY" == "yes" ]]; then
    fail "BOB_API_KEY presente ma nessun task che invia email via SMTP"
else
    fail "Parametro BOB_API_KEY non trovato nella Pipeline"
fi

log "--- 5B.3 PipelineRun Succeeded ---"
if [[ -z "$NAMESPACE" ]]; then
    fail "NAMESPACE non impostato — skip check PipelineRun"
elif ! $HAVE_OC; then
    fail "oc CLI non disponibile"
else
    SUCCEEDED_RUNS=$(oc get pipelinerun -n "$NAMESPACE" -o json 2>/dev/null | python3 -I -c '
import sys, json
try: items = json.load(sys.stdin).get("items", [])
except Exception: items = []
n = 0
for r in items:
    for c in (r.get("status", {}).get("conditions") or []):
        if c.get("type") == "Succeeded" and c.get("status") == "True":
            n += 1
print(n)
' 2>/dev/null)
    SUCCEEDED_RUNS="${SUCCEEDED_RUNS:-0}"
    log "  PipelineRun Succeeded: $SUCCEEDED_RUNS"
    if [[ "$SUCCEEDED_RUNS" -ge 1 ]]; then
        M5B_RUN_SUCCEEDED=$PASS
        pass "$SUCCEEDED_RUNS PipelineRun Succeeded nel namespace $NAMESPACE"
    else
        fail "Nessun PipelineRun Succeeded in namespace $NAMESPACE"
    fi
fi

log "--- 5B.4 Email report ricevuta in Mailpit ---"
MAILPIT_UI_URL=""; MAILPIT_USER=""; MAILPIT_PASS=""
if $HAVE_OC && [[ -n "$NAMESPACE" ]]; then
    MAILPIT_UI_URL=$(oc get configmap team-info -n "$NAMESPACE" -o jsonpath='{.data.MAILPIT_UI_URL}' 2>/dev/null)
    MAILPIT_USER=$(oc get configmap team-info -n "$NAMESPACE" -o jsonpath='{.data.MAILPIT_USERNAME}' 2>/dev/null)
    MAILPIT_PASS=$(oc get configmap team-info -n "$NAMESPACE" -o jsonpath='{.data.MAILPIT_PASSWORD}' 2>/dev/null)
fi
if [[ -z "$MAILPIT_UI_URL" ]]; then
    fail "MAILPIT_UI_URL non disponibile nel ConfigMap team-info — skip check email"
else
    MSG_COUNT=$(curl -sk --connect-timeout 8 --max-time 20 -u "${MAILPIT_USER}:${MAILPIT_PASS:-techrace}" \
        "${MAILPIT_UI_URL%/}/api/v1/messages?limit=50" 2>/dev/null \
        | python3 -I -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(max(int(d.get("total", 0) or 0), len(d.get("messages", []) or [])))
except Exception:
    print(0)
' 2>/dev/null)
    MSG_COUNT="${MSG_COUNT:-0}"
    log "  Messaggi in Mailpit: $MSG_COUNT"
    if [[ "$MSG_COUNT" -ge 1 ]]; then
        M5B_EMAIL=$PASS
        pass "Email report ricevuta in Mailpit ($MSG_COUNT messaggi)"
    else
        fail "Nessun messaggio trovato in Mailpit"
    fi
fi

log "--- 5.BONUS both 5A and 5B fully completed ---"
M5A_SCORE=$(( (M5A_DEP == 0 ? 2 : 0) + (M5A_MODEL_CONFIG == 0 ? 3 : 0) + (M5A_ENDPOINT == 0 ? 5 : 0) ))
M5B_SCORE=$(( (M5B_YAML == 0 ? 2 : 0) + (M5B_GATE_LOGIC == 0 ? 5 : 0) + (M5B_RUN_SUCCEEDED == 0 ? 1 : 0) + (M5B_EMAIL == 0 ? 2 : 0) ))
if [[ "$M5A_SCORE" -ge 10 && "$M5B_SCORE" -ge 10 ]]; then
    M5_BONUS_BOTH=$PASS
    pass "both 5A (${M5A_SCORE}pt) and 5B (${M5B_SCORE}pt) completed - bonus granted"
else
    fail "5A=${M5A_SCORE}pt, 5B=${M5B_SCORE}pt - bonus requires both at 10pt"
fi

log ""
log "=== M5 SUMMARY ==="
log "  5A.1 watsonx.ai dependency   : $([ $M5A_DEP -eq 0 ] && echo PASS || echo FAIL)"
log "  5A.2 model-id configured     : $([ $M5A_MODEL_CONFIG -eq 0 ] && echo PASS || echo FAIL)"
log "  5A.2b no hardcoded key       : $([ $M5A_NO_HARDCODED_KEY -eq 0 ] && echo PASS || echo FAIL)"
log "  5A.3 /assistant endpoint     : $([ $M5A_ENDPOINT -eq 0 ] && echo PASS || echo FAIL)"
log "  5B.1 Pipeline→bob-vuln-scan  : $([ $M5B_YAML -eq 0 ] && echo PASS || echo FAIL)"
log "  5B.2 BOB_API_KEY + SMTP task : $([ $M5B_GATE_LOGIC -eq 0 ] && echo PASS || echo FAIL)"
log "  5B.3 PipelineRun Succeeded   : $([ $M5B_RUN_SUCCEEDED -eq 0 ] && echo PASS || echo FAIL)"
log "  5B.4 Email in Mailpit        : $([ $M5B_EMAIL -eq 0 ] && echo PASS || echo FAIL)"
log "  BONUS both 5A+5B             : $([ $M5_BONUS_BOTH -eq 0 ] && echo PASS || echo FAIL)"

export M5A_DEP M5A_MODEL_CONFIG M5A_NO_HARDCODED_KEY M5A_ENDPOINT \
       M5B_YAML M5B_GATE_LOGIC M5B_RUN_SUCCEEDED M5B_EMAIL M5_BONUS_BOTH
