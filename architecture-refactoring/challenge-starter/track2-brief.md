# Tech Race - Traccia 2: Rifattorizza WareFlow

> **Documento per i partecipanti** - Leggi attentamente prima di iniziare.

---

## Scenario

Sei stato chiamato come consulente tecnico da **NordShip**, azienda di logistica B2B. Il loro sistema di gestione magazzino - `WareFlow` - gira in produzione da anni, costruito nel tempo da diversi contractor, nessuno dei quali lavora più per l'azienda. Funziona, ma nessuno in NordShip sa più spiegare con certezza come sia strutturato internamente, e la documentazione che esiste è scarsa e in parte non più accurata.

Il problema concreto che ha spinto NordShip a chiamarvi: durante i picchi di attività (molti ordini in contemporanea), i responsabili di magazzino segnalano occasionalmente conteggi di stock sbagliati. Nessuno è mai riuscito a riprodurre il problema con certezza, e il team interno ha troppa paura di toccare il codice per indagare seriamente - non sanno cosa potrebbero rompere.

Il vostro obiettivo: capire davvero come funziona `WareFlow`, costruire una rete di sicurezza che permetta di modificarlo senza paura, risolvere i problemi strutturali più evidenti, trovare e risolvere il bug dei conteggi di stock, ed estendere il sistema con una funzionalità di AI che il management vuole da tempo. Avete a disposizione **IBM Bob** come copilota.

---

## Cosa sapete di WareFlow

- Scritto in **Python** (Flask), stato in **SQLite in-memory**
- Si avvia con `pip install -r requirements.txt && python main.py` - nessuna dipendenza esterna
- Espone endpoint REST su magazzini, stock, ordini e spedizioni (`GET /warehouses`, `GET /stock/<sku>`, `POST /orders`, ecc. - il resto lo trovate esplorando il codice)
- **Non esiste una mappa dell'architettura reale**: quella che vedete come primo obiettivo è qualcosa che dovete costruire voi, non qualcosa che vi viene dato

Usate IBM Bob per esplorare il codice, mappare le dipendenze tra i moduli e capire cosa succede davvero prima di cambiare qualunque cosa.

---

## Milestone e punteggi

Puoi completare le milestone in ordine o saltare quelle che ritieni fuori portata. Le milestone sono **indipendenti**: puoi guadagnare punti su M3 senza aver completato M2. Detto questo, M1 e M2 producono le condizioni per intervenire sul resto con sicurezza - conviene non saltarle.

| # | Milestone | Punti base | Bonus | Max |
|---|-----------|-----------|-------|-----|
| Setup | Fai girare l'app e verificala | 5 | - | 5 |
| M1 | Mappa l'architettura reale | 25 | +5 | 30 |
| M2 | Rete di sicurezza: test di caratterizzazione | 25 | +5 | 30 |
| M3 | Rompi gli accoppiamenti | 15 | +5 | 20 |
| M4 | Il bug dei conteggi di stock | 15 | +5 | 20 |
| M5 | Osservabilità e AI | 20 | +5 | 25 |
| | **Totale** | **105** | **+25** | **130** |

### Classificazione finale

| Punti | Livello |
|-------|---------|
| 105-130 | ⭐⭐⭐ Platinum |
| 80-104 | ⭐⭐ Gold |
| 55-79 | ⭐ Silver |
| < 55 | Bronze |

---

## Accesso all'ambiente OpenShift

| Campo | Valore |
|-------|--------|
| Cluster API | `<CLUSTER_API_URL>` |
| Console web | `<CONSOLE_URL>` |
| Username | il nome del tuo team |
| Password | `techrace` |
| Namespace | `<nome-team>-ns` |

Stessa username e stessa password per OpenShift, Gitea e il registry immagini - una sola credenziale da ricordare.

### Login da terminale

```bash
oc login -u <nome-team> -p techrace <CLUSTER_API_URL>
```

### Login dalla console web

