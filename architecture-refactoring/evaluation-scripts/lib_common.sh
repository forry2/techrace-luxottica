#!/usr/bin/env bash
# lib_common.sh - helpers shared by the Track 2 check_*.sh scripts.
# Sourced by check_all.sh and by each check_*.sh, never executed: no "exit" (it would end
# check_all.sh) and no "set -e". JSON is parsed with python3 -I, never grep.
# Same idea as java-modernization/evaluation-scripts/lib_common.sh; the functions that exist in
# both tracks (lib_http*, lib_find_containerfiles) are kept identical on purpose.

# lib_http METHOD URL [JSON_BODY]  ->  sets LIB_CODE (000 if unreachable) and LIB_BODY
# Total timeout is LIB_MAX_TIME seconds (default 25; use more for LLM endpoints).
lib_http() {
    local method="$1" url="$2" body="${3:-}" out="" mt="${LIB_MAX_TIME:-25}"
    if [[ -n "$body" ]]; then
        out=$(curl -sk --connect-timeout 8 --max-time "$mt" -w $'\n%{http_code}' -X "$method" "$url" \
                -H 'Content-Type: application/json' -d "$body" 2>/dev/null) || true
    else
        out=$(curl -sk --connect-timeout 8 --max-time "$mt" -w $'\n%{http_code}' -X "$method" "$url" 2>/dev/null) || true
    fi
    LIB_CODE="${out##*$'\n'}"
    LIB_BODY="${out%$'\n'*}"
    if ! [[ "$LIB_CODE" =~ ^[0-9]{3}$ ]]; then LIB_CODE=000; LIB_BODY=""; fi
    return 0
}

# lib_http_retry METHOD URL [JSON_BODY] [ATTEMPTS]  ->  like lib_http, but retries while the answer is
# a transient failure: no answer (000), a gateway error (502/503/504) or an empty 200. LLM endpoints are
# slow and the first call after a cold start is the slowest, so one slow answer must not cost points.
# Sets LIB_CODE / LIB_BODY of the last attempt. LIB_MAX_TIME applies to each attempt.
lib_http_retry() {
    local method="$1" url="$2" body="${3:-}" attempts="${4:-3}" i
    for (( i = 1; i <= attempts; i++ )); do
        lib_http "$method" "$url" "$body"
        case "$LIB_CODE" in 000|502|503|504) ;; 200) [[ -n "$LIB_BODY" ]] && return 0 ;; *) return 0 ;; esac
        (( i < attempts )) && sleep 3
    done
    return 0
}

# lib_extract_llm_json  (stdin: free text from an LLM)  ->  stdout: ONE-line JSON object, or {}.
# Models often wrap the answer in prose or markdown fences, or put "{...}" examples before it, so a
# greedy "first { to last }" match breaks. Every "{" is tried with a real JSON decoder and the LAST
# object that carries the expected verdict keys wins (the final answer comes after any reasoning).
lib_extract_llm_json() {
    python3 -I -c '
import json, sys
text = sys.stdin.read()
KEYS = ("m1_map_accurate", "m1_temporal_coupling_found", "m2_tests_meaningful",
        "m3_utils_decomposed", "m4_root_cause_fixed")
dec = json.JSONDecoder()
best = None
i = text.find("{")
while i != -1:
    try:
        obj, end = dec.raw_decode(text, i)
    except ValueError:
        i = text.find("{", i + 1)
        continue
    if isinstance(obj, dict) and any(k in obj for k in KEYS):
        best = obj
    i = text.find("{", end if isinstance(obj, dict) and any(k in obj for k in KEYS) else i + 1)
print(json.dumps(best if best is not None else {}, ensure_ascii=False))
' 2>/dev/null || echo "{}"
}

