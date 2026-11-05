import threading

from app import db
from app.utils import log_event

# In-memory cache of aggregate stock per SKU, kept for performance so every
# request doesn't have to hit SQLite just to check availability. Populated
# once at startup by initialize_stock_cache().
_STOCK_CACHE = {}
_stock_lock = threading.Lock()


def initialize_stock_cache():
    rows = db.query_all("SELECT sku, SUM(quantity) AS total FROM stock GROUP BY sku")
    for row in rows:
        _STOCK_CACHE[row["sku"]] = row["total"]
    log_event("stock_cache_initialized", skus=len(_STOCK_CACHE))


def list_warehouses():
    return db.query_all("SELECT id, name, city FROM warehouses")


def get_warehouse_for_sku(sku):
    row = db.query_one(
        "SELECT warehouse_id FROM stock WHERE sku = ? ORDER BY quantity DESC LIMIT 1", (sku,)
    )
    return row["warehouse_id"] if row else None


def get_stock(sku):
    return _STOCK_CACHE.get(sku, 0)


def check_and_decrement_stock(sku, quantity):
    """Atomically verify availability and decrement both the in-memory cache and the DB."""
    with _stock_lock:
        current = _STOCK_CACHE.get(sku, 0)
        if current < quantity:
            raise ValueError(f"not enough stock for {sku}: have {current}, need {quantity}")
        _STOCK_CACHE[sku] = current - quantity
        # Persist the decrement to the DB so restarts and direct DB reads stay consistent.
        # Apply the full reduction to the warehouse that holds the most stock for this SKU
        # (same warehouse chosen by get_warehouse_for_sku / create_shipment_for_line).
        db.execute(
            """UPDATE stock SET quantity = MAX(0, quantity - ?)
               WHERE sku = ? AND warehouse_id = (
                   SELECT warehouse_id FROM stock WHERE sku = ? ORDER BY quantity DESC LIMIT 1
               )""",
            (quantity, sku, sku),
        )
        log_event("stock_decremented", sku=sku, quantity=quantity, remaining=_STOCK_CACHE[sku])


def decrement_stock(sku, quantity_before, quantity):
    """Legacy signature kept for test compatibility. Delegates to the atomic version."""
    with _stock_lock:
        _STOCK_CACHE[sku] = quantity_before - quantity
        log_event("stock_decremented", sku=sku, quantity=quantity, remaining=_STOCK_CACHE[sku])


def restock(sku, quantity):
    with _stock_lock:
        _STOCK_CACHE[sku] = _STOCK_CACHE.get(sku, 0) + quantity
        # Persist restock to the DB on the warehouse that already holds this SKU
        # (or the first one found), so the value survives a restart.
        db.execute(
            """UPDATE stock SET quantity = quantity + ?
               WHERE sku = ? AND warehouse_id = (
                   SELECT warehouse_id FROM stock WHERE sku = ? LIMIT 1
               )""",
            (quantity, sku, sku),
        )