Apri `<CONSOLE_URL>` nel browser. Se la pagina di login mostra più opzioni, scegli "htpasswd" e usa le stesse credenziali.

### Non hai la CLI `oc` installata?

Non serve scaricarla da internet: ogni cluster OpenShift la distribuisce da solo. Nella console web, clicca l'icona **?** in alto a destra → **Command Line Tools** → scegli il tuo sistema operativo e scarica il binario corretto.

### Tutti i tuoi link in un posto

Nel tuo namespace è presente un **ConfigMap `team-info`** con tutte le coordinate preconfigurate. Puoi leggerlo con:

```bash
oc get configmap team-info -n <nome-team>-ns -o jsonpath='{.data}'
```

Contiene queste chiavi:

| Chiave | Descrizione |
|--------|-------------|
| `TEAM_NAME` | Nome del tuo team |
| `TRACK` | Traccia assegnata |
| `NAMESPACE` | Il tuo namespace OpenShift |
| `REGISTRY_URL` | URL del registry immagini interno |
| `GITEA_URL` | URL di Gitea |
| `GITEA_REPO_URL` | URL HTTPS del tuo repository |
| `OPENSHIFT_API_URL` | URL API del cluster |
| `OPENSHIFT_CONSOLE_URL` | URL della console web |
| `MAILPIT_SMTP_HOST` | Host SMTP di Mailpit per l'invio email |
| `MAILPIT_SMTP_PORT` | Porta SMTP |
| `MAILPIT_UI_URL` | URL interfaccia web Mailpit per leggere le email ricevute |
| `MAILPIT_USERNAME` | Username SMTP (il tuo nome team) |
| `MAILPIT_PASSWORD` | Password SMTP (stessa del login OpenShift) |

### Registry immagini

Ogni team ha il proprio spazio isolato nel registry interno di OpenShift. Per autenticarti con Podman/Docker:

```bash
podman login -u <nome-team> -p $(oc whoami -t) --tls-verify=false <REGISTRY_URL>
podman push --tls-verify=false <immagine> <REGISTRY_URL>/<nome-team>-ns/<nome-immagine>:<tag>
```

### Repository Git (Gitea)

Il tuo repo è già pronto su Gitea (self-hosted sul cluster, stesse credenziali di OpenShift). L'URL esatto è la chiave `GITEA_REPO_URL` del ConfigMap `team-info`; per clonare inserisci le credenziali nell'URL:

```bash
# URL del repo, es. https://<host-gitea>/<nome-team>/<nome-repo>.git
oc get configmap team-info -n <nome-team>-ns -o jsonpath='{.data.GITEA_REPO_URL}'

git clone https://<nome-team>:techrace@<host-gitea>/<nome-team>/<nome-repo>.git
```

> Il nome del repo è quello indicato in `GITEA_REPO_URL` (di norma `architecture-refactoring`): usa sempre quel valore.

---

## Setup - Fai girare l'app e verificala

### Contesto

Prima di toccare qualunque cosa, verifica che `WareFlow` funzioni davvero sul tuo ambiente, dentro un container - esattamente come girerebbe in produzione.

### Obiettivo

Scrivi un `Containerfile` che costruisca un'immagine dell'app, poi verificala end-to-end: build immagine, avvio container, chiamata a un endpoint reale che deve rispondere con dati validi.

**Immagine base suggerita**: `docker.io/library/python:3.12-slim`

### Deliverable attesi

- [ ] `Containerfile` presente nel repo
- [ ] L'immagine builda senza errori (`podman build` / `docker build`)
- [ ] Il container si avvia e `GET /warehouses` risponde HTTP 200 con JSON valido

