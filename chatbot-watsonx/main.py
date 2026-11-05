"""
FastAPI backend per il chatbot watsonx AI.
Espone:
  GET  /          → pagina HTML del chatbot
  POST /chat      → endpoint API conversazione
  GET  /health    → health check
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.watsonx_client import WatsonxClient

load_dotenv()

app = FastAPI(title="Chatbot watsonx AI", version="1.0.0")

# Mount static files solo se la directory contiene almeno un file
static_dir = Path(__file__).parent / "app" / "static"
if static_dir.exists() and any(static_dir.iterdir()):
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Istanza condivisa del client watsonx
_client: WatsonxClient | None = None


def get_client() -> WatsonxClient:
    global _client
    if _client is None:
        _client = WatsonxClient()
    return _client


# ── Modelli Pydantic ──────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str   # "user" o "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    system_prompt: str = (
        "Sei un assistente AI utile, preciso e conciso. "
        "Rispondi sempre nella stessa lingua in cui ti viene posta la domanda."
    )


class ChatResponse(BaseModel):
    reply: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": os.environ.get("WATSONX_MODEL_ID", "openai/gpt-oss-120b")}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Invia la cronologia dei messaggi al modello e restituisce la risposta."""
    client = get_client()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        reply = client.chat(messages=messages, system_prompt=request.system_prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return ChatResponse(reply=reply)


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve la pagina HTML del chatbot."""
    template_path = Path(__file__).parent / "app" / "templates" / "index.html"
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
