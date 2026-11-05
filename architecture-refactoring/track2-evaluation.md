# Tech Race - Traccia 2: Sistema di Valutazione Automatica

> **Documento per gli organizzatori** - descrive il funzionamento del sistema di scoring automatico.
> La valutazione è quasi interamente automatizzata: l'unico intervento umano previsto è la
> revisione di eventuali segnalazioni del golden master (vedi Layer 3).

---

## Architettura del sistema di valutazione

```
┌──────────────────────────────────────────────────────────────────┐
│                        check_all.sh                               │
│                   (Orchestratore 3 Layer)                         │
└────────────┬──────────────┬──────────────────┬───────────────────┘
             │              │                  │
             ▼              ▼                  ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
    │   LAYER 1    │ │   LAYER 2    │ │     LAYER 3      │
    │Script Python/│ │ LLM Analysis │ │   Regressione     │
    │    bash      │ │ (bob run)    │ │  (golden master)  │
    │check_setup.sh│ │              │ │                  │
    │ check_m1.sh  │ │ Accuratezza  │ │ Stessi flussi    │
    │ check_m2.sh  │ │ mappa, test  │ │ contro l'app     │
    │ check_m3.sh  │ │ significativi│ │ originale vs il  │
    │ check_m4.sh  │ │ decomposizione│ │ repo del team   │
    │ check_m5.sh  │ │ root cause   │ │                  │
    └──────────────┘ └──────────────┘ └──────────────────┘
                     └──────────────┘
                            │
                            ▼
                  ┌─────────────────┐
                  │  JSON Report    │
                  │  scoring finale │
                  └─────────────────┘
```

---

## Layer 1 - Verifica Artefatti e Funzionale

Verifica oggettiva di artefatti, file, grafi di dipendenza e risposte HTTP contro un'istanza
realmente avviata dell'app. Non richiede giudizio umano.

### Script disponibili

| Script | Milestone | Cosa verifica |
|--------|-----------|---------------|
| `check_setup.sh` | Setup | Containerfile presente, build immagine, container avviato + endpoint risponde |
| `check_m1.sh` | M1 | `ARCHITECTURE.md` presente, bonus diagramma, estrazione del grafo reale delle dipendenze |
| `check_m2.sh` | M2 | Coverage prima/dopo, `pytest` passa, bonus test di concorrenza |
| `check_m3.sh` | M3 | Nessun import circolare (`detect_cycles.py`), codice morto rimosso, bonus test ancora passanti |
| `check_m4.sh` | M4 | Load test reale: 50 richieste concorrenti via HTTP, stock finale esatto |
| `check_m5.sh` | M5 | Dipendenza watsonx.ai, model-id, no key hardcoded, endpoint `/assistant`, `pipeline.yaml`, PipelineRun |
| `check_golden_master.sh` | - | Layer 3: cattura/verifica di non-regressione (vedi sezione dedicata) |
| `detect_cycles.py` | M1, M3 | Analizzatore AST di import circolari - usato sia per estrarre il grafo (M1) che per verificarne l'aciclicità (M3) |

### Variabili di input richieste

```bash
# Obbligatorie
export TEAM="team-alpha"
export REPO_DIR="/path/al/repository/del/team"

# Opzionali
export NAMESPACE="team-alpha-ns"       # richiesto per M5B (PipelineRun)
export GOLDEN_MASTER_FILE="/path/golden_master.json"   # richiesto per il Layer 3
export BASELINE_COVERAGE="8"                  # default: coverage dell'app di partenza (vedi nota sotto)
export CONTAINER_RUNTIME="podman"             # "docker" o "podman" (default: auto-detect)
export EVAL_PORT="18092"                      # porta host per il container di valutazione long-lived
export SETUP_PORT="18090"                     # porta host per il container transiente di check_setup.sh
export PYTHON_BIN="/path/al/venv/bin/python"  # default: python3 - usare un venv con pytest+coverage installati
export WATSONX_API_KEY="..."
export WATSONX_PROJECT_ID="..."
export SKIP_LAYER2="false"                    # default di check_all.sh: true (vedi "Configurazione Layer 2")
export OUTPUT_FILE="scoring-team-alpha.json"  # default: stdout
```

