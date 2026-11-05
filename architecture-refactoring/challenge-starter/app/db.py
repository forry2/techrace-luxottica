import sqlite3
import threading

_init_lock = threading.Lock()
_initialized = False

# A single persistent in-memory connection, shared by every request thread.
# Python's sqlite3 module does not make concurrent execute() calls on the
# SAME Connection object safe on its own (even with check_same_thread=False
# and an underlying SQLite built in serialized mode) - calling it from
# multiple threads at once without this lock produces InterfaceError: "bad
# parameter or other API misuse", or silently wrong reads. This lock only
# protects access to SQLite itself; it does NOT guard the in-memory stock
# cache in warehouse.py, which is deliberately left unsynchronized.
_connection = None
_db_lock = threading.Lock()


def query_all(sql, params=()):
    with _db_lock:
        rows = _connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def query_one(sql, params=()):
    with _db_lock:
        row = _connection.execute(sql, params).fetchone()
        return dict(row) if row is not None else None


def execute(sql, params=()):
    with _db_lock:
        cur = _connection.execute(sql, params)
        _connection.commit()
        return cur.lastrowid


def init_db():
    global _initialized, _connection
    with _init_lock:
        if _initialized:
            return
        _connection = sqlite3.connect(":memory:", check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        conn = _connection
        conn.executescript(
            """
            CREATE TABLE warehouses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL
            );

            CREATE TABLE stock (
                sku TEXT NOT NULL,
                warehouse_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                PRIMARY KEY (sku, warehouse_id)
            );

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE order_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL
            );

            CREATE TABLE shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                tracking_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
            );
            """
        )
        conn.executemany(
            "INSERT INTO warehouses (name, city) VALUES (?, ?)",
            [("Milano Nord", "Milano"), ("Bologna Est", "Bologna"), ("Torino Sud", "Torino")],
        )
        conn.executemany(
            "INSERT INTO stock (sku, warehouse_id, name, quantity) VALUES (?, ?, ?, ?)",
            [
                ("WIDGET-1", 1, "Widget standard", 1000),
                ("WIDGET-2", 1, "Widget rinforzato", 250),
                ("PALLET-BOX", 2, "Scatola pallet", 500),
                ("WIDGET-1", 3, "Widget standard", 300),
            ],
        )
        conn.commit()
        _initialized = True
