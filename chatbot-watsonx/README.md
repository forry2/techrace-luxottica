# Chatbot watsonx AI

Agente conversazionale basato su **IBM watsonx AI** (modello `openai/gpt-oss-120b`) con interfaccia web integrata, costruito con **FastAPI**.

---

## Struttura del progetto

```
chatbot-watsonx/
├── main.py                    # Entry point FastAPI
├── requirements.txt
├── .env.example               # Template credenziali (copiare in .env)
└── app/
    ├── watsonx_client.py      # Client IBM watsonx AI (autenticazione IAM + chat)
    ├── templates/
    │   └── index.html         # Interfaccia chatbot
    └── static/                # Asset CSS/JS aggiuntivi (opzionale)
```

---

## Setup

### 1. Clona e installa le dipendenze

```bash
cd chatbot-watsonx
pip install -r requirements.txt
```

### 2. Configura le credenziali

Copia il file di esempio e inserisci le tue credenziali IBM Cloud:

```bash
cp .env.example .env
```

Apri `.env` e compila:

```env
WATSONX_API_KEY=<la_tua_ibm_cloud_api_key>
WATSONX_PROJECT_ID=<il_tuo_watsonx_project_id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=openai/gpt-oss-120b
```

> **Come trovare le credenziali:**
> - **API Key**: IBM Cloud → Gestisci → Accesso (IAM) → Chiavi API
> - **Project ID**: [watsonx.ai](https://dataplatform.cloud.ibm.com) → progetto → Gestisci → Generale → ID progetto

### 3. Avvia il server

```bash
uvicorn main:app --reload
```

L'app sarà disponibile su **http://localhost:8000**

---

## Endpoints API

| Metodo | Path      | Descrizione                              |
|--------|-----------|------------------------------------------|
| `GET`  | `/`       | Interfaccia web del chatbot              |
| `POST` | `/chat`   | API conversazione (JSON)                 |
| `GET`  | `/health` | Health check + modello attivo            |
| `GET`  | `/docs`   | Documentazione interattiva Swagger UI    |

### Esempio chiamata `/chat`

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Ciao, chi sei?"}
    ]
  }'
```

**Risposta:**
```json
{
  "reply": "Ciao! Sono un assistente AI powered by IBM watsonx..."
}
```

---

## Personalizzare il system prompt

Puoi passare un `system_prompt` personalizzato nel body della richiesta:

```json
{
  "messages": [{"role": "user", "content": "Come funziona la fotosintesi?"}],
  "system_prompt": "Sei un esperto di biologia. Rispondi in modo semplice per bambini."
}
```

---

## Note

- Il token IAM IBM Cloud ha una durata di **1 ora**. Il client lo rinnova automaticamente in caso di risposta `401`.
- Configura solo **un modello core** alla volta in watsonx AI.
- Per ambienti di produzione, usa un secret manager (es. HashiCorp Vault, IBM Secrets Manager) invece del file `.env`.
