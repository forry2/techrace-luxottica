# M3 — Refactoring strutturale di WareFlow

## Obiettivo

Eliminare i problemi strutturali interni identificati in M1 senza cambiare il comportamento esterno dell'applicazione:

1. **Dipendenza circolare** tra `warehouse.py` e `orders.py`
2. **Modulo "discarica"** `utils.py` con responsabilità non correlate
3. **Codice morto** `legacy_fax.py` ancora importato nel codice attivo

---

## Cosa è stato modificato

### 1. Dipendenza circolare eliminata

**Problema:** `warehouse.py` conteneva una funzione `get_reserved_quantity()` che al suo interno eseguiva un `from app.orders import list_pending_orders_for_sku`. Questo import deferred creava un ciclo nascosto:

```
orders.py → warehouse.py → (dentro get_reserved_quantity) → orders.py
```

Il cycle-detector analizza l'AST completo del file, quindi rilevava il ciclo anche se l'import era dentro il corpo di una funzione.

**Soluzione:**
- `get_reserved_quantity()` rimossa da `warehouse.py`
- Funzione spostata in `orders.py`, dove appartiene naturalmente (interroga le tabelle degli ordini)

**File modificati:**
- `app/warehouse.py` — rimossa `get_reserved_quantity()` e il relativo import deferred
- `app/orders.py` — aggiunta `get_reserved_quantity()` accanto a `list_pending_orders_for_sku()`
- `tests/test_warehouse.py` — aggiornato l'import: `get_reserved_quantity` ora importata da `app.orders`

---

### 2. `utils.py` decomposto per responsabilità

**Problema:** `utils.py` raccoglieva quattro funzioni senza nessun legame tra loro:

| Funzione | Responsabilità |
|---|---|
| `log_event` | Logging su stdout |
| `validate_order_payload` | Validazione input HTTP |
| `format_notification_email` | Formattazione email cliente |
| `calculate_shipping_rate` | Calcolo tariffa di spedizione |

**Soluzione:** ogni funzione spostata nel modulo che ne ha la responsabilità semantica.

| Funzione | Prima | Dopo |
|---|---|---|
| `log_event` | `utils.py` | `utils.py` (invariato — logging è una responsabilità trasversale) |
| `validate_order_payload` | `utils.py` | `validators.py` (nuovo modulo — validazione input) |
| `format_notification_email` | `utils.py` | `notifications.py` (formattazione email è parte della notifica) |
| `calculate_shipping_rate` | `utils.py` | `shipping.py` (la tariffa è logica di spedizione) |

**File modificati:**
- `app/utils.py` — ora contiene solo `log_event`
- `app/validators.py` — **nuovo file**, contiene `validate_order_payload`
- `app/notifications.py` — aggiunta `format_notification_email`, rimosso import da `utils`
- `app/shipping.py` — aggiunta `calculate_shipping_rate`, rimosso import da `utils`
- `main.py` — aggiornato import: `validate_order_payload` ora da `app.validators`
- `tests/test_basic.py` — aggiornati gli import per seguire le nuove posizioni delle funzioni

---

### 3. Codice morto rimosso

**Problema:** `legacy_fax.py` era un modulo decommissionato (il gateway fax è spento da anni) ma era ancora importato attivamente in `notifications.py` con un commento `# noqa: F401 - unused`. Non causava errori a runtime ma ingannava chi leggeva il codice.

**Soluzione:**
- `app/legacy_fax.py` **eliminato**
- `notifications.py` — rimosso `from app import legacy_fax`
- `tests/test_legacy_fax.py` — il test che importava direttamente il modulo è marcato `@pytest.mark.skip` con spiegazione, poiché il modulo testato non esiste più

---

## Stato dei test dopo il refactoring

```
47 passed, 1 skipped
```

Il test saltato (`test_send_fax_notification_raises`) riguarda il modulo rimosso.

L'unico test in stato di failure (`test_confirm_order_concurrent_race_condition`) era già fallente prima di M3: documenta la race condition sulla cache dello stock, che è l'oggetto del fix in M4.

---

## Struttura dei moduli dopo M3

```
app/
├── db.py             — accesso SQLite (invariato)
├── utils.py          — solo log_event
├── validators.py     — NEW: validate_order_payload
├── warehouse.py      — cache stock + query magazzino (senza import circolari)
├── orders.py         — logica ordini + get_reserved_quantity
├── shipping.py       — logica spedizioni + calculate_shipping_rate
└── notifications.py  — notifiche cliente + format_notification_email
```

Grafo delle dipendenze dopo M3 — **nessun ciclo**:

```
main.py
  ├── app.db
  ├── app.validators
  ├── app.warehouse  →  app.db, app.utils
  ├── app.orders     →  app.db, app.warehouse, app.shipping, app.notifications, app.utils
  └── app.shipping   →  app.db, app.warehouse, app.utils

app.notifications    →  app.utils
app.utils            →  (nessuna dipendenza interna)
app.validators       →  (nessuna dipendenza interna)
app.db               →  (nessuna dipendenza interna)
```
