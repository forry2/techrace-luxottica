# Piano M5B — Pipeline Tekton: security scan + email report

## Panoramica

Creare una Pipeline Tekton nel namespace OpenShift del team che:
1. Usa il Task preinstallato `bob-vulnerability-scan` per scansionare il repository
2. Invia il report risultante (`bob-scan-report.txt`) via SMTP a Mailpit
3. Viene eseguita almeno una volta con successo (PipelineRun Succeeded)

Il file YAML va committato nel repo sotto `tekton/pipeline.yaml`
(il valutatore cerca prima nel namespace, poi nel repo come fallback).

**Criteri di valutazione (da `check_m5.sh`):**
- **5B.1** (2pt) — Pipeline ha un task che referenzia `bob-vulnerability-scan` come `taskRef`
- **5B.2** (5pt) — Pipeline ha il parametro `BOB_API_KEY` + un task che usa SMTP
  (il valutatore cerca: `smtplib`, `smtp_ssl`, `SMTP_HOST`, `MAILPIT_SMTP`, `smtps://`, `sendmail`)
- **5B.3** (1pt) — Almeno un PipelineRun con `conditions[type=Succeeded, status=True]`
- **5B.4** (2pt) — Almeno un messaggio in Mailpit (`GET /api/v1/messages?limit=50`)

---

## Sub-Task 1 — Scrivere `tekton/pipeline.yaml`

**Status:** [ ] pending

### Intent
Creare il file Pipeline Tekton con i due task richiesti:
- `bob-security-scan` via `taskRef: bob-vulnerability-scan`
- `send-report-email` con `taskSpec` inline contenente uno script Python che:
  - legge `bob-scan-report.txt` dal workspace condiviso
  - lo invia via SMTP a Mailpit usando `smtplib.SMTP_SSL`
  - legge host/porta/credenziali dal ConfigMap `team-info` via `env[].valueFrom.configMapKeyRef`

### Expected Outcomes
- File `tekton/pipeline.yaml` presente nel repo
- Contiene `kind: Pipeline`
- Contiene `taskRef.name: bob-vulnerability-scan`
- Contiene il parametro `BOB_API_KEY` a livello di Pipeline spec
- Lo script del task email contiene `smtplib` (o pattern SMTP riconoscibile dal valutatore)
- I segreti SMTP non sono hardcodati: vengono letti dal ConfigMap `team-info`

### Todo List
1. Creare la directory `tekton/` nella root del challenge-starter (o nella root del repo)
2. Scrivere `tekton/pipeline.yaml` con:
   - `spec.params`: `BOB_API_KEY`, `REPO_URL`, `GIT_REVISION` (default: main)
   - `spec.workspaces`: `scan-results`
   - Task 1 `bob-security-scan`: taskRef + params + workspace `output → scan-results`
   - Task 2 `send-report-email`: taskSpec inline, `runAfter: [bob-security-scan]`
     - image: `python:3.12-slim`
     - env vars da ConfigMap `team-info`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `FROM_ADDR`, `TO_ADDR`
     - script Python con `smtplib.SMTP_SSL`, `context.check_hostname=False`, `context.verify_mode=ssl.CERT_NONE`
3. Commit e push del file

### Relevant Context
- Scheletro del task nel brief: `track2-brief.md` righe 341-389
- Workspace condiviso si chiama `scan-results`; il Task preinstallato lo mappa su `output`
- Il valutatore SMTP cerca (riga 140 di `check_m5.sh`):
  `smtplib|smtp_ssl|SMTP_HOST|MAILPIT_SMTP|smtps?://|sendmail|swaks|mailx`
- Il valutatore inline (riga 170) cerca anche nelle `env[].name` la parola `smtp`
- Mailpit usa TLS autofirmato su porta 443 → necessario `ssl.CERT_NONE`
- `BOB_API_KEY` non va mai scritto nel file: va passato solo al `PipelineRun`

---

## Sub-Task 2 — Applicare la Pipeline al namespace OpenShift

**Status:** [ ] pending

### Intent
Fare `oc apply` del file prodotto nel sub-task 1, in modo che la Pipeline
sia nel namespace e il valutatore la trovi direttamente tramite `oc get pipeline`.

### Expected Outcomes
- `oc get pipeline -n <namespace>` mostra `wareflow-security-scan`
- `oc get pipeline wareflow-security-scan -n <namespace> -o yaml` mostra il contenuto corretto

### Todo List
1. Recuperare il namespace del team:
   ```bash
   oc get configmap team-info -n <namespace> -o jsonpath='{.data.NAMESPACE}'
   ```
2. Applicare la Pipeline:
   ```bash
   oc apply -f tekton/pipeline.yaml -n <namespace>
   ```