> **Nota sulla baseline di coverage**: `challenge-starter/tests/test_basic.py`, come
> distribuito ai team, copre circa l'**8%** del codice (misurato con
> `coverage run -m pytest && coverage report`, usando il `.coveragerc` del
> repo). `check_m2.sh` usa questo valore come default per `BASELINE_COVERAGE`.
> Se l'app di partenza viene modificata prima della gara, ricalcolare questo
> numero e passarlo esplicitamente.

### Dettaglio dei check Layer 1

```text
# Setup: Containerizzazione (vedi check_setup.sh)
  - file Containerfile*/Dockerfile*/*.Containerfile/*.Dockerfile in QUALSIASI cartella del repo (2pt)
  - build immagine → exit 0 (2pt)
  - run (senza config, con segnaposto WATSONX_*) + curl su EXPOSE (default 8080) /warehouses → HTTP 200 + JSON (1pt)
  # Candidati ordinati dando precedenza a quelli nella cartella che contiene l'app (main.py, requirements.txt,
  # package app/), poi per profondita'; ne vengono provati fino a 6, passa se UNO funziona.

# M1: Mappa dell'architettura (vedi check_m1.sh)
  - find ARCHITECTURE.md (8pt - Layer 1)
  - estrazione del grafo reale (detect_cycles.py --graph) → passato al Layer 2 per 1.2/1.3
  BONUS: blocco mermaid/dot/plantuml o immagine in ARCHITECTURE.md (+5pt)

# M2: Test di caratterizzazione (vedi check_m2.sh)
  - coverage.py: coverage attuale - BASELINE_COVERAGE >= 30 punti (10pt)
  - pytest → exit 0 (8pt)
  BONUS: test file che menziona "stock" + un termine di concorrenza nel codice, non nei soli import/commenti (+5pt)

# M3: Rompi gli accoppiamenti (vedi check_m3.sh)
  - detect_cycles.py sul package "app" → exit 0, nessun ciclo (6pt)
  - legacy_fax.py assente + nessun import residuo (4pt)
  BONUS: pytest ancora exit 0 dopo il refactoring (+5pt)

# M4: Il bug dei conteggi di stock (vedi check_m4.sh)
  - 50 POST /orders + 50 POST /orders/{id}/confirm concorrenti sullo stesso
    SKU, confronto stock finale con il valore atteso deterministico (10pt)
  BONUS: stesso pattern di ricerca del bonus M2 (+5pt)

# M5A: Assistente AI (vedi check_m5.sh)
  - grep requirements.txt per ibm-watsonx-ai / langchain-ibm (2pt)
  - grep sorgente per "openai/gpt-oss-120b" + assenza di key hardcoded (3pt)
  - POST /assistant {"question": "..."} → campo "answer" > 50 caratteri (5pt)
    # Timeout 150 s per tentativo; fino a 3 tentativi se la risposta e' 000/502/503/504 o ha corpo vuoto
    # (l'LLM puo' superare il minuto quando e' sotto carico, e il primo giro a freddo e' il piu' lento).
    # Il brief chiede ai team 180 s sulla chiamata a watsonx.ai, cosi' l'app rinuncia dopo il checker.
    # Caso peggiore: 3 x 150 s = 7,5 minuti per team.

# M5B: Pipeline Tekton scan + email (stesso meccanismo di Traccia 1)
  - una Pipeline del namespace (letta come JSON da OpenShift; in mancanza, il YAML nel repo)
    ha un task con taskRef.name: bob-vulnerability-scan (2pt)
    # Task preinstallato nel namespace del team
    # (immagine: image-registry.openshift-image-registry.svc:5000/bobshell/bobshell:latest).
    # Il nome del task dentro la Pipeline (es. "bob-security-scan") non viene verificato.
  - la stessa Pipeline ha BOB_API_KEY tra i parametri e un task che invia email via SMTP (5pt)
    # Il task di invio puo' essere inline (taskSpec) o un Task del namespace richiamato con taskRef;
    # si cerca "smtp", "smtplib", "sendmail" o "mailpit" nello script, nei comandi/argomenti o nei nomi
    # delle variabili d'ambiente degli step. Un Task preso da un resolver remoto (hub, git) non e'
    # leggibile e non conta; il NOME del task (es. "send-report-email") non conta mai.
    # Ripiego sul file del repo (solo se nel namespace non c'e' nessuna Pipeline con il Task Bob):
    # vale il file con kind: Pipeline (non PipelineRun) che soddisfa piu' criteri, ignorando le righe
    # di commento; l'invio e' riconosciuto da smtplib/smtp_ssl/SMTP_HOST/MAILPIT_SMTP/smtps:///sendmail/swaks/mailx.
  - almeno un PipelineRun con condizione Succeeded=True nel namespace (1pt)
  - mailpit: GET https://<MAILPIT_UI_URL>/api/v1/messages → almeno 1 messaggio ricevuto (2pt)
    # Verifica che l'email con il report sia effettivamente arrivata in Mailpit
    # curl -s -k https://<MAILPIT_UI_URL>/api/v1/messages | python3 -c
    #   "import sys,json; msgs=json.load(sys.stdin)['messages']; assert len(msgs)>0"
  BONUS M5: M5A + M5B entrambi a 10pt (+5pt)
```

