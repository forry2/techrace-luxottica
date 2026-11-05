# WareFlow — Architettura del Sistema (post-refactoring)

> Documento prodotto da analisi diretta del codice sorgente rifattorizzato (M3 + fix concorrenza M4).  
> Descrive la struttura reale dell'applicazione nello stato attuale — non quella originale.

---

## 1. Vista dei Requisiti — Use Case Diagram

Gli attori principali e le operazioni che il sistema espone. Invariati rispetto alla versione originale: il refactoring non ha cambiato il comportamento esterno.

```mermaid
graph LR
    subgraph Attori
        RM["Responsabile Magazzino"]
        OPER["Operatore Logistico"]
        SYS["Sistema (interno)"]
    end

    subgraph WareFlow REST API
        UC1["Consulta magazzini"]
        UC2["Consulta stock per SKU"]
        UC3["Rifornisci SKU (restock)"]
        UC4["Crea ordine (DRAFT)"]
        UC5["Consulta ordini"]
        UC6["Conferma ordine"]
        UC7["Annulla ordine"]
        UC8["Consulta spedizioni"]
        UC9["Invia notifica cliente"]
        UC10["Crea spedizione"]
    end

    RM --> UC1
    RM --> UC2
    RM --> UC3
    OPER --> UC4
    OPER --> UC5
    OPER --> UC6
    OPER --> UC7
    OPER --> UC8
    SYS --> UC9
    SYS --> UC10
    UC6 --> UC9
    UC6 --> UC10
```

---

## 2. Vista Logica — Package Diagram

Mappa dei moduli Python e le dipendenze reali dopo il refactoring. Nessun ciclo, nessun modulo decommissionato, responsabilità separate.

```mermaid
graph TD
    main["main.py\n(Flask app factory + route handlers)"]

    subgraph app/
        db["db.py\n(SQLite layer)"]
        warehouse["warehouse.py\n(stock cache + lock + queries)"]
        orders["orders.py\n(business logic ordini\n+ get_reserved_quantity)"]
        shipping["shipping.py\n(logica spedizioni\n+ calculate_shipping_rate)"]
        notifications["notifications.py\n(notifiche + format_notification_email)"]
        validators["validators.py\n(validazione payload HTTP)"]
        utils["utils.py\n(solo log_event)"]
    end

    main --> db
    main --> orders
    main --> shipping
    main --> warehouse
    main --> validators

    orders --> db
    orders --> shipping
    orders --> warehouse
    orders --> notifications
    orders --> utils

    shipping --> db
    shipping --> warehouse
    shipping --> utils

    warehouse --> db
    warehouse --> utils

    notifications --> utils
```

> **Nessun ciclo.** La dipendenza circolare `warehouse ↔ orders` è stata eliminata spostando `get_reserved_quantity()` in `orders.py`. Il modulo `legacy_fax.py` è stato rimosso insieme a tutti i suoi riferimenti.

---

## 3. Vista Logica — Data Model Diagram

Schema delle entità persistite in SQLite. Invariato rispetto all'originale: il refactoring non ha toccato il database.

```mermaid
erDiagram
    warehouses {
        int id PK
        text name
        text city
    }
    stock {
        text sku PK
        int warehouse_id PK
        text name
        int quantity
    }
    orders {
        int id PK
        text customer_name
        text status
        text created_at
    }
    order_lines {
        int id PK
        int order_id FK
        text sku
        int quantity
    }
    shipments {
        int id PK
        int order_id FK
        int warehouse_id FK
        text tracking_code
        text status
    }

    warehouses ||--o{ stock : "ospita"
    orders ||--o{ order_lines : "contiene"
    orders ||--o| shipments : "genera"
    warehouses ||--o{ shipments : "origine"
```

**Valori possibili di `orders.status`:** `DRAFT` → `CONFIRMED` oppure `CANCELLED`  
**Valori possibili di `shipments.status`:** `PENDING` (unico valore scritto dal codice)

---

## 4. Vista dei Processi — State Machine: ciclo di vita di un ordine

```mermaid
stateDiagram-v2
    [*] --> DRAFT : POST /orders
    DRAFT --> CONFIRMED : POST /orders/{id}/confirm\n[stock sufficiente — check atomico con lock]
    DRAFT --> CANCELLED : POST /orders/{id}/cancel
    CONFIRMED --> [*]
    CANCELLED --> [*]

    note right of CONFIRMED
        Al momento della conferma:
        1. check + decremento stock sotto _stock_lock (atomico)
        2. spedizione creata (status PENDING)
        3. notifica cliente inviata (log su stdout)
    end note
```

