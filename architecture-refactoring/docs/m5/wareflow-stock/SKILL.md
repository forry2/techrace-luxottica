---
name: wareflow-stock
description: Use when the user wants to check stock availability or restock a SKU in the WareFlow system via the REST API.
---

# WareFlow — Skill: Stock

Questa skill guida nella consultazione e nel rifornimento dello stock articoli
tramite le API REST di WareFlow. L'API gira su `http://localhost:8080`.

## Operazioni disponibili

### 1. Consulta disponibilità di un articolo

```
GET /stock/{sku}
```

Restituisce la quantità disponibile per uno SKU specifico. Il valore viene letto
dalla cache in memoria (`_STOCK_CACHE`), non direttamente dal database.

**Parametri:**
- `{sku}` (path, obbligatorio) — codice articolo, es. `WIDGET-1`

**Risposta 200:**
```json
{ "sku": "WIDGET-1", "quantity": 1300 }
```

Se lo SKU non esiste nella cache, `quantity` è `0` (nessun errore 404).

**Esempio curl:**
```bash
curl http://localhost:8080/stock/WIDGET-1
curl http://localhost:8080/stock/PALLET-BOX
```

**SKU disponibili al seed:**
| SKU | Magazzino | Quantità iniziale |
|---|---|---|
| WIDGET-1 | Milano Nord (1) + Torino Sud (3) | 1300 (1000+300) |
| WIDGET-2 | Milano Nord (1) | 250 |
| PALLET-BOX | Bologna Est (2) | 500 |

---

### 2. Rifornisci uno SKU

```
POST /stock/{sku}/restock
Content-Type: application/json
```

Aggiunge quantità alla cache dello stock per un articolo.

**Parametri:**
- `{sku}` (path, obbligatorio) — codice articolo

**Body JSON:**
```json
{ "quantity": 100 }
```
- `quantity` (intero, default 0) — unità da aggiungere

**Risposta 200:**
```json
{ "sku": "WIDGET-1", "quantity": 1400 }
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8080/stock/WIDGET-1/restock \
     -H "Content-Type: application/json" \
     -d '{"quantity": 100}'
```

## ⚠️ Limitazioni importanti

- `restock` aggiorna **solo la cache in memoria**, non il database SQLite.
  Al riavvio dell'applicazione, il rifornimento va perso.
- La cache viene inizializzata da SQLite **una sola volta all'avvio**
  (`initialize_stock_cache()`). Modifiche dirette al DB non si riflettono
  sulla cache senza riavvio.
- Le operazioni di decremento (`confirm_order`) e di rifornimento condividono
  lo stesso `_stock_lock`: le chiamate concorrenti sono thread-safe.

## Passi per usare questa skill

1. Verificare che l'app sia in esecuzione (`python main.py` — porta 8080).
2. Per **controllare lo stock**: `GET /stock/{sku}`.
3. Per **rifornire**: `POST /stock/{sku}/restock` con body `{"quantity": N}`.
4. Verificare il nuovo valore con `GET /stock/{sku}`.