### Gestione del container di valutazione

A differenza di Traccia 1 (dove i servizi girano già su OpenShift al momento della
valutazione), qui `check_all.sh` builda e avvia **un solo container long-lived** dal
`Containerfile` del team, e lo riusa per tutti i check HTTP-dipendenti (Layer 3 golden
master, M4, M5A.3) prima di distruggerlo. L'ordine è importante:

1. `check_setup.sh` builda l'immagine e verifica l'endpoint con un container *transiente*
   (lo distrugge subito dopo - è solo il check S.1-S.3)
2. Se S.2 è passato, `check_all.sh` builda **un'altra** immagine long-lived e avvia un
   container fresco
3. **Il golden master viene verificato per primo**, sul container appena avviato - prima
   che qualunque altro check lo tocchi. `check_golden_master.sh` fa un confronto per
   valore esatto, e questo è valido solo su un'istanza con i dati di seed intatti
4. Solo dopo, `check_m4.sh` (che muta lo stock) e `check_m5.sh` (stateless)

---

## Layer 2 - Analisi Qualitativa del Codice (LLM, tramite `bob run`)

Analisi semantica del codice e dei documenti prodotti dal team: un agente Bob legge il repository clonato (con `read_file`/`grep`/`list_files`) e risponde con un JSON di verdetti. Valuta
aspetti che gli script non possono giudicare con certezza: accuratezza di una mappa
architetturale, se un refactoring ha davvero separato le responsabilità, se un fix
affronta la causa reale di un bug di concorrenza.

### Prompt template

Un'unica chiamata a `bob run` copre tutti i criteri Layer 2. Nel prompt (definito in
`lib_common.sh`, `lib_layer2_prompt`) vanno solo i due grafi di dipendenza: quello dell'app di
partenza e quello estratto dal repository del team (`detect_cycles.py --graph`, calcolato da
`check_m1.sh`). `ARCHITECTURE.md`, i test e i moduli di magazzino/ordini li legge l'agente stesso
nel repository, con `read_file`/`grep`/`list_files`.

Per la mappa (1.2) il giudice accetta un `ARCHITECTURE.md` fedele a **uno dei due** grafi: la
traccia chiede di mappare il codice *prima* di toccarlo, quindi un documento fedele all'app
originale è corretto anche se il codice è stato poi rifattorizzato.

