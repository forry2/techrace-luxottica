# M4 — Fix della race condition sullo stock

## Sommario

Nei periodi di picco, il conteggio di stock di alcuni articoli risultava sempre più basso del reale
dopo una raffica di conferme ordine concorrenti. Il problema era una **race condition classica**
(lost update) sulla cache in memoria `_STOCK_CACHE` in `warehouse.py`.

La soluzione adottata è la sincronizzazione reale: check e decremento dello stock vengono ora
eseguiti come operazione atomica protetta da `threading.Lock`. Il fix è stato verificato con un
test di regressione che lancia 50 thread concorrenti sullo stesso SKU e verifica che il saldo
finale sia aritmeticamente esatto.

**Risultato:** 50 passed, 1 skipped, 0 failed.

---

## Causa del bug

In `orders.py`, la funzione `confirm_order()` seguiva questo pattern per ogni riga dell'ordine:

```python
current = warehouse.get_stock(sku)        # 1. legge il valore dalla cache
# ... lavoro intermedio (in produzione: tax, audit, etc.) ...
time.sleep(0.01)                           # 2. finestra di vulnerabilità
warehouse.decrement_stock(sku, current, qty)  # 3. scrive usando il valore stale
```

Con `threaded=True`, Flask serve ogni richiesta in un thread separato. Se due thread
eseguivano `confirm_order` sullo stesso SKU in contemporanea:

```
Thread A legge:  current = 1000
Thread B legge:  current = 1000   ← stesso valore, A non ha ancora scritto
Thread A scrive: _STOCK_CACHE = 1000 - 100 = 900
Thread B scrive: _STOCK_CACHE = 1000 - 200 = 800  ← doveva essere 700!
```

Il secondo thread sovrascriveva il risultato del primo: **lost update**.
Il conteggio risultante era sempre più basso del corretto (unità "sparite").

---

## La soluzione

### `app/warehouse.py` — nuova funzione `check_and_decrement_stock()`

Introdotto `_stock_lock = threading.Lock()` a livello di modulo.

La funzione `check_and_decrement_stock()` esegue **lettura + controllo + scrittura
come operazione atomica** dentro il lock:

```python
_stock_lock = threading.Lock()

def check_and_decrement_stock(sku, quantity):
    with _stock_lock:
        current = _STOCK_CACHE.get(sku, 0)
        if current < quantity:
            raise ValueError(f"not enough stock for {sku}: have {current}, need {quantity}")
        _STOCK_CACHE[sku] = current - quantity
        log_event("stock_decremented", sku=sku, quantity=quantity, remaining=_STOCK_CACHE[sku])
```

Nessun thread può leggere o scrivere `_STOCK_CACHE` per quello SKU mentre
un altro thread è dentro il blocco `with _stock_lock`. Il lost update diventa
strutturalmente impossibile.

Anche `restock()` acquisisce lo stesso lock, evitando interferenze con le
operazioni di decremento concorrenti.

### `app/orders.py` — `confirm_order()` usa la nuova API

Il vecchio pattern read-sleep-write è stato sostituito con una singola chiamata:

```python
for line in order["lines"]:
    try:
        warehouse.check_and_decrement_stock(line["sku"], line["quantity"])
    except ValueError as e:
        raise StockError(str(e))
```

Rimosso anche il `time.sleep(0.01)` che era lì per simulare il lavoro intermedio
e allargava artificialmente la finestra di vulnerabilità.

---

## Perché non è una patch superficiale

| Approccio | Perché non è sufficiente |
|---|---|
| `time.sleep` ridotto o rimosso | Riduce la probabilità, non elimina il problema |
| Retry in caso di valore anomalo | Non rileva il lost update (il valore scritto è sintatticamente valido) |
| `time.sleep` + retry casuale | Non garantisce correttezza, degrada le performance |
| **`threading.Lock` (adottato)** | **Garantisce mutua esclusione: un solo thread modifica la cache alla volta** |

---

## Test di regressione

File: [`tests/test_stock_concurrency.py`](../../challenge-starter/tests/test_stock_concurrency.py)

### `test_50_concurrent_confirmations_exact_stock`

Lancia 50 thread in contemporanea, ciascuno conferma un ordine da 1 unità di `WIDGET-1`
(stock iniziale: 1300). Tutti e 50 devono riuscire e il saldo finale deve essere
esattamente `1300 - 50 = 1250`.

Con il vecchio codice, il valore finale sarebbe stato un numero imprevedibile
tra 1299 e 1250 (o anche fuori range) a causa dei lost update.

### `test_50_concurrent_confirmations_stock_never_goes_negative`

50 thread tentano di confermare 30 unità ciascuno su `WIDGET-2` (stock: 250).
Solo 8 possono riuscire (8 × 30 = 240 ≤ 250; 9 × 30 = 270 > 250).
Verifica che lo stock non vada mai sotto zero e che l'equazione
`confermati × 30 + stock_finale = 250` sia esatta.

### `test_concurrent_restock_and_confirm_exact_result`

Interleave di 20 `restock(+10)` e 20 `confirm(1 unità)` concorrenti sullo stesso SKU.
Verifica che il saldo finale rispetti l'aritmetica esatta anche con operazioni
di tipo diverso (incremento e decremento) che condividono lo stesso lock.

---

## File modificati

| File | Modifica |
|---|---|
| `app/warehouse.py` | Aggiunto `_stock_lock`, nuova `check_and_decrement_stock()`, lock su `restock()` e `decrement_stock()` |
| `app/orders.py` | `confirm_order()` usa `check_and_decrement_stock()`, rimosso `time.sleep`, rimosso `import time` |
| `tests/test_stock_concurrency.py` | **Nuovo** — 3 test di regressione sulla concorrenza |

---

## Risultato finale

```
50 passed, 1 skipped, 0 failed
```

Il test skippato (`test_send_fax_notification_raises`) riguarda il modulo
`legacy_fax` rimosso in M3 — non correlato a questa milestone.
