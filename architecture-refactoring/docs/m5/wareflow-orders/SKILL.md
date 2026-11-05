---
name: wareflow-orders
description: Use when the user wants to create, read, confirm or cancel orders in the WareFlow system via the REST API.
---

# WareFlow — Skill: Orders

Questa skill guida nella gestione completa del ciclo di vita degli ordini tramite
le API REST di WareFlow. L'API gira su `http://localhost:8080`.

## Ciclo di vita di un ordine

```
[creazione] → DRAFT → [conferma] → CONFIRMED
                    → [annulla]  → CANCELLED
```

Un ordine in `DRAFT` può essere confermato o annullato.
Un ordine `CONFIRMED` o `CANCELLED` è in stato terminale — non modificabile.

---

## Operazioni disponibili

### 1. Crea un ordine

```
POST /orders
Content-Type: application/json
```

Crea un nuovo ordine in stato `DRAFT`. Non scala lo stock.

**Body JSON:**
```json
{
  "customer_name": "Acme Spa",
  "lines": [
    { "sku": "WIDGET-1", "quantity": 10 },
    { "sku": "PALLET-BOX", "quantity": 2 }
  ]
}
```

**Campi obbligatori:**
- `customer_name` — stringa non vuota
- `lines` — lista non vuota; ogni elemento richiede `sku` (stringa) e
  `quantity` (intero positivo)

**Risposta 201:**
```json
{
  "id": 1,
  "customer_name": "Acme Spa",
  "status": "DRAFT",
  "created_at": "2026-11-05 10:00:00",
  "lines": [
    { "sku": "WIDGET-1", "quantity": 10 },
    { "sku": "PALLET-BOX", "quantity": 2 }
  ]
}
```

**Risposta 400** (payload non valido):
```json
{ "error": "customer_name is required" }
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8080/orders \
     -H "Content-Type: application/json" \
     -d '{"customer_name":"Acme Spa","lines":[{"sku":"WIDGET-1","quantity":5}]}'
```

---

### 2. Elenco ordini

```
GET /orders
```

Restituisce tutti gli ordini (senza righe di dettaglio).

**Risposta 200:**
```json
[
  { "id": 1, "customer_name": "Acme Spa", "status": "DRAFT", "created_at": "..." }
]
```

**Esempio curl:**
```bash
curl http://localhost:8080/orders
```

---

### 3. Dettaglio ordine

```
GET /orders/{order_id}
```

Restituisce un ordine con le righe di dettaglio.

**Parametri:**
- `{order_id}` (path, intero) — id dell'ordine

**Risposta 200:**
```json
{
  "id": 1,
  "customer_name": "Acme Spa",
  "status": "DRAFT",
  "created_at": "...",
  "lines": [{ "sku": "WIDGET-1", "quantity": 5 }]
}
```

**Risposta 404:**
```json
{ "error": "not found" }
```

**Esempio curl:**
```bash
curl http://localhost:8080/orders/1
```

---

### 4. Conferma ordine

```
POST /orders/{order_id}/confirm
```

Conferma l'ordine: verifica la disponibilità di ogni SKU, decrementa lo stock,
crea la spedizione e notifica il cliente.

**Parametri:**
- `{order_id}` (path, intero)

**Nessun body richiesto.**

**Risposta 200** (successo):
```json
{
  "id": 1,
  "customer_name": "Acme Spa",
  "status": "CONFIRMED",
  "lines": [...],
  "shipment": {
    "id": 1,
    "order_id": 1,
    "warehouse_id": 1,
    "tracking_code": "WF-A1B2C3D4",
    "status": "PENDING",
    "rate": 8.65
  }
}
```

**Risposta 400** (stock insufficiente o stato non valido):
```json
{ "error": "not enough stock for WIDGET-1: have 5, need 10" }
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8080/orders/1/confirm
```

---

### 5. Annulla ordine

```
POST /orders/{order_id}/cancel
```

Annulla un ordine in stato `DRAFT`. Non è possibile annullare un ordine già
confermato.

**Parametri:**
- `{order_id}` (path, intero)

**Nessun body richiesto.**

**Risposta 200:**
```json
{ "id": 1, "status": "CANCELLED", ... }
```

**Risposta 400** (ordine già confermato):
```json
{ "error": "order 1 is already confirmed, cannot cancel" }
```

**Risposta 404:**
```json
{ "error": "not found" }
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8080/orders/1/cancel
```

---

## Passi per creare e confermare un ordine end-to-end

1. Controllare che lo stock sia sufficiente:
   `GET /stock/{sku}` per ogni articolo che si vuole ordinare.
2. Creare l'ordine in `DRAFT`:
   `POST /orders` con `customer_name` e `lines`.
3. Annotare l'`id` restituito.
4. Confermare l'ordine:
   `POST /orders/{id}/confirm`.
   - Se lo stock è sufficiente → risposta 200 con `shipment` allegato.
   - Se lo stock è esaurito → risposta 400 con messaggio d'errore.
5. Verificare lo stato aggiornato:
   `GET /orders/{id}`.
