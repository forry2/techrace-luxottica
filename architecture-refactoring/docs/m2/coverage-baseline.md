# M2 – Coverage di partenza

Rilevata il **2026-11-05** prima di qualsiasi modifica al codice.

## Risultato globale

| Metric | Valore |
|--------|--------|
| Test eseguiti | 3 |
| Test passanti | 3 |
| **Coverage totale** | **11%** |

## Dettaglio per modulo

| Modulo | Statements | Miss | Cover | Righe scoperte |
|--------|-----------|------|-------|----------------|
| `app/__init__.py` | 0 | 0 | 100% | — |
| `app/utils.py` | 24 | 7 | 71% | 5-6, 11, 16, 19, 24-25 |
| `app/db.py` | 31 | 31 | 0% | 1-99 |
| `app/legacy_fax.py` | 3 | 3 | 0% | 5-9 |
| `app/notifications.py` | 6 | 6 | 0% | 1-8 |
| `app/orders.py` | 50 | 50 | 0% | 1-90 |
| `app/shipping.py` | 21 | 21 | 0% | 1-46 |
| `app/warehouse.py` | 24 | 24 | 0% | 1-55 |
| **TOTAL** | **159** | **142** | **11%** | |

## Obiettivo M2

La valutazione richiede almeno **+30 punti percentuali** rispetto alla baseline → target minimo: **≥ 38%**.

### Priorità per massimizzare il guadagno

| Modulo | Stmt da coprire | Impatto stimato |
|--------|----------------|-----------------|
| `app/orders.py` | 50 | +31 pt |
| `app/db.py` | 31 | +20 pt |
| `app/warehouse.py` | 24 | +15 pt |
| `app/shipping.py` | 21 | +13 pt |

Coprire `orders.py` + `warehouse.py` da soli porta già ben oltre il 38%.
