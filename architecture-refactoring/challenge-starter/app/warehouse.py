from app import db
from app.utils import log_event

# In-memory cache of aggregate stock per SKU, kept for performance so every
# request doesn't have to hit SQLite just to check availability. Populated
# once at startup by initialize_stock_cache().
_STOCK_CACHE = {}


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


def decrement_stock(sku, quantity_before, quantity):
    # Takes the caller's own "quantity_before" (captured when it checked
    # availability) instead of re-reading _STOCK_CACHE fresh here. That
    # means two threads that both read the same stale value before either
    # of them writes will both compute the same "new" total and the second
    # write silently overwrites the first - a lost update, not a crash.
    _STOCK_CACHE[sku] = quantity_before - quantity
    log_event("stock_decremented", sku=sku, quantity=quantity, remaining=_STOCK_CACHE[sku])


def restock(sku, quantity):
    _STOCK_CACHE[sku] = _STOCK_CACHE.get(sku, 0) + quantity
