---
name: wareflow-shipments
description: Use when the user wants to list or inspect shipments in the WareFlow system via the REST API.
---

# WareFlow — Skill: Shipments

Questa skill guida nella consultazione delle spedizioni tramite le API REST di
WareFlow. L'API gira su `http://localhost:8080`.

## Operazioni disponibili

### Elenco spedizioni

```
GET /shipments
```

Restituisce tutte le spedizioni presenti nel sistema.

**Nessun parametro richiesto.**

**Risposta 200:**
```json
[
  {
    "id": 1,
    "order_id": 1,
    "warehouse_id": 1,
    "tracking_code": "WF-A1B2C3D4",
    "status": "PENDING"
  }
]
```

**Esempio curl:**
```bash
curl http://localhost:8080/shipments
```

---

## Come viene creata una spedizione

Le spedizioni **non si creano direttamente** tramite API: vengono generate
automaticamente dal sistema al momento della conferma di un ordine
(`POST /orders/{id}/confirm`).

La logica di assegnazione del magazzino è:
1. Per ogni articolo dell'ordine, si cerca il primo SKU con stock > 0 nella cache.
2. Si usa il magazzino che ospita quel SKU (quello con la quantità più alta).
3. Se nessun SKU ha stock disponibile, viene usato il magazzino di default (id=1).

La risposta di `POST /orders/{id}/confirm` include già la spedizione creata nel
campo `shipment`.

---

## Campi della risposta

| Campo | Tipo | Descrizione |
|---|---|---|
| `id` | intero | Identificativo univoco della spedizione |
| `order_id` | intero | Riferimento all'ordine confermato |
| `warehouse_id` | intero | Magazzino di origine (vedi `GET /warehouses`) |
| `tracking_code` | stringa | Codice di tracciamento formato `WF-XXXXXXXX` |
| `status` | stringa | Stato attuale — solo `PENDING` nel sistema corrente |

---

## Note operative

- Non esiste un endpoint per aggiornare lo stato di una spedizione: `PENDING`
  è l'unico stato possibile nell'implementazione attuale.
- Il campo `rate` (tariffa di spedizione calcolata) è presente nella risposta
  di conferma ordine ma non è persistito in SQLite, quindi non appare in
  `GET /shipments`.
- Per correlare una spedizione a un ordine: usa `order_id` con `GET /orders/{id}`.

## Passi per usare questa skill

1. Verificare che l'app sia in esecuzione (`python main.py` — porta 8080).
2. Eseguire `GET /shipments` per vedere tutte le spedizioni.
3. Per il dettaglio dell'ordine associato: `GET /orders/{order_id}`.
4. Per il magazzino di origine: `GET /warehouses` e filtra per `warehouse_id`.
