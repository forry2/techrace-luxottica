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

_VALID_SKUS = {"WIDGET-1", "WIDGET-2", "PALLET-BOX"}
_FORM_SKUS = ", ".join(sorted(_VALID_SKUS))

_DEFAULT_SYSTEM_PROMPT = (
    "Sei un assistente AI per la gestione magazzino WareFlow, preciso e conciso. "
    "Puoi aiutare con ordini, stock, magazzini e spedizioni. "
    "Quando l'utente chiede informazioni su ordini, clienti, magazzini, stock o spedizioni, "
    "usa SEMPRE i tool disponibili per recuperare i dati aggiornati dal sistema. "
    "Quando l'utente vuole creare un ordine o aggiungere un cliente con articoli, "
    "usa SEMPRE lo strumento create_order per crearlo direttamente nel sistema. "
    "Quando l'utente vuole aggiungere stock, usa lo strumento restock_sku. "
    "Non inventare dati: usa i tool per ottenerli. "
    f"SKU disponibili: {_FORM_SKUS}. "
    "Rispondi sempre nella stessa lingua in cui ti viene posta la domanda."
)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

_TOOLS = [
    # ── Tool di lettura ──────────────────────────────────────────────────────
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
    # ── Tool di scrittura ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": (
                "Crea un nuovo ordine nel sistema WareFlow con un cliente e le righe articolo. "
                "Usare quando l'utente vuole creare un ordine o aggiungere un cliente con articoli."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Nome del cliente per cui creare l'ordine.",
                    },
                    "lines": {
                        "type": "array",
                        "description": "Righe dell'ordine con SKU e quantità.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {
                                    "type": "string",
                                    "enum": sorted(_VALID_SKUS),
                                    "description": "Codice SKU del prodotto.",
                                },
                                "quantity": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "Quantità da ordinare.",
                                },
                            },
                            "required": ["sku", "quantity"],
                        },
                    },
                },
                "required": ["customer_name", "lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restock_sku",
            "description": "Aggiunge quantità a uno SKU nel magazzino.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "enum": sorted(_VALID_SKUS),
                        "description": "Codice SKU da rifornire.",
                    },
                    "quantity": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Quantità da aggiungere allo stock.",
                    },
                },
                "required": ["sku", "quantity"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 5  # prevent infinite loops


def _execute_tool(name: str, arguments: dict) -> tuple[str, bool]:
    """
    Esegue il tool richiesto dal modello.

    Returns:
        (result_json, is_write_action) — il secondo valore è True se il tool
        ha modificato lo stato del sistema (ordine creato, stock aggiornato).
    """
    try:
        # ── Tool di lettura ──────────────────────────────────────────────────
        if name == "get_orders":
            result = orders.list_orders()
            return json.dumps(result, ensure_ascii=False), False

        if name == "get_order":
            order_id = int(arguments.get("order_id", 0))
            result = orders.get_order(order_id)
            if result is None:
                return json.dumps({"error": f"Ordine #{order_id} non trovato."}, ensure_ascii=False), False
            return json.dumps(result, ensure_ascii=False), False

        if name == "get_warehouses":
            result = warehouse.list_warehouses()
            return json.dumps(result, ensure_ascii=False), False

        if name == "get_stock":
            sku = arguments.get("sku", "").strip()
            if sku:
                qty = warehouse.get_stock(sku)
                return json.dumps({"sku": sku, "quantity": qty}, ensure_ascii=False), False
            rows = db.query_all("SELECT sku, warehouse_id, quantity FROM stock ORDER BY sku, warehouse_id")
            return json.dumps(rows, ensure_ascii=False), False

        if name == "get_customers":
            rows = db.query_all(
                "SELECT customer_name, COUNT(*) AS total_orders "
                "FROM orders GROUP BY customer_name ORDER BY customer_name"
            )
            return json.dumps(rows, ensure_ascii=False), False

        if name == "get_shipments":
            result = shipping.list_shipments()
            return json.dumps(result, ensure_ascii=False), False

        # ── Tool di scrittura ────────────────────────────────────────────────
        if name == "create_order":
            customer_name = arguments.get("customer_name", "").strip()
            lines = arguments.get("lines", [])
            if not customer_name:
                return json.dumps({"error": "customer_name mancante"}), False
            valid_lines = [
                {"sku": l["sku"], "quantity": int(l["quantity"])}
                for l in lines
                if l.get("sku") in _VALID_SKUS and int(l.get("quantity", 0)) >= 1
            ]
            if not valid_lines:
                return json.dumps({"error": "Nessuna riga valida. SKU disponibili: " + _FORM_SKUS}), False
            order = orders.create_order(customer_name, valid_lines)
            return json.dumps({
                "success": True,
                "order_id": order["id"],
                "customer_name": order["customer_name"],
                "status": order["status"],
                "lines": valid_lines,
            }), True

        if name == "restock_sku":
            sku = arguments.get("sku", "")
            quantity = int(arguments.get("quantity", 0))
            if sku not in _VALID_SKUS:
                return json.dumps({"error": f"SKU '{sku}' non valido"}), False
            if quantity < 1:
                return json.dumps({"error": "quantità deve essere >= 1"}), False
            warehouse.restock(sku, quantity)
            new_qty = warehouse.get_stock(sku)
            return json.dumps({"success": True, "sku": sku, "new_quantity": new_qty}), True

    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False), False

    return json.dumps({"error": f"Tool '{name}' non riconosciuto."}, ensure_ascii=False), False


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
    Invia la cronologia al modello con supporto tool-calling.
    Il modello può invocare tool di lettura (get_orders, get_order, get_warehouses,
    get_stock, get_customers, get_shipments) e di scrittura (create_order, restock_sku).
    La risposta include `actions_done` con i tool di scrittura eseguiti con successo,
    per permettere al frontend di refreshare le viste pertinenti.
    """
    body = request.get_json(silent=True) or {}
    messages = body.get("messages", [])
    base_prompt = body.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)

    # Inietta sempre il contesto aggiornato nel system prompt
    context = _get_warehouse_context()
    system_prompt = f"{base_prompt}\n\n{context}"

    client = _get_client()
    actions_done = []

    # Manteniamo una copia locale della history per la conversazione con i tool.
    # Non modifichiamo la lista originale del client per non sporcare la history
    # visibile all'utente con i messaggi interni di tool.
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
                # Risposta testuale finale
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

                tool_result, is_write = _execute_tool(tool_name, tool_args)

                if is_write:
                    result_data = json.loads(tool_result)
                    actions_done.append({"tool": tool_name, "result": result_data})

                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
        else:
            reply = "Limite di iterazioni raggiunto. Riprova con una domanda più specifica."

    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({
        "reply": reply,
        "actions_done": actions_done if actions_done else None,
    })


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