---

## 5. Vista dei Processi — Sequence Diagram: `POST /orders/{id}/confirm`

Il flusso critico dopo il fix della concorrenza. Il check e il decremento dello stock avvengono ora come operazione atomica all'interno di `_stock_lock`.

```mermaid
sequenceDiagram
    actor Client
    participant main as main.py (route handler)
    participant orders as orders.py
    participant warehouse as warehouse.py
    participant db as db.py (SQLite in-memory)
    participant shipping as shipping.py
    participant notifications as notifications.py

    Client->>main: POST /orders/{id}/confirm
    main->>orders: confirm_order(order_id)
    orders->>db: SELECT * FROM orders WHERE id=?
    db-->>orders: order (status=DRAFT) oppure → StockError "not found"
    orders->>db: SELECT sku, quantity FROM order_lines WHERE order_id=?
    db-->>orders: lines[]

    loop per ogni line item
        orders->>warehouse: check_and_decrement_stock(sku, qty)
        Note over warehouse: acquisisce _stock_lock
        Note over warehouse: legge cache, verifica disponibilità, decrementa
        Note over warehouse: rilascia _stock_lock
        warehouse-->>orders: ok oppure ValueError → StockError
    end

    orders->>db: UPDATE orders SET status='CONFIRMED'
    orders->>shipping: create_shipment_for_order(order, lines)
    shipping->>warehouse: get_stock(sku) — per warehouse selection
    shipping->>db: INSERT INTO shipments
    db-->>shipping: shipment_id
    shipping-->>orders: shipment dict
    orders->>notifications: notify_customer(order, lines)
    notifications-->>orders: email_body (loggata su stdout)
    orders-->>main: order + shipment
    main-->>Client: 200 OK + JSON
```

---

## 6. Vista dei Processi — Activity Diagram: `POST /stock/{sku}/restock`

```mermaid
flowchart TD
    A([Client: POST /stock/sku/restock]) --> B[Leggi quantity dal body JSON]
    B --> C[warehouse.restock(sku, quantity)]
    C --> D["acquisisce _stock_lock\n_STOCK_CACHE[sku] += quantity\nrilascia _stock_lock"]
    D --> E[warehouse.get_stock(sku)]
    E --> F([Risposta: sku + quantity aggiornata])
```

> **Nota:** `restock` aggiorna **solo** `_STOCK_CACHE` — non scrive su SQLite. Lo stock aggiunto a runtime non sopravvive a un riavvio del processo. L'operazione è ora thread-safe grazie a `_stock_lock`.

---

## 7. Vista dei Componenti — Component Diagram

Responsabilità e confini di ciascun componente dopo il refactoring.

```mermaid
graph TB
    subgraph "Flask Process — porta 8080"
        subgraph "HTTP Layer"
            routes["Route Handlers\n(main.py closures)\nDeserializza input HTTP,\nchiama i moduli, serializza JSON"]
        end

        subgraph "Business Logic"
            orders_mod["orders.py\nOrchestrazione ordini:\ncreazione, conferma, cancellazione\nget_reserved_quantity"]
            warehouse_mod["warehouse.py\nGestione _STOCK_CACHE con _stock_lock\ncheck_and_decrement_stock (atomico)\nquery warehouse su SQLite"]
            shipping_mod["shipping.py\nCreazione spedizioni\ncalculate_shipping_rate\ntracking code"]
            notifications_mod["notifications.py\nformat_notification_email\nnotify_customer"]
            validators_mod["validators.py\nvalidate_order_payload"]
        end

        subgraph "Infrastructure"
            db_mod["db.py\nAccesso SQLite con _db_lock"]
            utils_mod["utils.py\nSolo log_event"]
        end

        subgraph "In-process State"
            stock_cache["_STOCK_CACHE\n(dict Python)\nprotetto da _stock_lock"]
            sqlite_db["SQLite :memory:\n(singola connessione)\nprotetta da _db_lock"]
        end
    end

    routes --> orders_mod
    routes --> warehouse_mod
    routes --> shipping_mod
    routes --> validators_mod

    orders_mod --> warehouse_mod
    orders_mod --> shipping_mod
    orders_mod --> notifications_mod
    orders_mod --> db_mod
    orders_mod --> utils_mod

    shipping_mod --> warehouse_mod
    shipping_mod --> db_mod
    shipping_mod --> utils_mod

    warehouse_mod --> db_mod
    warehouse_mod --> utils_mod
    warehouse_mod <-->|"con _stock_lock"| stock_cache

    notifications_mod --> utils_mod

    db_mod <-->|"con _db_lock"| sqlite_db
```