3. Verificare con `oc get pipeline -n <namespace>`

### Relevant Context
- Namespace formato: `<nome-team>-ns` (es. `team-luxottica-ns`)
- Il valutatore usa `oc get pipeline -n "$NAMESPACE" -o json`

---

## Sub-Task 3 — Eseguire la Pipeline (PipelineRun)

**Status:** [ ] pending

### Intent
Avviare un PipelineRun che passi `BOB_API_KEY` e `REPO_URL` come parametri,
collegando il workspace `scan-results` a un `volumeClaimTemplate`.

### Expected Outcomes
- Almeno un PipelineRun nel namespace con `conditions[type=Succeeded, status=True]`
- Task 1 (`bob-security-scan`) ha prodotto `bob-scan-report.txt` nel workspace
- Task 2 (`send-report-email`) ha inviato il report a Mailpit
- Almeno un messaggio visibile nell'interfaccia Mailpit (`MAILPIT_UI_URL`)

### Todo List
1. Recuperare i valori dal ConfigMap:
   ```bash
   oc get configmap team-info -n <namespace> -o jsonpath='{.data.GITEA_REPO_URL}'
   ```
2. Avviare il PipelineRun con `tkn` o `oc`:
   ```bash
   tkn pipeline start wareflow-security-scan \
     -n <namespace> \
     -p BOB_API_KEY=<la-tua-api-key> \
     -p REPO_URL=https://<team>:techrace@<host-gitea>/<team>/<repo>.git \
     -p GIT_REVISION=main \
     -w name=scan-results,volumeClaimTemplateFile=- <<EOF
   apiVersion: v1
   kind: PersistentVolumeClaim
   spec:
     accessModes: [ReadWriteOnce]
     resources:
       requests:
         storage: 500Mi
   EOF
   ```
3. Monitorare l'esecuzione:
   ```bash
   tkn pipelinerun logs -f -n <namespace>
   ```
4. Verificare il completamento:
   ```bash
   oc get pipelinerun -n <namespace>
   ```
5. Verificare l'email in Mailpit aprendo `MAILPIT_UI_URL` nel browser

### Relevant Context
- `BOB_API_KEY` va passato solo qui, mai scritto nel file YAML del repo
- URL Gitea con credenziali: `https://<nome-team>:techrace@<host-gitea>/<nome-team>/<nome-repo>.git`
- Il valutatore controlla PipelineRun con `conditions[type=Succeeded, status=True]`
- Il valutatore controlla Mailpit con `GET <MAILPIT_UI_URL>/api/v1/messages?limit=50`

---

## Note tecniche chiave

### Script Python per l'invio email (da includere nel taskSpec)
```python
#!/usr/bin/env python3
import os, ssl, smtplib
from email.message import EmailMessage

workspace = os.environ.get("WORKSPACE_PATH", "/workspace/scan-results")
report_path = os.path.join(workspace, "bob-scan-report.txt")

with open(report_path) as f:
    body = f.read()

msg = EmailMessage()
msg["Subject"] = "WareFlow Security Scan Report"
msg["From"] = os.environ["SMTP_USER"]
msg["To"] = os.environ["SMTP_USER"]
msg.set_content(body)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), context=ctx) as s:
    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    s.send_message(msg)

print("Email inviata con successo")
```

### Variabili d'ambiente dallo step (da ConfigMap)
```yaml
env:
  - name: SMTP_HOST
    valueFrom:
      configMapKeyRef:
        name: team-info
        key: MAILPIT_SMTP_HOST
  - name: SMTP_PORT
    valueFrom:
      configMapKeyRef:
        name: team-info
        key: MAILPIT_SMTP_PORT
  - name: SMTP_USER
    valueFrom:
      configMapKeyRef:
        name: team-info
        key: MAILPIT_USERNAME
  - name: SMTP_PASS
    valueFrom:
      configMapKeyRef:
        name: team-info
        key: MAILPIT_PASSWORD
  - name: WORKSPACE_PATH
    value: $(workspaces.scan-results.path)
```

### Cosa controlla il valutatore (da `check_m5.sh`)
| Check | Come viene rilevato |
|---|---|
| 5B.1 taskRef | `taskRef.name == "bob-vulnerability-scan"` nel JSON della Pipeline |
| 5B.2 BOB_API_KEY | `"BOB_API_KEY" in params` della Pipeline spec |
| 5B.2 SMTP | cerca `smtp` nel `script`, `args`, `command` degli step, o nelle `env[].name` |
| 5B.3 PipelineRun | `conditions[type=Succeeded, status=True]` nel namespace |
| 5B.4 Email | `GET <MAILPIT_UI_URL>/api/v1/messages?limit=50` ritorna `total >= 1` |