```
1. m1_map_accurate: ARCHITECTURE.md descrive il grafo delle dipendenze di UNO dei due stati
   (originale o attuale)? Piccole omissioni vanno bene; moduli/dipendenze inventati o un
   mix dei due no.
2. m1_temporal_coupling_found: ARCHITECTURE.md documenta esplicitamente l'accoppiamento
   temporale per cui spedizione/magazzino dipendono silenziosamente dall'ordine di
   inizializzazione (es. initialize_stock_cache() va chiamata prima)?
3. m2_tests_meaningful: i test asseriscono su valori concreti, non check vuoti o tautologici?
4. m3_utils_decomposed: utils.py è stato scomposto per responsabilità reali (non solo
   rinominato o lasciato come unico file)?
5. m4_root_cause_fixed: il fix in warehouse.py / orders.py usa una vera primitiva di
   sincronizzazione (threading.Lock, transazione DB, ...), non una patch superficiale
   (sleep, retry alla cieca)?

Risposta: SOLO un JSON
{"m1_map_accurate":..., "m1_temporal_coupling_found":..., "m2_tests_meaningful":...,
 "m3_utils_decomposed":..., "m4_root_cause_fixed":..., "notes":"..."}
```

(Il testo esatto del prompt è in inglese, in `lib_layer2_prompt`.)

### Configurazione Layer 2

Il Layer 2 usa `bob run` (serve `bob` nel PATH), non servono credenziali watsonx. Si può eseguire
in due modi:

```bash
# 1) Batch (skill techrace-score*): il batch ASPETTA il Layer 2.
#    score-all-teams.sh valuta prima i team con SKIP_LAYER2=true (Layer 1 al posto del giudice),
#    poi esegue run-layer2.sh in primo piano: per ogni team lancia "bob run" sul clone, sostituisce
#    i 5 criteri nel JSON, RICALCOLA punteggio di milestone, totale e tier, riscrive
#    teams-score.json e cancella il clone. La tabella finale viene stampata solo dopo, quindi i
#    totali mostrati sono definitivi (34 punti su 105 dipendono dal Layer 2). Per ogni team
#    senza verdetto la tabella riporta "PROVVISORIO: Layer 2 non disponibile".
bash .bob/skills/techrace-score-architecture-refactoring/score-all-teams.sh              # con Layer 2
bash .bob/skills/techrace-score-architecture-refactoring/score-all-teams.sh --no-layer2  # senza: punteggi provvisori

# 2) Singolo team: check_all.sh con il Layer 2 in linea (qui il default è true, quindi va
#    chiesto esplicitamente)
export SKIP_LAYER2="false"
```

Il prompt e le chiamate a `bob run` (2 tentativi, estrazione del JSON dal testo) sono definiti
una sola volta in `lib_common.sh` (`lib_layer2_prompt`, `lib_layer2_judge`) e usati sia da
`check_all.sh` sia da `run-layer2.sh`: i due percorsi non possono giudicare con domande diverse.

### Ruolo del Layer 2 nel punteggio

Il Layer 2 non è solo consultivo: le sue risposte (`true`/`false`) determinano direttamente i
punti dei criteri 1.2 (10), 1.3 (7), 2.3 (7), 3.2 (5) e 4.2 (5), cioè 34 punti su 105 (vedi
`track2-scoring.md`). Se il giudice non risponde (`layer2.available: false`), i cinque
criteri sono derivati dal Layer 1 come proxy e vanno rivisti a mano.

---

## Layer 3 - Verifica di Non-Regressione (`check_golden_master.sh`)

A differenza di Traccia 1, qui il Layer 3 non verifica flussi funzionali nuovi: verifica
che il refactoring non abbia cambiato comportamento esistente sui flussi che **nessuna
milestone chiede di toccare**.

### Come funziona