**Come viene verificato.** Il `Containerfile` può stare in qualsiasi cartella del repo e avere qualsiasi nome (`Containerfile`, `Dockerfile`, `Dockerfile.app`...). Se nel repo ce ne sono più di uno, la valutazione ne prova fino a 6, a partire da quelli nella cartella che contiene l'app (`main.py`, `requirements.txt` o il package `app/`), e il Setup passa se almeno uno builda e risponde. Il container viene avviato **senza configurazione aggiuntiva**, sulla porta indicata da `EXPOSE` (8080 se manca), e la valutazione cerca una risposta 200 con JSON su `GET /warehouses`. Se la tua app legge `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` o `WATSONX_URL` all'avvio, nella prova di Setup vengono passati valori segnaposto.

---

## M1 - Mappa l'architettura reale

### Contesto

Nessuno in NordShip può spiegarti con certezza come sono collegati i moduli di `WareFlow`. Prima di cambiare qualunque cosa, serve una mappa di come il codice è *davvero* strutturato - non di come "dovrebbe" essere secondo il README.

### Obiettivo

Prodotto un documento `ARCHITECTURE.md` che mappi i moduli dell'applicazione e le dipendenze reali tra di essi. Usa IBM Bob per esplorare il codice ed estrarre le dipendenze effettive, non solo quelle che sembrano ovvie leggendo i nomi dei file.

In particolare, cerca punti in cui un modulo si aspetta che un altro abbia già fatto qualcosa (es. popolato uno stato, inizializzato una risorsa) senza che questa aspettativa sia dichiarata da nessuna parte - e documentalo esplicitamente se lo trovi.

### Deliverable attesi

- [ ] `ARCHITECTURE.md` nel repo, con mappa dei moduli e delle dipendenze
- [ ] La mappa corrisponde alla struttura reale del codice (verificata contro il codice, non contro il README esistente)

**Bonus (+5 pt)**: la mappa include anche un diagramma (es. blocco Mermaid, non solo testo).

---

## M2 - Rete di sicurezza: test di caratterizzazione

### Contesto

Il team NordShip ha troppa paura di modificare `WareFlow` perché non sa cosa potrebbe rompere. Prima di cambiare qualunque comportamento, serve una rete di sicurezza che fissi quello che il sistema fa OGGI.

### Obiettivo

Scrivi test di caratterizzazione sui flussi principali (creazione ordine, conferma ordine, spedizione, aggiornamento stock) che passino contro il codice attuale, prima di modificarlo. Aumenta sensibilmente la coverage di test rispetto al punto di partenza.

### Deliverable attesi

- [ ] Suite di test che copre i flussi principali, tutti passanti
- [ ] Coverage misurabilmente più alta rispetto al punto di partenza (lo script di valutazione confronta i due valori)

**Bonus (+5 pt)**: almeno un test copre esplicitamente lo scenario di richieste concorrenti sullo stock.

---

## M3 - Rompi gli accoppiamenti

### Contesto

Mentre mappavi l'architettura in M1, probabilmente hai notato dipendenze che non dovrebbero esistere: moduli che si richiamano a vicenda, un file che ha finito per contenere di tutto senza una responsabilità chiara, e del codice che non viene più usato da nessuno ma è ancora lì, importato "per sicurezza".

### Obiettivo

Elimina le dipendenze circolari tra i moduli dell'applicazione. Scomponi il modulo che accumula responsabilità non correlate in base a cosa fa davvero ciascuna parte. Rimuovi il codice morto che hai individuato (e tutti i suoi riferimenti).

Non è richiesto cambiare il comportamento esterno dell'app - solo la sua struttura interna. I test scritti in M2 devono continuare a passare dopo queste modifiche.

### Deliverable attesi

- [ ] Nessuna dipendenza circolare residua tra i moduli dell'app
- [ ] Il modulo "discarica" è stato scomposto per responsabilità
- [ ] Il codice morto individuato è stato rimosso, insieme a tutti i suoi riferimenti: nessun modulo deve più importarlo né richiamarlo (un commento o una docstring che lo nomina non è un problema)

**Bonus (+5 pt)**: tutti i test di M2 continuano a passare dopo il refactoring.

---

## M4 - Il bug dei conteggi di stock

### Contesto