---

## 8. Vista Fisica — Deployment Diagram

```mermaid
graph TD
    subgraph "Host / Container (singolo processo)"
        subgraph "Python Process"
            FLASK["Flask HTTP Server\nthreaded=True — porta 8080"]
            APP["WareFlow App Modules"]
            CACHE["_STOCK_CACHE\n(dict in heap)\nprotetto da _stock_lock"]
            SQLITE["SQLite :memory:\n(singola connessione)\nprotetta da _db_lock"]
        end
    end

    CLIENT["Client HTTP\n(browser / curl / sistema ERP)"] -->|"HTTP REST :8080"| FLASK
    FLASK -->|"richiesta per thread"| APP
    APP -->|"read/write con _stock_lock"| CACHE
    APP -->|"read/write con _db_lock"| SQLITE
```

> L'app gira con `threaded=True`: ogni richiesta HTTP viene gestita in un thread separato. Dopo il refactoring **entrambi** gli stati condivisi sono protetti: `_STOCK_CACHE` da `_stock_lock` in `warehouse.py`, SQLite da `_db_lock` in `db.py`.

---

## 9. Riepilogo dipendenze tra moduli

| Modulo | Dipende da |
|---|---|
| `main.py` | `db`, `orders`, `shipping`, `warehouse`, `validators` |
| `orders.py` | `db`, `shipping`, `warehouse`, `notifications`, `utils` |
| `shipping.py` | `db`, `warehouse`, `utils` |
| `warehouse.py` | `db`, `utils` |
| `notifications.py` | `utils` |
| `validators.py` | *(nessuna dipendenza interna)* |
| `utils.py` | *(nessuna dipendenza interna)* |
| `db.py` | *(nessuna dipendenza interna)* |

**Nessun ciclo.** Verificato con `detect_cycles.py` → `no cycles`.

---

## 10. Mappa degli endpoint REST

| Metodo | Path | Modulo | Funzione |
|---|---|---|---|
| `GET` | `/warehouses` | `warehouse` | `list_warehouses()` |
| `GET` | `/stock/<sku>` | `warehouse` | `get_stock(sku)` |
| `POST` | `/stock/<sku>/restock` | `warehouse` | `restock(sku, quantity)` |
| `GET` | `/orders` | `orders` | `list_orders()` |
| `POST` | `/orders` | `orders` | `create_order(customer_name, lines)` |
| `GET` | `/orders/<id>` | `orders` | `get_order(order_id)` |
| `POST` | `/orders/<id>/confirm` | `orders` | `confirm_order(order_id)` |
| `POST` | `/orders/<id>/cancel` | `orders` | `cancel_order(order_id)` |
| `GET` | `/shipments` | `shipping` | `list_shipments()` |

---

## 11. Problemi risolti rispetto alla versione originale

| Problema originale | Stato |
|---|---|
| Race condition su `_STOCK_CACHE` (lost update tra thread) | ✅ Risolto — `check_and_decrement_stock()` è atomico sotto `_stock_lock` |
| Import circolare `warehouse ↔ orders` (deferred, nascosto) | ✅ Risolto — `get_reserved_quantity()` spostata in `orders.py` |
| `utils.py` con responsabilità miste (4 funzioni non correlate) | ✅ Risolto — split in `validators.py`, `notifications.py`, `shipping.py`, `utils.py` |
| `legacy_fax.py` decommissionato ma ancora importato | ✅ Risolto — modulo eliminato, zero riferimenti residui |
| `confirm_order` restituiva `None` per ordine inesistente | ✅ Risolto — ora solleva `StockError` coerentemente con gli altri casi |

### ⚠️ Limitazioni strutturali ancora presenti

| Limitazione | Nota |
|---|---|
| Stato completamente volatile (SQLite `:memory:`) | Ogni riavvio azzera ordini, stock e spedizioni. Non affrontato: fuori scope del refactoring |
| `restock()` non persiste su SQLite | Lo stock aggiunto a runtime non sopravvive al riavvio |
| `initialize_stock_cache()` deve essere chiamata prima di `create_shipment_for_order()` | Dipendenza di ordine di inizializzazione non dichiarata esplicitamente |