1. **Prima della gara** (una volta, contro `WareFlow` originale non modificato, istanza
   appena avviata):
   ```bash
   python3 main.py &
   ./evaluation-scripts/check_golden_master.sh capture http://127.0.0.1:8080 golden_master.json
   ```
   Questo salva una sequenza fissa di 12 richieste (lifecycle di un ordine, casi di
   errore, liste) e le relative risposte, con i campi non deterministici (`created_at`,
   `tracking_code`) esclusi dal confronto.

2. **A fine gara**, contro un'istanza **appena avviata** del repository di ciascun team
   (lo stesso container long-lived che `check_all.sh` builda per M4/M5 - il golden
   master viene verificato per primo, prima che M4 muti lo stock):
   ```bash
   ./evaluation-scripts/check_golden_master.sh verify http://127.0.0.1:18092 golden_master.json
   ```

### Perché richiede un'istanza fresca

Il confronto è per valore esatto (non solo struttura), e questo è valido solo perché
`WareFlow` riparte sempre dai medesimi dati di seed (vedi `app/db.py`) su ogni avvio
pulito. Se il golden master venisse verificato contro un'istanza già "sporcata" da
richieste precedenti (es. dal load test di M4), il confronto darebbe falsi positivi.

### Esito

Un mismatch viene *segnalato*, non sottratto automaticamente da una milestone specifica -
quasi sempre indica una regressione accidentale introdotta durante M3/M4, e richiede una
rapida revisione umana prima di finalizzare il punteggio del team.

---

## Formato Output Scoring JSON

```json
{
  "team": "team-alpha",
  "namespace": "team-alpha-ns",
  "timestamp": "2026-01-01T14:00:00Z",
  "layer1": {
    "setup_containerfile": true,
    "setup_build": true,
    "setup_run": true,
    "m1_arch_doc": true,
    "m1_bonus_diagram": false,
    "m2_coverage": true,
    "m2_tests_pass": true,
    "m2_coverage_current": 42.3,
    "m2_bonus_concurrency_test": true,
    "m3_no_cycles": true,
    "m3_dead_code_removed": true,
    "m3_bonus_tests_pass": true,
    "m4_load": true,
    "m4_bonus_regression_test": false,
    "m5a_dep": true,
    "m5a_model_config": true,
    "m5a_no_hardcoded_key": true,
    "m5a_endpoint": true,
    "m5b_yaml": false,
    "m5b_gate_logic": false,
    "m5b_run_succeeded": false,
    "golden_master_ok": true
  },
  "layer2": {
    "m1_map_accurate": true,
    "m1_temporal_coupling_found": true,
    "m2_tests_meaningful": true,
    "m3_utils_decomposed": true,
    "m4_root_cause_fixed": true,
    "notes": "Mappa accurata, fix di concorrenza con threading.Lock corretto"
  },
  "milestones": {
    "setup": {"score": 5, "bonus": 0, "max": 5},
    "m1": {"score": 25, "bonus": 0, "max": 30},
    "m2": {"score": 25, "bonus": 5, "max": 30},
    "m3": {"score": 15, "bonus": 5, "max": 20},
    "m4": {"score": 15, "bonus": 0, "max": 20},
    "m5a": {"score": 10, "bonus": 0, "max": 10},
    "m5b": {"score": 0, "bonus": 0, "max": 10},
    "m5_bonus": 0
  },
  "total": 105,
  "tier": "Platinum"
}
```

---

## Istruzioni operative per gli organizzatori

### Setup pre-gara (1 giorno prima)

