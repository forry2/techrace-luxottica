# Tech Race - Traccia 2: Sistema di Scoring

> **Documento pubblico** - visibile ai partecipanti. I criteri di verifica sono trasparenti.

---

## Riepilogo punteggi

| Milestone | Punti base | Bonus | Max |
|-----------|-----------|-------|-----|
| Setup - Containerizzazione app | 5 | - | 5 |
| M1 - Mappa l'architettura reale | 25 | +5 | 30 |
| M2 - Rete di sicurezza (test) | 25 | +5 | 30 |
| M3 - Rompi gli accoppiamenti | 15 | +5 | 20 |
| M4 - Il bug dei conteggi di stock | 15 | +5 | 20 |
| M5 - Osservabilità e AI | 20 | +5 | 25 |
| **Totale** | **105** | **+25** | **130** |

---

## Classificazione finale

| Range punti | Livello | Descrizione |
|-------------|---------|-------------|
| 105-130 | ⭐⭐⭐ Platinum | Tutte le milestone completate in pieno, tipicamente con bonus |
| 80-104 | ⭐⭐ Gold | Tutte le milestone completate (o quasi) |
| 55-79 | ⭐ Silver | 3-4 milestone completate |
| < 55 | Bronze | 1-2 milestone completate |

---

## Setup - Containerizzazione app (5 punti)

### Criteri di scoring

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| S.1 | `Containerfile` presente nel repo | 2 | `check_setup.sh`: almeno un file `Containerfile*`/`Dockerfile*` in qualsiasi cartella |
| S.2 | L'immagine builda senza errori | 2 | `check_setup.sh`: `docker build`/`podman build` → exit 0 (provati fino a 6 candidati, prima quelli nella cartella dell'app) |
| S.3 | Container avviato, `GET /warehouses` risponde HTTP 200 + JSON valido | 1 | `check_setup.sh`: `docker run` senza configurazione (segnaposto `WATSONX_*`) + `curl` su `/warehouses` |
| | **Totale Setup** | **5** | |

Nessun bonus per questa fase: è un gate di verifica, non un obiettivo di qualità.

---

## M1 - Mappa l'architettura reale (25 punti)

### Criteri di scoring

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 1.1 | `ARCHITECTURE.md` presente nel repo | 8 | `check_m1.sh`: file inspection |
| 1.2 | La mappa corrisponde alla struttura reale del codice | 10 | Layer 2: LLM confronta `ARCHITECTURE.md` con il grafo delle dipendenze reale estratto da `detect_cycles.py --graph` |
| 1.3 | Identificato l'accoppiamento temporale implicito tra i moduli di spedizione e magazzino | 7 | Layer 2: il documento menziona la dipendenza dall'ordine di inizializzazione |
| | **Totale M1** | **25** | |