I responsabili di magazzino segnalano che, nei periodi di picco, il conteggio di stock di alcuni articoli risulta a volte sbagliato - mai più alto del reale, sempre più basso di quanto dovrebbe essere dopo una raffica di ordini. Nessuno è mai riuscito a riprodurlo con certezza, finché non si prova a generare molte richieste di conferma ordine sullo stesso articolo nello stesso momento.

### Obiettivo

Fai in modo che il sistema gestisca correttamente almeno 50 richieste concorrenti di decremento stock sullo stesso articolo, con un risultato finale sempre esatto. Non è richiesto cambiare la logica di business - il problema è di sincronizzazione, non di dominio.

### Deliverable attesi

- [ ] 50 richieste concorrenti di conferma ordine sullo stesso articolo producono un conteggio finale di stock esatto
- [ ] La causa del bug è risolta alla radice (sincronizzazione reale), non con una patch superficiale come un retry casuale

**Bonus (+5 pt)**: la soluzione è accompagnata da un test di regressione specifico per questo bug.

---

## M5A - Assistente AI per il magazzino

### Contesto

Il management di NordShip vuole che i responsabili di magazzino possano fare domande in linguaggio naturale sullo stato del magazzino, invece di leggere tabelle JSON. watsonx.ai è disponibile nell'infrastruttura aziendale.

### Obiettivo

Aggiungi l'endpoint:

```
POST /assistant
Body: {"question": "<domanda in linguaggio naturale>"}
```

L'endpoint deve:
1. Chiamare watsonx.ai tramite SDK Python o LangChain, con modello `openai/gpt-oss-120b`
2. Basare la risposta sui dati reali del magazzino (stock, ordini, spedizioni)
3. Restituire una risposta in linguaggio naturale, non dati grezzi:

```json
{"answer": "Lo stock di WIDGET-2 è di 248 unità, concentrato nel magazzino di Milano Nord. Nessun articolo è sotto la soglia minima al momento."}
```

Le credenziali `WATSONX_API_KEY` e `WATSONX_PROJECT_ID` sono disponibili come variabili d'ambiente (già configurate come Secret OpenShift nel tuo namespace). Il servizio watsonx.ai da usare è `https://us-south.ml.cloud.ibm.com` (leggilo da una variabile `WATSONX_URL` con questo valore come default): le credenziali fornite valgono per questa regione.

