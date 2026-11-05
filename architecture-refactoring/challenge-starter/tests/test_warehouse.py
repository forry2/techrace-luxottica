import app.db as db_module
import app.warehouse as warehouse_module
from app.orders import get_reserved_quantity


def _reset_db():
    db_module._initialized = False
    db_module._connection = None


def setup_function():
    _reset_db()
    db_module.init_db()
    warehouse_module._STOCK_CACHE.clear()
    warehouse_module.initialize_stock_cache()


def teardown_function():
    warehouse_module._STOCK_CACHE.clear()
    _reset_db()


# Sub-Task 3 tests -----------------------------------------------------------

def test_initialize_stock_cache_populates_cache():
    assert len(warehouse_module._STOCK_CACHE) > 0


def test_initialize_stock_cache_known_sku():
    # WIDGET-1 exists in warehouses 1 and 3 (seed: 1000 + 300 = 1300)
    assert warehouse_module._STOCK_CACHE.get("WIDGET-1", 0) == 1300


def test_list_warehouses():
    warehouses = warehouse_module.list_warehouses()
    assert isinstance(warehouses, list)
    assert len(warehouses) >= 3
    names = {w["name"] for w in warehouses}
    assert "Milano Nord" in names


def test_get_warehouse_for_sku_known():
    wid = warehouse_module.get_warehouse_for_sku("WIDGET-1")
    assert wid is not None
    assert isinstance(wid, int)


def test_get_warehouse_for_sku_unknown():
    wid = warehouse_module.get_warehouse_for_sku("NONEXISTENT-SKU")
    assert wid is None


def test_get_stock_returns_quantity():
    qty = warehouse_module.get_stock("WIDGET-1")
    assert qty > 0


def test_get_stock_returns_zero_for_unknown_sku():
    qty = warehouse_module.get_stock("NONEXISTENT-SKU")
    assert qty == 0


def test_decrement_stock():
    before = warehouse_module.get_stock("WIDGET-2")
    warehouse_module.decrement_stock("WIDGET-2", before, 10)
    assert warehouse_module.get_stock("WIDGET-2") == before - 10


def test_restock():
    before = warehouse_module.get_stock("PALLET-BOX")
    warehouse_module.restock("PALLET-BOX", 50)
    assert warehouse_module.get_stock("PALLET-BOX") == before + 50


def test_get_reserved_quantity_empty():
    # No DRAFT orders exist yet, so reserved qty is 0
    qty = get_reserved_quantity("WIDGET-1")
    assert qty == 0


# ---------------------------------------------------------------------------
# Regression tests — DB persistence of stock changes (fix for lost-update bug)
# ---------------------------------------------------------------------------

def test_check_and_decrement_stock_persists_to_db():
    """After check_and_decrement_stock the DB total for the SKU must decrease."""
    sku = "WIDGET-1"
    db_before = sum(
        r["quantity"] for r in db_module.query_all("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    )
    warehouse_module.check_and_decrement_stock(sku, 5)
    db_after = sum(
        r["quantity"] for r in db_module.query_all("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    )
    assert db_after == db_before - 5, (
        f"DB not updated after decrement: expected {db_before - 5}, got {db_after}"
    )


def test_restock_persists_to_db():
    """After restock() the DB total for the SKU must increase."""
    sku = "PALLET-BOX"
    db_before = sum(
        r["quantity"] for r in db_module.query_all("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    )
    warehouse_module.restock(sku, 20)
    db_after = sum(
        r["quantity"] for r in db_module.query_all("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    )
    assert db_after == db_before + 20, (
        f"DB not updated after restock: expected {db_before + 20}, got {db_after}"
    )


def test_stock_cache_matches_db_after_operations():
    """After a decrement and a restock the cache total must equal the DB total."""
    sku = "WIDGET-2"
    warehouse_module.check_and_decrement_stock(sku, 10)
    warehouse_module.restock(sku, 5)
    cache_total = warehouse_module.get_stock(sku)
    db_total = sum(
        r["quantity"] for r in db_module.query_all("SELECT quantity FROM stock WHERE sku = ?", (sku,))
    )
    assert cache_total == db_total, (
        f"Cache/DB diverged after operations: cache={cache_total}, db={db_total}"
    )