### Bonus M1 (+5 pt)
La mappa include anche un diagramma generato o disegnato, non solo testo:
- Verifica: `check_m1.sh` → blocco ```mermaid/```dot/```plantuml o immagine embedded in `ARCHITECTURE.md`

---

## M2 - Rete di sicurezza: test di caratterizzazione (25 punti)

### Criteri di scoring

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 2.1 | Coverage aumentata di almeno 30 punti percentuali rispetto al punto di partenza | 10 | `check_m2.sh`: `coverage.py` sul codice attuale vs `BASELINE_COVERAGE` (~8%, quella dell'app di partenza) |
| 2.2 | I test passano | 8 | `check_m2.sh`: `pytest` exit 0 |
| 2.3 | I test sono significativi (asseriscono su valori reali, non trivialmente vuoti) | 7 | Layer 2: LLM analizza i file di test prodotti |
| | **Totale M2** | **25** | |

### Bonus M2 (+5 pt)
Almeno un test copre esplicitamente lo scenario di richieste concorrenti su `/stock`:
- Verifica: `check_m2.sh` → un file di test (in `tests/`, `test/` o `test_*.py`/`*_test.py`, ovunque nel repo) che nel codice — non nei soli `import` o commenti — referenzia sia "stock" che un meccanismo di concorrenza (thread/concurrent/parallel/executor/asyncio/multiprocessing)

---

## M3 - Rompi gli accoppiamenti (15 punti)

### Criteri di scoring

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 3.1 | Nessun import circolare residuo tra i moduli dell'app | 6 | `check_m3.sh`: analisi statica del grafo delle dipendenze (`detect_cycles.py`, basata su AST - rileva anche import circolari "nascosti" dentro una funzione) |
| 3.2 | Il modulo "discarica" è stato scomposto per responsabilità | 5 | Layer 2: LLM valuta se le responsabilità sono state effettivamente separate (non solo rinominate) |
| 3.3 | Codice morto rimosso (file + tutti i riferimenti residui) | 4 | `check_m3.sh`: file assente + nessun import residuo nel sorgente |
| | **Totale M3** | **15** | |

### Bonus M3 (+5 pt)
Tutti i test di M2 continuano a passare dopo il refactoring (comportamento preservato):
- Verifica: `check_m3.sh` → `pytest` exit 0 sul codice refactorizzato

---

## M4 - Il bug dei conteggi di stock (15 punti)

### Criteri di scoring

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 4.1 | Il sistema gestisce correttamente 50 richieste concorrenti di decremento stock sullo stesso articolo, risultato finale esatto | 10 | `check_m4.sh`: 50 richieste HTTP reali e concorrenti (`POST /orders` + `POST /orders/{id}/confirm`) contro un'istanza viva dell'app, confronto del valore finale con quello atteso deterministico |
| 4.2 | Causa del bug risolta alla radice (sincronizzazione reale), non con una patch superficiale (es. retry casuale) | 5 | Layer 2: LLM analizza la soluzione nel codice |
| | **Totale M4** | **15** | |

### Bonus M4 (+5 pt)
La soluzione è accompagnata da un test di regressione specifico per questo bug:
- Verifica: `check_m4.sh` → stesso pattern di ricerca del bonus M2, nella suite di test del team

---

## M5 - Osservabilità e AI (20 punti)

Divisa in due challenge indipendenti da 10 punti ciascuna.

### M5A - Assistente AI per il magazzino (10 punti)

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 5A.1 | Dipendenza watsonx.ai presente (SDK Python o LangChain-IBM) in `requirements.txt` | 2 | `check_m5.sh`: file inspection |
| 5A.2 | Model-id `openai/gpt-oss-120b` configurato nel sorgente, nessuna API key hardcoded | 3 | `check_m5.sh`: grep sul sorgente + assenza di pattern di credenziali letterali |
| 5A.3 | `POST /assistant` risponde con testo in linguaggio naturale, campo `answer` > 50 caratteri | 5 | `check_m5.sh`: chiamata HTTP reale contro un'istanza viva dell'app |
| | **Totale M5A** | **10** | |

### M5B - Pipeline Tekton con IBM Bob Security Gate (10 punti)

| # | Criterio | Punti | Metodo di verifica |
|---|----------|-------|-------------------|
| 5B.1 | Una Pipeline Tekton del namespace usa il Task preinstallato `bob-vulnerability-scan` (`taskRef`) | 2 | `check_m5.sh`: Pipeline letta da OpenShift come JSON, `taskRef.name` dei task |
| 5B.2 | La stessa Pipeline ha il parametro `BOB_API_KEY` e un task che invia il report via email (SMTP) | 5 | `check_m5.sh`: parametri della Pipeline + script/variabili dei task |
| 5B.3 | Almeno un PipelineRun con risultato `Succeeded` | 1 | `check_m5.sh`: condizione `Succeeded=True` dei PipelineRun del namespace |
| 5B.4 | L'email con il report è arrivata in Mailpit | 2 | `check_m5.sh`: `GET /api/v1/messages` sul Mailpit del team |
| | **Totale M5B** | **10** | |

### Bonus M5 (+5 pt)
Entrambe le challenge M5A e M5B completate (tutti e 20 i punti base conquistati).

---

## Layer 3 - Verifica di non-regressione (Golden Master)

A differenza di Traccia 1, qui il Layer 3 non verifica solo funzionalità nuove: verifica soprattutto che il refactoring **non abbia cambiato il comportamento esistente**. Prima della gara, gli organizzatori eseguono una sequenza fissa di richieste contro `WareFlow` originale (non modificato, istanza appena avviata) e salvano le risposte come golden master (`check_golden_master.sh capture`). A fine gara, la stessa sequenza viene eseguita contro un'istanza appena avviata del repository di ciascun team (`check_golden_master.sh verify`): se le risposte sui flussi non toccati da nessuna milestone coincidono, il comportamento è stato preservato.

Questo controllo è **diagnostico, non punteggiato direttamente**: una divergenza indica quasi sempre una regressione introdotta per errore durante M3/M4 (non un fallimento di una milestone specifica), e viene segnalata agli organizzatori per una revisione manuale rapida prima di assegnare il punteggio finale.

---

## Formato deliverable

Al termine della gara, il team consegna:

```
REPO_GIT=https://<gitea-host>/<team>/architecture-refactoring
NAMESPACE=<team>-ns
URL_APP=https://wareflow-<team>.apps.cluster.example.com
```

Il sistema di valutazione esegue automaticamente i 3 layer di verifica e produce il JSON di scoring finale.

---

## Criteri di squalifica

| Criterio | Conseguenza |
|----------|-------------|
| Credenziali hardcoded nel sorgente (API key, password, token) | Squalifica della milestone interessata |
| Copia diretta di soluzioni da repository pubblici senza adattamento | Squalifica della milestone interessata |
| Manipolazione degli script di valutazione o dei log | Squalifica del team |

La verifica è automatizzata: layer 1 (script Python/bash), layer 2 (giudizio qualitativo di un agente IBM Bob, `bob run`, eseguito dagli organizzatori: non richiede nessuna azione da parte dei team), layer 3 (regressione comportamentale). Nessun intervento umano è richiesto nel processo di scoring, salvo revisione di eventuali segnalazioni del golden master.
