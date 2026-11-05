---
name: wareflow-warehouses
description: Use when the user wants to list or inspect warehouses in the WareFlow system via the REST API.
---

# WareFlow — Skill: Warehouses

Questa skill guida nell'utilizzo dell'endpoint magazzini esposto da WareFlow
(`GET /warehouses`). L'API gira su `http://localhost:8080`.

## Operazioni disponibili

### Elenco magazzini

```
GET /warehouses
```

Restituisce la lista completa dei magazzini registrati nel sistema.

**Nessun parametro richiesto.**

**Risposta 200:**
```json
[
  { "id": 1, "name": "Milano Nord", "city": "Milano" },
  { "id": 2, "name": "Bologna Est", "city": "Bologna" },
  { "id": 3, "name": "Torino Sud",  "city": "Torino" }
]
```

**Esempio curl:**
```bash
curl http://localhost:8080/warehouses
```

## Note operative

- I magazzini sono dati di configurazione: non esiste un endpoint per crearli,
  modificarli o eliminarli tramite API.
- Il campo `id` dei magazzini è usato come riferimento nelle spedizioni
  (`shipments.warehouse_id`).
- Al momento del seed, il sistema carica tre magazzini fissi:
  Milano Nord (id=1), Bologna Est (id=2), Torino Sud (id=3).

## Passi per usare questa skill

1. Verificare che l'app sia in esecuzione (`python main.py` dalla cartella
   `challenge-starter/` — porta 8080).
2. Eseguire `GET /warehouses` per ottenere l'elenco.
3. Annotare gli `id` dei magazzini di interesse: serviranno per interpretare
   le risposte di `/shipments`.
