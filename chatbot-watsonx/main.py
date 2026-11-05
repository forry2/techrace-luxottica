"""
FastAPI backend per il chatbot watsonx AI.
Espone:
  GET  /        → pagina HTML del chatbot
  POST /chat    → endpoint API conversazione
  GET  /health  → health check
  GET  /orders  → lista ordini
  POST /orders  → crea un nuovo ordine
"""

import os
import sqlite3
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.watsonx_client import WatsonxClient

load_dotenv()

# ── Database ordini (SQLite in-memory) ───────────────────────────────────────

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            CREATE TABLE orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'DRAFT',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE order_lines (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sku      TEXT NOT NULL,
                quantity INTEGER NOT NULL
            );
        """)
        _conn.commit()
    return _conn


def _db_execute(sql: str, params: tuple = ()) -> int:
    with _db_lock:
        cur = _get_conn().execute(sql, params)
        _get_conn().commit()
        return cur.lastrowid  # type: ignore


def _db_query_all(sql: str, params: tuple = ()) -> list[dict]:
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _db_query_one(sql: str, params: tuple = ()) -> dict | None:
    with _db_lock:
        row = _get_conn().execute(sql, params).fetchone()
        return dict(row) if row else None


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot watsonx AI", version="1.0.0")

static_dir = Path(__file__).parent / "app" / "static"
if static_dir.exists() and any(static_dir.iterdir()):
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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


_FORM_SKUS = ", ".join(sorted({"WIDGET-1", "WIDGET-2", "PALLET-BOX"}))

_DEFAULT_SYSTEM_PROMPT = (
    "Sei un assistente AI per la gestione ordini, preciso e conciso. "
    "Rispondi sempre nella stessa lingua in cui ti viene posta la domanda."
)

_EXTRACT_SYSTEM_PROMPT = (
    "Sei un estrattore di dati. Analizza il testo e rispondi ESCLUSIVAMENTE con un oggetto JSON "
    "valido, senza markdown, senza commenti, senza testo aggiuntivo.\n"
    "Formato richiesto:\n"
    '{\"customer_name\": \"<nome cliente, stringa vuota se assente>\", '
    '\"lines\": [{\"sku\": \"<SKU>\", \"quantity\": <intero>}]}\n'
    f"SKU validi (usa SOLO questi): {_FORM_SKUS}.\n"
    "Se nel testo non c'è nessun ordine da creare, rispondi esattamente con: "
    '{\"customer_name\": \"\", \"lines\": []}'
)


class ChatRequest(BaseModel):
    messages: list[Message]
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT


class ChatResponse(BaseModel):
    reply: str
    form_data: dict | None = None


class OrderLine(BaseModel):
    sku: str
    quantity: int


class OrderRequest(BaseModel):
    customer_name: str
    lines: list[OrderLine]


# ── Helpers ordini ────────────────────────────────────────────────────────────

VALID_SKUS = {"WIDGET-1", "WIDGET-2", "PALLET-BOX"}


def _get_order(order_id: int) -> dict | None:
    order = _db_query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if order is None:
        return None
    lines = _db_query_all(
        "SELECT sku, quantity FROM order_lines WHERE order_id = ?", (order_id,)
    )
    order["lines"] = lines
    return order


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": os.environ.get("WATSONX_MODEL_ID", "openai/gpt-oss-120b")}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Invia la cronologia al modello e restituisce la risposta.
    Se l'ultimo messaggio utente descrive un ordine, esegue una seconda chiamata
    di estrazione e restituisce anche form_data con customer_name e lines.
    """
    import json as _json

    client = get_client()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        reply = client.chat(messages=messages, system_prompt=request.system_prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Estrazione strutturata (seconda chiamata) ──────────────────────────────
    # Prendiamo l'ultimo messaggio utente come testo da analizzare
    user_text = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    form_data = None
    if user_text:
        try:
            raw_json = client.chat(
                messages=[{"role": "user", "content": user_text}],
                system_prompt=_EXTRACT_SYSTEM_PROMPT,
            )
            # Pulizia backtick/markdown che il modello potrebbe aggiungere
            cleaned = raw_json.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()
            extracted = _json.loads(cleaned)
            lines = [
                {"sku": str(l.get("sku", "")).strip(), "quantity": int(l.get("quantity", 1))}
                for l in extracted.get("lines", [])
                if str(l.get("sku", "")).strip() in VALID_SKUS and int(l.get("quantity", 1)) >= 1
            ]
            if lines or extracted.get("customer_name", "").strip():
                form_data = {
                    "customer_name": str(extracted.get("customer_name", "")).strip(),
                    "lines": lines,
                }
        except Exception:
            pass  # estrazione fallita — non blocca la chat

    return ChatResponse(reply=reply, form_data=form_data)


@app.get("/orders")
def list_orders():
    """Restituisce la lista di tutti gli ordini con le loro righe."""
    orders = _db_query_all(
        "SELECT id, customer_name, status, created_at FROM orders ORDER BY id DESC"
    )
    result = []
    for o in orders:
        full = _get_order(o["id"])
        if full:
            result.append(full)
    return result


@app.post("/orders", status_code=201)
def create_order(request: OrderRequest):
    """Crea un nuovo ordine in stato DRAFT."""
    if not request.customer_name.strip():
        raise HTTPException(status_code=422, detail="Il nome del cliente è obbligatorio")
    if not request.lines:
        raise HTTPException(status_code=422, detail="L'ordine deve contenere almeno una riga")
    for line in request.lines:
        if line.sku not in VALID_SKUS:
            raise HTTPException(
                status_code=422,
                detail=f"SKU '{line.sku}' non valido. SKU disponibili: {', '.join(sorted(VALID_SKUS))}",
            )
        if line.quantity < 1:
            raise HTTPException(status_code=422, detail="La quantità deve essere almeno 1")

    order_id = _db_execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, 'DRAFT')",
        (request.customer_name.strip(),),
    )
    for line in request.lines:
        _db_execute(
            "INSERT INTO order_lines (order_id, sku, quantity) VALUES (?, ?, ?)",
            (order_id, line.sku, line.quantity),
        )
    order = _get_order(order_id)
    return order


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve la pagina HTML del chatbot."""
    template_path = Path(__file__).parent / "app" / "templates" / "index.html"
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
