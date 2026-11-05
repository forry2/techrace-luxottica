# Piano: Coverage al 100%

## Overview

**Obiettivo:** Portare la test coverage da **11% → 100%** aggiungendo test in `tests/test_basic.py` (o in nuovi file di test dedicati per modulo).

**Baseline (2026-11-05):**
- 159 statement totali, 142 non coperti (11%)
- Solo `app/utils.py` è parzialmente coperto (71%) grazie ai 3 test esistenti
- I moduli `db`, `orders`, `warehouse`, `shipping`, `notifications`, `legacy_fax` hanno copertura 0%

**Approccio:** Aggiungere test unitari in ordine di dipendenza (dal basso verso l'alto dello stack):
`db` → `utils` (completamento) → `warehouse` → `shipping` → `notifications` → `orders` → `legacy_fax`

Tutti i test che richiedono il DB useranno `app.db.init_db()` per inizializzare il database SQLite in-memory prima di ogni test (o suite).

**Struttura dei file di test:** file separati per modulo (`test_db.py`, `test_warehouse.py`, `test_shipping.py`, `test_notifications.py`, `test_orders.py`, `test_legacy_fax.py`) in aggiunta al `test_basic.py` esistente.

---

## Sub-Task 1 — Completare la copertura di `app/utils.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire le 7 righe mancanti in `app/utils.py`: le branch non testate di `validate_order_payload`, la funzione `log_event` e `format_notification_email`.

**Expected Outcomes:**
- `app/utils.py` raggiunge 100% di copertura
- I test esistenti rimangono verdi

**Righe scoperte da coprire:**
- `5-6`: corpo di `log_event` (print con timestamp)
- `11`: branch `if "customer_name" not in payload`
- `16`: branch `if not isinstance(payload["lines"], list)`
- `19`: branch `if len(payload["lines"]) == 0`
- `24-25`: corpo di `format_notification_email`

**Todo List:**
- [ ] Aggiungere `test_log_event_prints_output` — chiama `log_event("test_event", key="val")` e verifica che stampi a stdout (capsys)
- [ ] Aggiungere `test_validate_order_payload_missing_customer_name` — payload senza `customer_name` → stringa d'errore (già presente, verificare riga 11)
- [ ] Aggiungere `test_validate_order_payload_lines_not_list` — payload con `lines` non lista → stringa d'errore (riga 16)
- [ ] Aggiungere `test_validate_order_payload_lines_empty` — payload con `lines=[]` → stringa d'errore (riga 19)
- [ ] Aggiungere `test_format_notification_email` — verifica che restituisca una stringa contenente nome cliente e righe d'ordine (righe 24-25)

**Relevant Context:**
- File: `challenge-starter/app/utils.py`
- File test esistente: `challenge-starter/tests/test_basic.py`

---

## Sub-Task 2 — Testare `app/db.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/db.py` al 100%: `init_db`, `query_all`, `query_one`, `execute`. Il database è SQLite in-memory, quindi i test sono veloci e senza dipendenze esterne.

**Expected Outcomes:**
- `app/db.py` raggiunge 100% di copertura
- I test verificano il corretto schema del DB e le operazioni CRUD base

**Todo List:**
- [ ] Creare `tests/test_db.py` (o aggiungere a `test_basic.py`)
- [ ] Aggiungere fixture/setup che chiama `init_db()` prima di ogni test (resetta `_initialized = False` per forzare re-init se necessario)
- [ ] `test_init_db_creates_tables` — dopo `init_db()`, query `SELECT name FROM sqlite_master WHERE type='table'` e verifica le 5 tabelle attese
- [ ] `test_init_db_seeds_data` — verifica che `query_all("SELECT * FROM warehouses")` restituisca 3 righe
- [ ] `test_execute_and_query_one` — inserisce una riga, recupera con `query_one`, verifica i valori
- [ ] `test_query_all_returns_list` — verifica che `query_all` ritorni lista di dict
- [ ] `test_query_one_returns_none_when_missing` — query su ID inesistente → `None`

**Relevant Context:**
- File: `challenge-starter/app/db.py`
- `_initialized` è un flag di modulo; va resettato a `False` tra i test per poter chiamare `init_db()` più volte
- Il DB è un singleton `sqlite3.connect(":memory:", check_same_thread=False)`

---

## Sub-Task 3 — Testare `app/warehouse.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/warehouse.py` al 100%: inizializzazione cache, lettura/scrittura cache, query DB per warehouse e stock.

**Expected Outcomes:**
- `app/warehouse.py` raggiunge 100% di copertura

**Todo List:**
- [ ] Creare `tests/test_warehouse.py`
- [ ] Setup: `init_db()` + `initialize_stock_cache()` prima dei test
- [ ] `test_initialize_stock_cache_populates_cache` — verifica che `_STOCK_CACHE` non sia vuoto dopo l'init
- [ ] `test_list_warehouses` — verifica che ritorni lista con almeno 3 magazzini
- [ ] `test_get_warehouse_for_sku_known` — per uno SKU presente nel seed, ritorna un warehouse_id valido
- [ ] `test_get_warehouse_for_sku_unknown` — per uno SKU sconosciuto, ritorna `None`
- [ ] `test_get_stock_returns_quantity` — SKU presente → quantità > 0
- [ ] `test_get_stock_returns_zero_for_unknown_sku` — SKU assente → 0
- [ ] `test_decrement_stock` — decrementa di N unità, verifica che `get_stock` rifletta il nuovo valore
- [ ] `test_restock` — aumenta la quantità, verifica via `get_stock`
- [ ] `test_get_reserved_quantity_empty` — senza ordini DRAFT, ritorna 0

**Relevant Context:**
- File: `challenge-starter/app/warehouse.py`
- `_STOCK_CACHE` è un dict di modulo; va riazzerato tra test se necessario
- `get_reserved_quantity` ha un import lazy di `orders` (anti-circular)

---

## Sub-Task 4 — Testare `app/shipping.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/shipping.py` al 100%: generazione tracking code, creazione spedizione, lista spedizioni.

**Expected Outcomes:**
- `app/shipping.py` raggiunge 100% di copertura

**Todo List:**
- [ ] Creare `tests/test_shipping.py`
- [ ] Setup: `init_db()` + `initialize_stock_cache()`
- [ ] `test_generate_tracking_code` — chiama `_generate_tracking_code()`, verifica formato (8 caratteri alfanumerici)
- [ ] `test_create_shipment_for_order` — fornisce un `order` dict e `lines` dict validi con SKU presenti nel seed; verifica che la spedizione abbia `status='PENDING'` e un `tracking_code`
- [ ] `test_list_shipments_empty` — senza spedizioni, ritorna lista vuota
- [ ] `test_list_shipments_after_create` — dopo `create_shipment_for_order`, `list_shipments()` ritorna 1 elemento

**Relevant Context:**
- File: `challenge-starter/app/shipping.py`
- Dipende da `warehouse._STOCK_CACHE` (deve essere inizializzato)
- SKU di seed disponibili in `app/db.py` → inseriti da `init_db()`

---

## Sub-Task 5 — Testare `app/notifications.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/notifications.py` al 100%: la funzione `notify_customer`.

**Expected Outcomes:**
- `app/notifications.py` raggiunge 100% di copertura

**Todo List:**
- [ ] Aggiungere test in `tests/test_notifications.py` o in `test_basic.py`
- [ ] `test_notify_customer_returns_email_body` — chiama `notify_customer(order, lines)` con dati fake, verifica che ritorni una stringa non vuota
- [ ] Verificare che `log_event` venga chiamato (side-effect su stdout, verificabile con `capsys`)

**Relevant Context:**
- File: `challenge-starter/app/notifications.py`
- Importa `app.legacy_fax` con `# noqa: F401` (import silenzioso, non richiede chiamata)
- Dipende da `utils.format_notification_email` e `utils.log_event`

---

## Sub-Task 6 — Testare `app/orders.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/orders.py` al 100%: creazione, lettura, lista, conferma e cancellazione ordini, incluse le eccezioni `StockError`.

**Expected Outcomes:**
- `app/orders.py` raggiunge 100% di copertura
- Tutti i path di errore (StockError) sono coperti

**Todo List:**
- [ ] Creare `tests/test_orders.py`
- [ ] Setup: `init_db()` + `initialize_stock_cache()` prima di ogni test
- [ ] `test_create_order` — crea un ordine con SKU validi, verifica dict restituito con `id`, `status='DRAFT'`
- [ ] `test_get_order_existing` — recupera ordine appena creato, verifica customer_name e lines
- [ ] `test_get_order_nonexistent` — `get_order(99999)` → `None`
- [ ] `test_list_orders` — verifica che ritorni lista (può essere vuota o con ordini creati nel test)
- [ ] `test_list_pending_orders_for_sku` — crea ordine DRAFT con SKU X, verifica che `list_pending_orders_for_sku(X)` lo includa
- [ ] `test_confirm_order_success` — conferma ordine valido → `status='CONFIRMED'`, verifica decremento stock
- [ ] `test_confirm_order_not_found` — `confirm_order(99999)` → `StockError`
- [ ] `test_confirm_order_already_confirmed` — tenta conferma su ordine già CONFIRMED → `StockError`
- [ ] `test_confirm_order_insufficient_stock` — crea ordine con qty > stock disponibile → `StockError`
- [ ] `test_confirm_order_concurrent_race_condition` — due `threading.Thread` confermano lo stesso ordine con stock limitato in contemporanea; verifica che esattamente uno riesca e l'altro riceva `StockError` (copre il path della race condition con `time.sleep(0.01)`)
- [ ] `test_cancel_order_draft` — cancella ordine DRAFT → `status='CANCELLED'`
- [ ] `test_cancel_order_confirmed_raises` — tenta cancellazione su ordine CONFIRMED → `StockError`

**Relevant Context:**
- File: `challenge-starter/app/orders.py`
- `confirm_order` chiama `warehouse`, `shipping`, `notifications`, `utils` → richiedono `init_db` + `initialize_stock_cache`
- `StockError` è definita in `app/orders.py`
- Il `time.sleep(0.01)` è intenzionale (race condition simulata); il test di concorrenza usa `threading.Thread` e raccoglie eccezioni nei thread

---

## Sub-Task 7 — Testare `app/legacy_fax.py`

**Stato:** `[ ] pending`

**Intent:**
Coprire `app/legacy_fax.py` al 100%: la funzione `send_fax_notification` che lancia sempre `NotImplementedError`.

**Expected Outcomes:**
- `app/legacy_fax.py` raggiunge 100% di copertura

**Todo List:**
- [ ] Aggiungere `test_send_fax_notification_raises` — chiama `send_fax_notification({"id": 1}, "123")` e verifica che sollevi `NotImplementedError` con il messaggio atteso (contiene `FAX_GATEWAY_HOST`)

**Relevant Context:**
- File: `challenge-starter/app/legacy_fax.py`
- Funzione dead-code: lancia sempre `NotImplementedError`, non fa I/O

---

## Sub-Task 8 — Verifica finale e pulizia

**Stato:** `[ ] pending`

**Intent:**
Eseguire l'intera suite di test con coverage report e verificare che tutti i moduli raggiungano 100%. Correggere eventuali gap residui.

**Expected Outcomes:**
- `pytest --cov=app --cov-report=term-missing` riporta 100% su tutti i moduli
- Nessun test in fail
- Nessun warning di coverage

**Todo List:**
- [ ] Eseguire `pytest --cov=app --cov-report=term-missing` dalla directory `challenge-starter`
- [ ] Se ci sono righe mancanti, aggiungere test mirati per coprirle
- [ ] Verificare che il file `.coveragerc` non escluda file indesiderati
- [ ] Confermare risultato finale: 159/159 statement coperti

**Relevant Context:**
- Config coverage: `challenge-starter/.coveragerc` — `source = .`, `omit = tests/*`
- Config pytest: `challenge-starter/pytest.ini`

---

## Ordine di esecuzione consigliato

```
Sub-Task 1 (utils completamento)
    ↓
Sub-Task 2 (db)
    ↓
Sub-Task 3 (warehouse)  ←── dipende da db
    ↓
Sub-Task 4 (shipping)   ←── dipende da warehouse + db
    ↓
Sub-Task 5 (notifications) ←── dipende da utils
    ↓
Sub-Task 6 (orders)     ←── dipende da tutto
    ↓
Sub-Task 7 (legacy_fax) ←── indipendente, ma lasciato per ultimo
    ↓
Sub-Task 8 (verifica finale)
```

## Note tecniche

- **DB reset tra test:** `app.db._initialized` va resettato a `False` nei `teardown`/fixture per garantire `init_db()` rieseguibile in test isolati.
- **Cache warehouse:** `app.warehouse._STOCK_CACHE` va svuotato nei teardown se i test modificano lo stock.
- **time.sleep in orders.py:** Il `time.sleep(0.01)` è intenzionale (simula latenza). I test lo tollerano senza mock a meno che la suite non diventi troppo lenta (non è il caso con pochi test).
- **Import circolare warehouse/orders:** Già gestito in `warehouse.py` con import lazy. I test non richiedono workaround aggiuntivi.
