"""
Blueprint Flask per il chatbot watsonx AI.
Espone:
  GET  /            → pagina HTML del chatbot
  POST /chat        → endpoint conversazione (chatbot con tool-calling)
  POST /assistant   → endpoint M5A (domanda in linguaggio naturale)
"""

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from app import db, orders, shipping, warehouse
from app.watsonx_client import WatsonxClient

bp = Blueprint("assistant", __name__)

_FORM_SKUS = ", ".join(sorted({"WIDGET-1", "WIDGET-2", "PALLET-BOX"}))

_DEFAULT_SYSTEM_PROMPT = (
    "Sei un assistente AI per la gestione magazzino WareFlow, preciso e conciso. "
    "Puoi aiutare con ordini, stock, magazzini e spedizioni. "
    "Rispondi SEMPRE basandoti ESCLUSIVAMENTE sui dati reali del magazzino che ti vengono forniti nel contesto. "
    "Non inventare dati e non chiedere chiarimenti su quale sistema usare: i dati sono già inclusi nel contesto. "
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

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_orders",
            "description": (
                "Restituisce la lista di tutti gli ordini nel sistema, con id, cliente, "
                "stato e data di creazione."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Restituisce i dettagli di un singolo ordine (righe incluse) dato il suo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "L'ID numerico dell'ordine.",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_warehouses",
            "description": "Restituisce la lista di tutti i magazzini con id, nome e città.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": (
                "Restituisce lo stock disponibile. Se viene fornito uno SKU specifico, "
                "restituisce solo la quantità per quello SKU; altrimenti restituisce "
                "tutto lo stock per tutti gli SKU presenti nel DB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "SKU del prodotto (opzionale). Esempi: WIDGET-1, WIDGET-2, PALLET-BOX.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customers",
            "description": (
                "Restituisce la lista dei clienti distinti che hanno effettuato almeno un ordine, "
                "con il numero totale di ordini per cliente."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shipments",
            "description": (
                "Restituisce la lista di tutte le spedizioni con id, ordine associato, "
                "magazzino, tracking code e stato."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 5  # prevent infinite loops


def _execute_tool(name: str, arguments: dict) -> str:
    """Esegue il tool richiesto dal modello e restituisce il risultato come stringa JSON."""
    try:
        if name == "get_orders":
            result = orders.list_orders()
            return json.dumps(result, ensure_ascii=False)

        if name == "get_order":
            order_id = int(arguments.get("order_id", 0))
            result = orders.get_order(order_id)
            if result is None:
                return json.dumps({"error": f"Ordine #{order_id} non trovato."}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)

        if name == "get_warehouses":
            result = warehouse.list_warehouses()
            return json.dumps(result, ensure_ascii=False)

        if name == "get_stock":
            sku = arguments.get("sku", "").strip()
            if sku:
                qty = warehouse.get_stock(sku)
                return json.dumps({"sku": sku, "quantity": qty}, ensure_ascii=False)
            rows = db.query_all("SELECT sku, warehouse_id, quantity FROM stock ORDER BY sku, warehouse_id")
            return json.dumps(rows, ensure_ascii=False)

        if name == "get_customers":
            rows = db.query_all(
                "SELECT customer_name, COUNT(*) AS total_orders "
                "FROM orders GROUP BY customer_name ORDER BY customer_name"
            )
            return json.dumps(rows, ensure_ascii=False)

        if name == "get_shipments":
            result = shipping.list_shipments()
            return json.dumps(result, ensure_ascii=False)

    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    return json.dumps({"error": f"Tool '{name}' non riconosciuto."}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    all_orders = db.query_all(
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
    if all_orders:
        for o in all_orders:
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.get("/")
def index():
    """Serve la pagina HTML del chatbot."""
    return render_template("index.html")


@bp.post("/chat")
def chat():
    """
    Invia la cronologia al modello.
    Il system prompt include sempre il contesto aggiornato del magazzino (ordini, stock,
    magazzini, spedizioni) in modo che il bot possa rispondere con dati reali.
    Se il modello supporta il function-calling, usa i tool come canale alternativo;
    altrimenti ha già tutto nel contesto.
    Restituisce anche form_data se l'utente descrive un ordine da creare.
    """
    body = request.get_json(silent=True) or {}
    messages = body.get("messages", [])
    base_prompt = body.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)

    # Inietta sempre il contesto aggiornato nel system prompt
    context = _get_warehouse_context()
    system_prompt = f"{base_prompt}\n\n{context}"

    client = _get_client()

    # --- Tool-calling loop ---
    # Tentiamo il function-calling; se il modello non supporta i tool_calls,
    # risponde direttamente con content (che è già arricchito dal contesto).
    working_messages = list(messages)
    reply = ""

    try:
        for _ in range(_MAX_TOOL_ROUNDS):
            msg = client.chat_with_tools(
                messages=working_messages,
                tools=_TOOLS,
                system_prompt=system_prompt,
            )

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                # Risposta testuale finale (diretta o dopo tool loop)
                reply = msg.get("content", "")
                break

            # Aggiungi il messaggio assistant con i tool_calls alla history di lavoro
            working_messages.append(msg)

            # Esegui tutti i tool richiesti e aggiungi i risultati
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"].get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result = _execute_tool(tool_name, tool_args)
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
        else:
            reply = "Limite di iterazioni raggiunto. Riprova con una domanda più specifica."

    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    # --- Estrazione strutturata (seconda chiamata) per pre-popolare il form ordine ---
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
