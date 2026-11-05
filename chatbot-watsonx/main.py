"""
FastAPI backend per il chatbot watsonx AI.
Espone:
  GET  /            → pagina HTML del chatbot
  POST /chat        → endpoint API conversazione
  GET  /health      → health check
  GET  /warehouses  → lista magazzini
  GET  /stock/{sku} → disponibilità SKU
  POST /stock/{sku}/restock → rifornimento SKU
  GET  /orders      → lista ordini
  POST /orders      → crea un nuovo ordine
  GET  /orders/{id} → dettaglio ordine
  POST /orders/{id}/confirm → conferma ordine
  POST /orders/{id}/cancel  → annulla ordine
  GET  /shipments   → lista spedizioni
"""

import os
import sqlite3
import threading
import random
import string
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.watsonx_client import WatsonxClient

load_dotenv()

# ── Database (SQLite in-memory) ───────────────────────────────────────────────

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            CREATE TABLE warehouses (
                id   INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL
            );
            INSERT INTO warehouses VALUES (1, 'Milano Nord', 'Milano');
            INSERT INTO warehouses VALUES (2, 'Bologna Est', 'Bologna');
            INSERT INTO warehouses VALUES (3, 'Torino Sud',  'Torino');

            CREATE TABLE stock (
                sku         TEXT PRIMARY KEY,
                quantity    INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO stock VALUES ('WIDGET-1',  1000);
            INSERT INTO stock VALUES ('WIDGET-2',  800);
            INSERT INTO stock VALUES ('PALLET-BOX', 500);

            CREATE TABLE orders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'DRAFT',
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE order_lines (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sku      TEXT NOT NULL,
                quantity INTEGER NOT NULL
            );

            CREATE TABLE shipments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id      INTEGER NOT NULL,
                warehouse_id  INTEGER NOT NULL DEFAULT 1,
                tracking_code TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'PENDING'
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


# ── Stock lock (serializza decrementi concorrenti) ────────────────────────────

_stock_lock = threading.Lock()


def _decrement_stock(sku: str, qty: int) -> int:
    """Decrementa atomicamente lo stock. Restituisce la quantità dopo il decremento."""
    with _stock_lock:
        row = _db_query_one("SELECT quantity FROM stock WHERE sku = ?", (sku,))
        current = row["quantity"] if row else 0
        if current < qty:
            raise ValueError(f"not enough stock for {sku}: have {current}, need {qty}")
        new_qty = current - qty
        with _db_lock:
            _get_conn().execute("UPDATE stock SET quantity = ? WHERE sku = ?", (new_qty, sku))
            _get_conn().commit()
        return new_qty


def _generate_tracking() -> str:
    chars = string.ascii_uppercase + string.digits
    return "WF-" + "".join(random.choices(chars, k=8))


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
    "Sei un assistente AI per la gestione magazzino WareFlow, preciso e conciso. "
    "Puoi aiutare con ordini, stock, magazzini e spedizioni. "
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


class RestockRequest(BaseModel):
    quantity: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Warehouses ────────────────────────────────────────────────────────────────

@app.get("/warehouses")
def list_warehouses():
    """Restituisce la lista dei magazzini."""
    return _db_query_all("SELECT id, name, city FROM warehouses ORDER BY id")


# ── Stock ─────────────────────────────────────────────────────────────────────

@app.get("/stock/{sku}")
def get_stock(sku: str):
    """Disponibilità attuale di un articolo per SKU."""
    row = _db_query_one("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    return {"sku": sku, "quantity": row["quantity"] if row else 0}


@app.post("/stock/{sku}/restock")
def restock(sku: str, body: RestockRequest = RestockRequest()):
    """Aggiunge disponibilità a uno SKU."""
    with _stock_lock:
        existing = _db_query_one("SELECT quantity FROM stock WHERE sku = ?", (sku,))
        if existing:
            new_qty = existing["quantity"] + body.quantity
            with _db_lock:
                _get_conn().execute("UPDATE stock SET quantity = ? WHERE sku = ?", (new_qty, sku))
                _get_conn().commit()
        else:
            new_qty = body.quantity
            with _db_lock:
                _get_conn().execute("INSERT INTO stock (sku, quantity) VALUES (?, ?)", (sku, new_qty))
                _get_conn().commit()
    return {"sku": sku, "quantity": new_qty}


# ── Orders ────────────────────────────────────────────────────────────────────

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
    return _get_order(order_id)


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    """Dettaglio di un ordine con righe."""
    order = _get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    return order


@app.post("/orders/{order_id}/confirm")
def confirm_order(order_id: int):
    """Conferma l'ordine: scala lo stock e genera la spedizione."""
    order = _get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    if order["status"] != "DRAFT":
        raise HTTPException(
            status_code=400,
            detail=f"order {order_id} is already {order['status']}, cannot confirm",
        )

    # Decrementa stock per ogni riga
    try:
        for line in order["lines"]:
            _decrement_stock(line["sku"], line["quantity"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Aggiorna stato ordine
    _db_execute("UPDATE orders SET status = 'CONFIRMED' WHERE id = ?", (order_id,))

    # Crea spedizione
    tracking = _generate_tracking()
    shipment_id = _db_execute(
        "INSERT INTO shipments (order_id, warehouse_id, tracking_code, status) VALUES (?, 1, ?, 'PENDING')",
        (order_id, tracking),
    )

    order = _get_order(order_id)
    shipment = _db_query_one("SELECT * FROM shipments WHERE id = ?", (shipment_id,))
    order["shipment"] = dict(shipment)
    return order


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int):
    """Annulla un ordine in stato DRAFT."""
    order = _get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    if order["status"] != "DRAFT":
        raise HTTPException(
            status_code=400,
            detail=f"order {order_id} is already {order['status']}, cannot cancel",
        )
    _db_execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
    return _get_order(order_id)


# ── Shipments ─────────────────────────────────────────────────────────────────

@app.get("/shipments")
def list_shipments():
    """Restituisce la lista di tutte le spedizioni."""
    return _db_query_all(
        "SELECT id, order_id, warehouse_id, tracking_code, status FROM shipments ORDER BY id DESC"
    )


# ── HTML ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    """Serve la pagina HTML del chatbot."""
    template_path = Path(__file__).parent / "app" / "templates" / "index.html"
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
