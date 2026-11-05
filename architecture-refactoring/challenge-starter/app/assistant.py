"""
Blueprint Flask per il chatbot watsonx AI.
Espone:
  GET  /            → pagina HTML del chatbot
  POST /chat        → endpoint conversazione (chatbot)
  POST /assistant   → endpoint M5A (domanda in linguaggio naturale)
"""

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from app import db, warehouse
from app.watsonx_client import WatsonxClient

bp = Blueprint("assistant", __name__)

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
    '{"customer_name": "<nome cliente, stringa vuota se assente>", '
    '"lines": [{"sku": "<SKU>", "quantity": <intero>}]}\n'
    f"SKU validi (usa SOLO questi): {_FORM_SKUS}.\n"
    "Se nel testo non c'è nessun ordine da creare, rispondi esattamente con: "
    '{"customer_name": "", "lines": []}'
)

_client: WatsonxClient | None = None


def _get_client() -> WatsonxClient:
    global _client
    if _client is None:
        _client = WatsonxClient()
    return _client


def _get_warehouse_context() -> str:
    """Costruisce un riepilogo testuale dello stato del magazzino da passare al modello."""
    warehouses = db.query_all("SELECT id, name, city FROM warehouses ORDER BY id")
    stock_rows = db.query_all("SELECT sku, warehouse_id, quantity FROM stock ORDER BY sku, warehouse_id")
    orders = db.query_all(
        "SELECT id, customer_name, status, created_at FROM orders ORDER BY id DESC LIMIT 20"
    )
    shipments = db.query_all(
        "SELECT id, order_id, warehouse_id, tracking_code, status FROM shipments ORDER BY id DESC LIMIT 20"
    )

    wh_map = {w["id"]: w["name"] for w in warehouses}

    lines = ["=== STATO MAGAZZINO WareFlow ===\n"]

    lines.append("-- Magazzini --")
    for w in warehouses:
        lines.append(f"  #{w['id']} {w['name']} ({w['city']})")

    lines.append("\n-- Stock --")
    for s in stock_rows:
        wh_name = wh_map.get(s["warehouse_id"], f"#{s['warehouse_id']}")
        lines.append(f"  {s['sku']} @ {wh_name}: {s['quantity']} unità")

    lines.append("\n-- Ultimi ordini (max 20) --")
    if orders:
        for o in orders:
            lines.append(f"  #{o['id']} {o['customer_name']} — {o['status']} ({o['created_at']})")
    else:
        lines.append("  Nessun ordine.")

    lines.append("\n-- Ultime spedizioni (max 20) --")
    if shipments:
        for s in shipments:
            wh_name = wh_map.get(s["warehouse_id"], f"#{s['warehouse_id']}")
            lines.append(
                f"  #{s['id']} ordine #{s['order_id']} — {wh_name} — {s['tracking_code']} ({s['status']})"
            )
    else:
        lines.append("  Nessuna spedizione.")

    return "\n".join(lines)


@bp.get("/")
def index():
    """Serve la pagina HTML del chatbot."""
    return render_template("index.html")


@bp.post("/chat")
def chat():
    """
    Invia la cronologia al modello e restituisce la risposta.
    Se l'ultimo messaggio utente descrive un ordine, esegue una seconda chiamata
    di estrazione e restituisce anche form_data con customer_name e lines.
    """
    body = request.get_json(silent=True) or {}
    messages = body.get("messages", [])
    system_prompt = body.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)

    client = _get_client()
    try:
        reply = client.chat(messages=messages, system_prompt=system_prompt)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    # Estrazione strutturata (seconda chiamata) per pre-popolare il form ordine
    user_text = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
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
            extracted = json.loads(cleaned)
            valid_skus = {"WIDGET-1", "WIDGET-2", "PALLET-BOX"}
            lines = [
                {"sku": str(l.get("sku", "")).strip(), "quantity": int(l.get("quantity", 1))}
                for l in extracted.get("lines", [])
                if str(l.get("sku", "")).strip() in valid_skus and int(l.get("quantity", 1)) >= 1
            ]
            if lines or extracted.get("customer_name", "").strip():
                form_data = {
                    "customer_name": str(extracted.get("customer_name", "")).strip(),
                    "lines": lines,
                }
        except Exception:
            pass  # estrazione fallita — non blocca la chat

    return jsonify({"reply": reply, "form_data": form_data})


@bp.post("/assistant")
def assistant():
    """
    Endpoint M5A: risponde in linguaggio naturale a domande sul magazzino.
    Body: {"question": "..."}
    """
    body = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    context = _get_warehouse_context()
    system_prompt = (
        "Sei un assistente AI per la gestione magazzino WareFlow. "
        "Rispondi in linguaggio naturale, in modo preciso e conciso, basandoti ESCLUSIVAMENTE "
        "sui dati reali del magazzino che ti vengono forniti. "
        "Rispondi nella stessa lingua della domanda."
    )
    messages = [
        {"role": "user", "content": f"{context}\n\nDomanda: {question}"},
    ]

    client = _get_client()
    try:
        answer = client.chat(messages=messages, system_prompt=system_prompt)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"answer": answer})
