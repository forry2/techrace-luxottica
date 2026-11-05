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