# lib_layer2_prompt <starter_graph> <real_graph>  ->  stdout: the prompt of the Layer 2 (LLM) judge.
# One definition shared by check_all.sh (inline Layer 2) and run-layer2.sh (background Layer 2), so the
# two paths can never judge with different questions.
lib_layer2_prompt() {
    local starter="${1:-unavailable}" real="${2:-unavailable}"
    [[ -n "$starter" ]] || starter="unavailable"
    [[ -n "$real" ]] || real="unavailable"
    cat <<PROMPT_EOF
You are a code evaluator for a Python refactoring exercise. The repository to analyse
is in your current workspace (already cloned from Gitea). Use read_file, grep, and
list_files to inspect the actual files — do NOT rely on memory or assumptions.

Verify these criteria and respond ONLY with a valid JSON object (no markdown, no extra text):

1. m1_map_accurate: Does ARCHITECTURE.md accurately describe the module dependency graph
   of EITHER of these two states of the code? The exercise asks teams to map the code BEFORE
   refactoring it, so a document faithful to the original app is correct even if the code was
   refactored afterwards; a document faithful to the current code is correct too.
   Answer true if the documented modules and dependencies match one of the two graphs
   (minor omissions are fine; invented modules/dependencies or a mix of the two are not).
   ORIGINAL (starter) graph:
   ${starter}
   CURRENT graph (extracted from the repo you are in):
   ${real}

2. m1_temporal_coupling_found: Does ARCHITECTURE.md explicitly document the temporal
   coupling where shipping/warehouse code silently depends on initialization order
   (e.g. initialize_stock_cache() must be called first)?

3. m2_tests_meaningful: Are the test files meaningful? Read them and check that
   assertions use concrete expected values — not trivially empty or tautological checks.

4. m3_utils_decomposed: Was the dumping-ground utils.py genuinely split by responsibility
   into separate cohesive modules, or is it just renamed / left as one file?

5. m4_root_cause_fixed: Does the concurrency fix in warehouse.py / orders.py address the
   root cause with a real synchronization primitive (threading.Lock, DB transaction, etc.),
   NOT a surface patch like a sleep or blind retry?

Respond ONLY with this JSON (no other text):
{"m1_map_accurate":true/false,"m1_temporal_coupling_found":true/false,"m2_tests_meaningful":true/false,"m3_utils_decomposed":true/false,"m4_root_cause_fixed":true/false,"notes":"brief observations citing specific files/lines"}
PROMPT_EOF
}