> **Attenzione ai tempi.** Il modello può impiegare da pochi secondi a oltre un minuto per rispondere, soprattutto quando più persone lo usano insieme. Imposta quindi un timeout di **3 minuti** (180 secondi) sulla chiamata a watsonx.ai dalla tua app, e se esponi l'app con una Route aggiungi l'annotazione `haproxy.router.openshift.io/timeout: 180s` (il router di questo cluster è già configurato a 3 minuti, ma l'annotazione ti protegge su un cluster con il default di 30 secondi, dove otterresti un HTTP 504). Con un timeout più corto l'endpoint può restituire errore proprio quando il modello è lento, e il controllo su `POST /assistant` non passa.


### Deliverable attesi

- [ ] La dipendenza watsonx.ai (SDK Python o LangChain-IBM) è dichiarata nei requisiti del progetto (`requirements.txt`, `pyproject.toml`...)
- [ ] Model-id `openai/gpt-oss-120b` configurato nel sorgente o nella configurazione, **senza** chiavi scritte nel repo (nemmeno nel `Containerfile`): le credenziali restano nelle variabili d'ambiente
- [ ] `POST /assistant` con `{"question": "..."}` risponde con un JSON il cui campo `answer` è un testo in linguaggio naturale (più di 50 caratteri), basato sui dati reali del magazzino

---

## M5B - Pipeline Tekton: Security Scan + Report via Email

### Contesto

Il team DevOps di `WareFlow` vuole automatizzare l'analisi di sicurezza del codice: ad ogni esecuzione della pipeline, **IBM Bob** analizza il repository e invia il report completo via email, così da tenere traccia di ogni scansione nel tempo senza leggere i log manualmente.

### Flusso della pipeline

```
Trigger → Pipeline Tekton
    └─ Task 1: bob-security-scan
               IBM Bob Shell analizza il codice sorgente
               → produce bob-scan-report.txt nel workspace condiviso
    └─ Task 2: send-report-email
               Legge bob-scan-report.txt e lo invia via email a Mailpit
               → email ricevuta con il report come corpo del messaggio
```

### Task preinstallato: `bob-vulnerability-scan`

Nel tuo namespace OpenShift è già presente il Task Tekton **`bob-vulnerability-scan`**, pronto all'uso - non devi installare Bob Shell né configurare immagini.

| Parametro | Obbligatorio | Descrizione |
|---|---|---|
| `BOB_API_KEY` | ✅ sì | La tua IBM Bob API key |
| `REPO_URL` | ✅ sì | URL HTTPS del repository da analizzare |
| `GIT_REVISION` | no (default: `main`) | Branch, tag o commit SHA da analizzare |
| `SCAN_PROMPT` | no | Prompt personalizzato per Bob (lascia vuoto per usare quello predefinito OWASP) |

Il Task scrive il report nel workspace `output` come `bob-scan-report.txt`.

> **Repository privato.** Il Task clona `REPO_URL` senza altre credenziali, quindi per il repo Gitea del team passa l'URL con utente e password: `https://<nome-team>:techrace@<host-gitea>/<nome-team>/<nome-repo>.git`.

### Mailpit - server email di test

Nel tuo namespace è già in esecuzione **Mailpit**, un server SMTP di test. Le credenziali di accesso sono nel ConfigMap `team-info` del tuo namespace:

```bash
oc get configmap team-info -n <tuo-namespace> -o yaml
```

| Chiave ConfigMap | Descrizione |
|---|---|
| `MAILPIT_SMTP_HOST` | Host SMTP (es. `mailpit-smtp-<team>-ns.apps.<cluster>`) |
| `MAILPIT_SMTP_PORT` | Porta SMTP - sempre `443` (SMTPS, TLS implicito) |
| `MAILPIT_UI_URL` | URL dell'interfaccia web per leggere le email ricevute |
| `MAILPIT_USERNAME` | Username SMTP (il nome del tuo team) |
| `MAILPIT_PASSWORD` | Password SMTP (la stessa usata per il login OpenShift) |

> ⚠️ Mailpit usa un certificato TLS autofirmato. Il client SMTP deve disabilitare la verifica del certificato.

### Cosa deve contenere la Pipeline

La valutazione legge le Pipeline **dal tuo namespace OpenShift** (applica quindi la Pipeline con `oc apply`; il file nel repo è solo un ripiego) e controlla questi punti. I nomi della Pipeline, dei task e dei file sono liberi.

| # | Cosa deve esserci |
|---|---|
| 5B.1 | Una Pipeline con almeno un task che usa il Task preinstallato `bob-vulnerability-scan` tramite `taskRef` |
| 5B.2 | La stessa Pipeline ha il parametro `BOB_API_KEY` **e** un task che invia il report via SMTP |
| 5B.3 | Almeno un PipelineRun concluso con `Succeeded` |
| 5B.4 | Almeno un'email arrivata nel Mailpit del tuo namespace |

Sul task di invio email (5B.2):

- Puoi definirlo direttamente nella Pipeline (`taskSpec`) oppure come Task separato nel tuo namespace, richiamato con `taskRef`.
- Può essere scritto in qualunque linguaggio o strumento (Python con `smtplib`, `curl` con `smtps://`, ...): la valutazione cerca nello script, nel comando o nelle variabili del task l'uso di SMTP.
- Non usare un Task preso da un resolver remoto (hub, git): non se ne può leggere il contenuto. Definisci l'invio nella tua Pipeline o in un Task del tuo namespace.

### Scheletro di partenza

Lo scheletro collega il Task preinstallato alla Pipeline. Lo script di invio email è da scrivere tu.

```yaml
# tekton/pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: wareflow-security-scan
spec:
  params:
    - name: BOB_API_KEY
      type: string
    - name: REPO_URL
      type: string
    - name: GIT_REVISION
      type: string
      default: main
  workspaces:
    - name: scan-results
  tasks:
    - name: bob-security-scan
      taskRef:
        name: bob-vulnerability-scan     # Task preinstallato nel namespace
      params:
        - name: BOB_API_KEY
          value: $(params.BOB_API_KEY)
        - name: REPO_URL
          value: $(params.REPO_URL)
        - name: GIT_REVISION
          value: $(params.GIT_REVISION)
      workspaces:
        - name: output                   # il Task richiede un workspace chiamato "output"
          workspace: scan-results

    - name: send-report-email
      runAfter: [bob-security-scan]
      workspaces:
        - name: scan-results
          workspace: scan-results
      taskSpec:
        workspaces:
          - name: scan-results
        steps:
          - name: send
            image: python:3.12-slim
            # TODO: sostituisci lo script: deve leggere bob-scan-report.txt dal workspace
            # e inviarlo via SMTP alla tua istanza Mailpit (vedi sezione precedente)
            script: |
              #!/bin/sh
              ls -l "$(workspaces.scan-results.path)"
```

Host, porta e credenziali SMTP puoi leggerli dal ConfigMap `team-info` con `valueFrom.configMapKeyRef` (come variabili d'ambiente dello step) invece di copiarli a mano.

Per ottenere un PipelineRun `Succeeded`, avvia la Pipeline (ad esempio con `tkn pipeline start`) passando `BOB_API_KEY` e `REPO_URL` come parametri e collegando il workspace `scan-results` a un volume (ad esempio un `volumeClaimTemplate`). `BOB_API_KEY` si passa solo qui: non scriverla mai in un file del repo.

### Deliverable attesi

- [ ] Una Pipeline Tekton nel tuo namespace con un task che usa il Task preinstallato `bob-vulnerability-scan` (`taskRef`)
- [ ] La stessa Pipeline ha il parametro `BOB_API_KEY` e un task che invia il report via SMTP
- [ ] Almeno un PipelineRun concluso con `Succeeded`
- [ ] Almeno un'email con il report arrivata nel Mailpit del tuo namespace

**Bonus M5 (+5 pt)**: M5A e M5B completate entrambe in pieno (tutti i 20 punti base della milestone).

---

## Deliverable finali attesi

Al termine delle 2 ore, fornisci agli organizzatori:

1. **URL del repository Git** contenente il codice prodotto
2. **Namespace OpenShift** del tuo team
3. **URL della Route OpenShift**, se hai deployato l'app

### Struttura attesa del repository

```
<nome-repo>/
├── app/
│   ├── ...
├── main.py
├── requirements.txt
├── Containerfile
├── ARCHITECTURE.md
├── tests/
│   └── ...
└── tekton/
    └── pipeline.yaml
```

Questa è la struttura consigliata, non l'unica ammessa: i controlli cercano i file in tutto il repo. Vedi le regole qui sotto per ciò che invece è obbligatorio.

### Regole di consegna (necessarie per la valutazione automatica)

La valutazione è automatica e non può intuire le tue scelte: se una di queste regole non è rispettata, il punteggio della relativa voce può risultare 0 anche se il lavoro è corretto.

1. **Repository.** Consegna tutto nel repo Gitea del team (`GITEA_REPO_URL`), sul branch `main`. Viene valutato quello che c'è su `main` al termine della gara, non il tuo working directory.
2. **Il package dell'app.** I controlli sul grafo delle dipendenze (M1, M3) e sulla coverage (M2) cercano il package Python dell'app: va bene `app/` nella radice, `qualcosa/app/`, oppure un package con un altro nome (deve avere un `__init__.py`). Non mettere codice dell'app dentro `tests/` o in una cartella `venv/`.
3. **L'app si avvia da sola.** La valutazione costruisce l'immagine dal tuo `Containerfile`, avvia **un container nuovo** e lo interroga: `GET /warehouses` deve rispondere 200 con JSON, `POST /orders` e `POST /orders/{id}/confirm` devono funzionare con questi campi: `customer_name`, `lines[{sku, quantity}]`, e `POST /stock/{sku}/restock` con `quantity`. Non cambiare questi percorsi né i nomi dei campi.
4. **Test.** I test devono potersi lanciare con `pytest` dalla cartella che contiene l'app, con le dipendenze di `requirements*.txt`. La coverage di partenza è circa l'**8%**: serve almeno +30 punti percentuali (quindi circa il 38%).
5. **Concorrenza.** Il controllo M4 lancia 50 conferme ordine contemporanee sullo stesso articolo (`PALLET-BOX`). Una soluzione con un lock rende le conferme sequenziali: va bene, purché ogni richiesta risponda entro 30 secondi.
6. **Configurazione obbligatoria con default.** Il container viene avviato senza variabili d'ambiente. Se la tua app legge `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` o `WATSONX_URL` all'avvio, nella prova di Setup e nell'avvio di valutazione vengono passati valori segnaposto; per qualunque altra variabile obbligatoria, metti un valore di default.
7. **Segreti.** Mai nel repo: `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` e `BOB_API_KEY` vanno letti da Secret/variabili d'ambiente o passati come parametro del PipelineRun. Una chiave nel sorgente comporta la squalifica della milestone: vale per il codice Python, per i file di configurazione e `.env`, e anche per il `Containerfile` (nemmeno come `ENV WATSONX_API_KEY=valore` o `ARG`). Nell'immagine non va nessun valore: la chiave si passa quando avvii il container, ad esempio `podman run -e WATSONX_API_KEY=... -e WATSONX_PROJECT_ID=...`, e in OpenShift da un Secret.
8. **Pipeline Tekton.** Applica la Pipeline nel tuo namespace (la valutazione la legge da OpenShift; il file nel repo è solo un ripiego) e lancia almeno un PipelineRun fino a `Succeeded`. Il report deve arrivare nel Mailpit del tuo namespace.
9. **Non cancellare, a fine gara, le risorse del namespace** (Pipeline, PipelineRun e, se hai deployato l'app, Deployment e Route): la valutazione le legge dal cluster.
10. **Dati di test.** La valutazione crea ordini sul container che avvia lei, non sui tuoi servizi live.

---

## Ambiente disponibile

| Risorsa | Dettaglio |
|---------|-----------|
| IBM Bob | Installato e configurato nel tuo IDE |
| Tekton | Pre-installato sul cluster |
| Registry immagini | Interno a OpenShift, un namespace isolato per team - vedi "Accesso all'ambiente" |
| Gitea | Self-hosted sul cluster, un repo per team - vedi "Accesso all'ambiente" |
| Toolchain locale | Python 3.12 (la stessa versione dell'immagine base suggerita; le dipendenze dello starter richiedono almeno la 3.8, ma se aggiungi librerie nuove usa la 3.12 per non avere sorprese tra il tuo PC e il container), pip, Podman/Docker (CLI `oc` si scarica dalla console, vedi "Accesso all'ambiente") |

### Risorse pre-configurate nel tuo namespace

Queste risorse sono già presenti nel tuo namespace al momento del login - non devi crearle:

| Risorsa | Tipo | Contenuto |
|---------|------|-----------|
| `team-info` | ConfigMap | URL del cluster, Gitea, registry, credenziali Mailpit (vedi "Accesso all'ambiente") |
| `watsonx-credentials` | Secret | `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` - credenziali watsonx.ai per M5A |
| `bob-vulnerability-scan` | Tekton Task | Task IBM Bob Shell preinstallato, usato dalla pipeline in M5B |
| `mailpit` | Deployment + Route | Server SMTP di test per verificare l'invio email in M5B |

---

*Buona fortuna - e usa IBM Bob!*
