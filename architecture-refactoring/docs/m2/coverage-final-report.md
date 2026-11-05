# M2 – Coverage finale e bug rilevati

Completato il **2026-11-05**.

---

## Risultato globale

| Metrica | Baseline | Finale |
|---------|----------|--------|
| Test eseguiti | 3 | 48 |
| Test passanti | 3 | 46 |
| **Test fallenti (bug reali)** | 0 | **2** |
| **Coverage totale** | **11%** | **100%** |
| Statement coperti | 17 / 159 | 159 / 159 |

---

## Dettaglio copertura per modulo

| Modulo | Statements | Miss | Cover |
|--------|-----------|------|-------|
| `app/__init__.py` | 0 | 0 | 100% |
| `app/db.py` | 31 | 0 | 100% |
| `app/legacy_fax.py` | 3 | 0 | 100% |
| `app/notifications.py` | 6 | 0 | 100% |
| `app/orders.py` | 50 | 0 | 100% |
| `app/shipping.py` | 21 | 0 | 100% |
| `app/utils.py` | 24 | 0 | 100% |
| `app/warehouse.py` | 24 | 0 | 100% |
| **TOTAL** | **159** | **0** | **100%** |

---

## File di test aggiunti

| File | Test | Modulo coperto |
|------|------|----------------|
| `tests/test_basic.py` | +7 (da 3 a 10) | `app/utils.py` |
| `tests/test_db.py` | 7 | `app/db.py` |
| `tests/test_warehouse.py` | 9 | `app/warehouse.py` |
| `tests/test_shipping.py` | 5 | `app/shipping.py` |
| `tests/test_notifications.py` | 2 | `app/notifications.py` |
| `tests/test_orders.py` | 13 | `app/orders.py` |
| `tests/test_legacy_fax.py` | 1 | `app/legacy_fax.py` |

---

## Bug rilevati dai test

I test sono stati scritti per specificare il comportamento **corretto atteso**.
I 2 test seguenti **falliscono** perché il codice di produzione non rispetta il contratto.

---

### Bug 1 — `confirm_order` non segnala ordini inesistenti

**Test fallente:** `tests/test_orders.py::test_confirm_order_not_found`

**Comportamento atteso:**
```
confirm_order(99999)  →  raise StockError("order 99999 not found")
```

**Comportamento effettivo:**
```
confirm_order(99999)  →  return None   # silenzioso
```

**Codice buggy** — `app/orders.py:52-55`:
```python
def confirm_order(order_id):
    order = get_order(order_id)
    if order is None:
        return None   # ← dovrebbe essere raise StockError
```

**Impatto:** Un chiamante che non controlla il valore di ritorno non viene mai informato
che l'ordine non esiste. L'operazione fallisce silenziosamente senza alcuna traccia di errore.

---

### Bug 2 — Race condition: lost update sullo stock (overselling)

**Test fallente:** `tests/test_orders.py::test_confirm_order_concurrent_race_condition`

**Comportamento atteso:**
Con 250 unità di `WIDGET-2` e due ordini concorrenti da 200 ciascuno,
esattamente **uno** deve riuscire e l'altro deve ricevere `StockError`.

**Comportamento effettivo:**
Entrambi i thread passano il controllo di disponibilità e confermano l'ordine.
Stock finale: `50` (dovrebbe essere impossibile — sono state "vendute" 400 unità su 250).

**Output stdout durante il test:**
```
stock_decremented sku=WIDGET-2 quantity=200 remaining=50   ← thread 1
stock_decremented sku=WIDGET-2 quantity=200 remaining=50   ← thread 2 (stesso risultato!)
```

**Codice buggy** — `app/warehouse.py:32-38`:
```python
def decrement_stock(sku, quantity_before, quantity):
    # Takes the caller's own "quantity_before" (captured when it checked
    # availability) instead of re-reading _STOCK_CACHE fresh here.
    # Two threads both read the same stale value → lost update.
    _STOCK_CACHE[sku] = quantity_before - quantity   # ← non atomico
```

**Radice del problema:** `confirm_order` in `orders.py` legge lo stock (`current = warehouse.get_stock(...)`)
e poi chiama `warehouse.decrement_stock(sku, current, quantity)` passando il valore già letto.
Il `time.sleep(0.01)` tra le due operazioni (riga 68) apre esplicitamente la finestra di race condition.
Poiché `_STOCK_CACHE` è un dizionario Python non protetto da lock, la sequenza è:

```
Thread 1: legge  _STOCK_CACHE["WIDGET-2"] = 250  ✓
Thread 2: legge  _STOCK_CACHE["WIDGET-2"] = 250  ✓ (Thread 1 non ha ancora scritto)
Thread 1: scrive _STOCK_CACHE["WIDGET-2"] = 50
Thread 2: scrive _STOCK_CACHE["WIDGET-2"] = 50   ← sovrascrive Thread 1
```

**Impatto:** Overselling — è possibile vendere più unità di quelle disponibili.

---

## Note tecniche

- I `ResourceWarning` su connessioni SQLite non chiuse sono rumore del GC di Python 3.14:
  il teardown imposta `_connection = None` senza chiamare `.close()` esplicitamente.
  Non impattano l'esito dei test né la coverage.
- Il `time.sleep(0.01)` in `orders.py:68` è intenzionale nel codice di produzione
  (simula latenza di elaborazione). I test lo tollerano senza mock; la suite completa
  si esegue in ~0.3 s.
- Il reset del singleton DB tra i test avviene impostando `app.db._initialized = False`
  e `app.db._connection = None` in `setup_function` / `teardown_function`.