# lib_layer2_judge <repo_dir> <prompt> [attempts=2] [timeout_s=900]  ->  stdout: ONE-line verdict JSON, or {}.
# A transient "bob run" failure must not silently zero the 34 Layer 2 points, hence the retries.
lib_layer2_judge() {
    local repo="$1" prompt="$2" attempts="${3:-2}" tmo="${4:-900}" i result text json="{}"
    for (( i = 1; i <= attempts; i++ )); do
        result=$(timeout "$tmo" bob run --format json --disable-mcp --disable-subagents \
            --workspace "$repo" --max-turns 10 "$prompt" 2>/dev/null || echo '{"status":"error"}')
        text=$(printf '%s' "$result" | python3 -I -c "
import sys, json
r = json.load(sys.stdin)
print(r.get('last_message', ''))
" 2>/dev/null || echo "")
        # Not a greedy "{.*}" regex: the model often wraps the verdict in prose or adds braces around it.
        json=$(printf '%s' "$text" | lib_extract_llm_json)
        [[ "$json" != "{}" ]] && break
        echo "[layer2] bob run senza JSON valido (tentativo $i/$attempts)" >&2
    done
    printf '%s\n' "$json"
}

# lib_count_hardcoded_secrets <dir>  ->  how many lines of the repo hold a literal API key.
# Looks at what a team can really commit: Python and config files, .env files (quoted or not), shell
# scripts, Kubernetes/Tekton manifests (a `name: ..._API_KEY` followed by a literal `value:`) and the
# ENV / ARG instructions of a Containerfile, in every syntax (ENV K=v, ENV K v, quoted, multi-line `\`).
# A value is a literal key when it is 20+ characters of [A-Za-z0-9_-] (dots too when it is quoted).
# Unquoted it must also contain a digit and no dot, which leaves out references such as
# `settings.WATSONX_API_KEY`, `$KEY` and `${KEY}`, empty values and identifiers.
# A key inside a comment still counts: it is in the repo all the same.
lib_count_hardcoded_secrets() {
    python3 -I - "${1:-.}" <<'PYEOF'
import os, re, shlex, sys

root = sys.argv[1]
SKIP = {".git", "node_modules", "venv", ".venv", "site-packages", "__pycache__"}
NAME = re.compile(r"api[._-]?key", re.I)
# Environment lookups and obvious placeholders on the same line are not secrets.
LINE_EXCL = re.compile(r"os\.environ|os\.getenv|getenv\(|\$\{|secretKeyRef|valueFrom|changeme|your[-_]|<.*>", re.I)
QUOTED = re.compile(r"""api[._-]?key["']?\s*[=:]\s*["']([A-Za-z0-9_.\-]{20,})""", re.I)
UNQUOTED = re.compile(r"""api[._-]?key\s*[=:]\s*([A-Za-z0-9_.\-]{20,})\s*(?:#.*)?$""", re.I)
YAML_ENV = re.compile(r"""name:\s*["']?[\w.\-]*api[._-]?key["']?\s*\n\s*value:\s*["']?([A-Za-z0-9_\-]{20,})["']?\s*$""",
                      re.I | re.M)


def unquoted_literal(v):
    return bool(re.fullmatch(r"[A-Za-z0-9_\-]{20,}", v)) and any(c.isdigit() for c in v)


def kind(name):
    n = name.lower()
    if n.startswith(("containerfile", "dockerfile")) or n.endswith((".containerfile", ".dockerfile")):
        return "cf"
    if n == ".env" or n.endswith(".env") or n.startswith(".env.") or ".env." in n:
        return "text"
    if os.path.splitext(n)[1] in {".py", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".properties", ".conf", ".sh"}:
        return "text"
    return None


def scan_text(text):
    hits = 0
    for line in text.splitlines():
        if LINE_EXCL.search(line):
            continue
        if QUOTED.search(line):
            hits += 1
        else:
            m = UNQUOTED.search(line)
            if m and unquoted_literal(m.group(1)):
                hits += 1
    hits += sum(1 for m in YAML_ENV.finditer(text) if not LINE_EXCL.search(m.group(0)))
    return hits


def scan_containerfile(text):
    hits = 0
    for line in re.sub(r"\\\s*\n", " ", text).splitlines():
        s = re.sub(r"^#\s*", "", line.strip())      # a commented-out key is still in the repo
        m = re.match(r"(?i)(?:ENV|ARG)\s+(.*)$", s)
        if not m:
            continue
        body = m.group(1)
        try:
            toks = shlex.split(body)
        except ValueError:
            toks = body.split()
        if toks and "=" not in toks[0]:               # old syntax: ENV KEY value
            pairs = [(toks[0], " ".join(toks[1:]))]
        else:
            pairs = [t.split("=", 1) for t in toks if "=" in t]
        hits += sum(1 for k, v in pairs if NAME.search(k) and unquoted_literal(v))
    return hits


total = 0
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    for name in filenames:
        k = kind(name)
        if not k:
            continue
        path = os.path.join(dirpath, name)
        try:
            if os.path.getsize(path) > 2_000_000:
                continue
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        total += scan_containerfile(text) if k == "cf" else scan_text(text)
print(total)
PYEOF
}

# lib_count_module_references <dir> <module>  ->  how many .py files REALLY reference <module>.
# A real reference is an import (import x / from x import y / from pkg import x), an attribute or a name
# (pkg.x.f(), x.f()), or a dynamic import by string (importlib.import_module("pkg.x"), __import__("x")).
# A comment, a docstring or a path inside an assert ("app/x.py") is not a reference, which a plain grep
# cannot tell apart: a team that writes "# legacy_fax removed" must not lose the dead-code points.
# Files that do not parse are counted with a fallback text match on non-comment lines, so a broken
# file cannot hide a live import.
lib_count_module_references() {
    python3 -I - "${1:-.}" "${2:?module}" <<'PYEOF'
import ast, os, re, sys

root, module = sys.argv[1], sys.argv[2]
SKIP = {".git", "node_modules", "venv", ".venv", "site-packages", "__pycache__"}
DYN = {"import_module", "__import__"}


def mentions(text):
    return module in (text or "")


def references(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            if any(mentions(a.name) for a in n.names):
                return True
        elif isinstance(n, ast.ImportFrom):
            if mentions(n.module) or any(a.name == module for a in n.names):
                return True
        elif isinstance(n, ast.Attribute):
            if n.attr == module:
                return True
        elif isinstance(n, ast.Name):
            if n.id == module:
                return True
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in DYN and n.args and isinstance(n.args[0], ast.Constant) and mentions(str(n.args[0].value)):
                return True
    return False


count = 0
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    for name in filenames:
        if not name.endswith(".py"):
            continue
        try:
            src = open(os.path.join(dirpath, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        try:
            hit = references(ast.parse(src))
        except (SyntaxError, ValueError):
            hit = any(mentions(l) for l in src.splitlines() if not l.lstrip().startswith("#"))
        count += 1 if hit else 0
print(count)
PYEOF
}

# lib_find_containerfiles <dir>  ->  one path per line: every Containerfile/Dockerfile in the repo,
# whatever its name or suffix (Containerfile, Dockerfile, Containerfile.app, app.Dockerfile, ...).
lib_find_containerfiles() {
    find "${1:-.}" -type f \( -name 'Containerfile*' -o -name 'Dockerfile*' -o -name '*.Containerfile' -o -name '*.Dockerfile' \) \
        -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/venv/*' -not -path '*/.venv/*' \
        -not -path '*/site-packages/*' 2>/dev/null
}

# lib_rank_containerfiles <repo-dir>  (stdin: Containerfile paths)  ->  same paths, best candidate first.
# Setup is about the starting app, so a Containerfile whose build context (its own folder) holds the
# app (main.py, requirements.txt or an app/ package) comes first; ties break on depth, then path.
lib_rank_containerfiles() {
    python3 -I -c '
import os, sys
rows = []
for line in sys.stdin:
    path = line.rstrip("\n")
    if not path:
        continue
    ctx = os.path.dirname(os.path.abspath(path))
    has_app = any(os.path.exists(os.path.join(ctx, n)) for n in ("main.py", "requirements.txt", "app", "pyproject.toml"))
    rows.append((0 if has_app else 1, path.count("/"), path))
for _, _, path in sorted(rows):
    print(path)
'
}

# lib_test_files_mention_stock_and_concurrency <repo-dir>  ->  exit 0 if some Python test file really
# exercises concurrency on the stock. Used by the M2 and M4 bonuses. A test file is any test_*.py /
# *_test.py / file under a tests/ or test/ folder, wherever it sits in the repo.
#
# The file is parsed (ast), so only code counts: a docstring, a comment, an unused import or a plain
# string saying "threading" does not earn the bonus. It needs BOTH
#   - a concurrency call: Thread / ThreadPoolExecutor / ProcessPoolExecutor / Pool / Process / Timer,
#     asyncio gather / create_task / TaskGroup / ensure_future / to_thread / run_in_executor, a
#     subclass of Thread or Process, or `.submit(...)` / `.apply_async(...)` on any object and
#     `.map(...)` / `.starmap(...)` / `.imap(...)` on something named like a pool or executor (the
#     executor often comes from a fixture, so its constructor is not in the test file);
#   - the word "stock" in an identifier, an attribute, or a string that is not a docstring.
# A file that does not parse cannot run as a test, so it earns nothing.
lib_test_files_mention_stock_and_concurrency() {
    python3 -I - "${1:-.}" <<'PYEOF'
import ast, os, re, sys

root = sys.argv[1]
SKIP = {".git", "node_modules", "venv", ".venv", "site-packages", "__pycache__"}
CALLS = {"Thread", "ThreadPoolExecutor", "ProcessPoolExecutor", "Pool", "Process", "Timer",
         "gather", "create_task", "TaskGroup", "ensure_future", "to_thread", "run_in_executor",
         "run_coroutine_threadsafe", "start_new_thread"}
BASES = {"Thread", "Process"}
ANY_RECEIVER = {"submit", "apply_async", "map_async", "starmap_async"}
POOL_RECEIVER = {"map", "starmap", "imap", "imap_unordered"}
POOL_NAME = re.compile(r"pool|executor|^ex$|^tp$|^pp$", re.I)
STOCK = re.compile(r"stock", re.I)


def last(node):
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def receiver_name(node):
    return last(node.value) if isinstance(node, ast.Attribute) else ""


def docstring_nodes(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def exercises_stock_concurrently(tree):
    concurrent = False
    stock = False
    docs = docstring_nodes(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = last(n.func)
            if name in CALLS or name in ANY_RECEIVER:
                concurrent = True
            elif name in POOL_RECEIVER and POOL_NAME.search(receiver_name(n.func)):
                concurrent = True
        elif isinstance(n, ast.ClassDef):
            if any(last(b) in BASES for b in n.bases):
                concurrent = True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and STOCK.search(n.name):
            stock = True
        elif isinstance(n, ast.Name) and STOCK.search(n.id):
            stock = True
        elif isinstance(n, ast.Attribute) and STOCK.search(n.attr):
            stock = True
        elif isinstance(n, ast.arg) and STOCK.search(n.arg):
            stock = True
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and STOCK.search(n.value):
            stock = True
        if concurrent and stock:
            return True
    return False


for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    in_tests = any(p in ("tests", "test") for p in dirpath.split(os.sep))
    for name in filenames:
        if not name.endswith(".py"):
            continue
        if not (in_tests or name.startswith("test_") or name.endswith("_test.py")):
            continue
        try:
            tree = ast.parse(open(os.path.join(dirpath, name), encoding="utf-8", errors="replace").read())
        except (OSError, SyntaxError, ValueError):
            continue
        if exercises_stock_concurrently(tree):
            sys.exit(0)
sys.exit(1)
PYEOF
}

# lib_app_dir <repo-dir>  ->  the directory of the application package, or nothing.
# One definition for M1, M2 and M3, so they never disagree about where the app is. A package called
# "app" wins; after a refactoring it may have been renamed or moved (wareflow/app, src/app, ...), so
# the first package with an __init__.py is the fallback. Tests, virtualenvs and VCS/vendor dirs are
# never the app. Shallowest candidate first.
lib_app_dir() {
    python3 -I - "${1:-.}" <<'PYEOF'
import os, sys
root = os.path.abspath(sys.argv[1])
SKIP = {".git", "node_modules", "venv", ".venv", "env", "site-packages", "tests", "test", "__pycache__", "build", "dist"}
named, pkg = [], []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = sorted(d for d in dirnames if d not in SKIP and not d.endswith(".egg-info"))
    depth = dirpath[len(root):].count(os.sep)
    if depth > 4:
        dirnames[:] = []
        continue
    has_py = any(f.endswith(".py") for f in filenames)
    if os.path.basename(dirpath) == "app" and has_py:
        named.append((depth, dirpath))
    elif "__init__.py" in filenames and dirpath != root:
        pkg.append((depth, dirpath))
for group in (named, pkg):
    if group:
        print(sorted(group)[0][1])
        break
PYEOF
}