1. **Preparare l'ambiente cluster**: creare i team con
   `organizer-scripts/provision-team.sh <team>,architecture-refactoring` (il repo Gitea del team si
   chiama `architecture-refactoring`, come la traccia). Il Secret `watsonx-credentials` del namespace
   (`WATSONX_API_KEY` e `WATSONX_PROJECT_ID`) viene creato **solo** se passi entrambe le credenziali,
   con `--watsonx-key=... --watsonx-project=...` oppure con le variabili `WATSONX_API_KEY` e
   `WATSONX_PROJECT_ID`. Con nessuna delle due, o con una sola, il Secret non viene creato e il log lo
   dice due volte: un avviso iniziale e una riga `watsonx.ai Secret: NOT CREATED - <motivo>` nel
   riepilogo di ogni team. Senza il Secret l'endpoint `POST /assistant` (5A.3) non può funzionare in
   OpenShift e lo scoring prova il container con valori segnaposto (5A.3 non passa): rilancia il
   provisioning con le credenziali.

2. **Catturare il golden master** contro `challenge-starter` non modificato:
   ```bash
   cd architecture-refactoring/challenge-starter
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python main.py &
   ../evaluation-scripts/check_golden_master.sh capture http://127.0.0.1:8080 \
       ../golden_master.json
   ```

3. **Consegnare ai team URL e password**: a fine provisioning `provision-team.sh` scrive in
   `organizer-scripts/team-credentials/` (ignorata da git, permessi 700) un file `<team>.md` per ogni
   team, con solo i suoi accessi (OpenShift, Gitea con il comando di clone, Mailpit), e
   `_riepilogo-organizzatori.md` con tutti i team in una tabella. Dai a ogni team solo il suo file; se la
   verifica finale di un team ha avuto errori, il suo file lo segnala in cima. Per riscriverli:
   `organizer-scripts/export-team-credentials.sh [team...]` (legge soltanto da OpenShift);
   `cleanup-teams.sh` li cancella con i team.

4. **Verificare gli script** contro una soluzione di riferimento interna (non distribuita
   ai partecipanti).

### Esecuzione scoring (al termine della gara)

```bash
# 1. Clone del repository del team
git clone <repo-url-del-team> /tmp/repos/team-alpha

# 2. Scoring completo
TEAM=team-alpha \
REPO_DIR=/tmp/repos/team-alpha \
NAMESPACE=team-alpha-ns \
GOLDEN_MASTER_FILE=/path/golden_master.json \
PYTHON_BIN=/path/al/venv/bin/python \
./evaluation-scripts/check_all.sh > scoring-team-alpha.json

# 3. Visualizzazione risultato
python3 -m json.tool < scoring-team-alpha.json
```

### Dipendenze richieste sulla macchina di valutazione

| Tool | Uso |
|------|-----|
| `bash` 4+ | Tutti gli script |
| `python3` 3.9+ | `detect_cycles.py`, `golden_master_runner.py`, estrazione JSON |
| `pytest` + `coverage` | M2, M3 (bonus) - installarli nel venv puntato da `PYTHON_BIN` |
| `curl` | Chiamate HTTP |
| `docker` o `podman` | Build/run dei container (Setup e container di valutazione long-lived) |
| `oc` | Verifica OpenShift (M5B, se si vuole controllare il namespace) |
| `tkn` | Verifica Tekton PipelineRun (M5B) |

---

## Gestione edge case

| Scenario | Comportamento |
|----------|----------------|
| Nessun Containerfile nel repo | Setup = FAIL, M4/M5A.3/golden master saltati, M1/M2/M3 (source-level) comunque eseguiti |
| Container non risponde in tempo | Setup S.3 / golden master / M4 / M5A.3 = FAIL con warning |
| `docker`/`podman` assente sulla macchina di valutazione | Setup e tutti i check HTTP-dipendenti = FAIL con warning |
| `bob run` non produce un giudizio valido | `layer2.available: false`, i criteri 1.2/1.3/2.3/3.2/4.2 restano derivati dal Layer 1 (proxy) e vanno rivisti a mano |
| `GOLDEN_MASTER_FILE` non impostato | Layer 3 saltato (non influisce sul punteggio, solo sulla diagnostica) |
| Namespace OpenShift non accessibile o `tkn` assente | M5B.3 = FAIL con messaggio esplicativo |
| Repository vuoto o non trovato | Tutti i check Layer 1 = FAIL |
