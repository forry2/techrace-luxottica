import app.db as db_module


def _reset_db():
    """Force re-initialization on the next init_db() call."""
    db_module._initialized = False
    db_module._connection = None


def setup_function():
    _reset_db()
    db_module.init_db()


def teardown_function():
    _reset_db()


# Sub-Task 2 tests -----------------------------------------------------------

def test_init_db_creates_tables():
    tables = db_module.query_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = {row["name"] for row in tables}
    assert {"warehouses", "stock", "orders", "order_lines", "shipments"}.issubset(table_names)


def test_init_db_seeds_warehouses():
    rows = db_module.query_all("SELECT * FROM warehouses")
    assert len(rows) == 3


def test_init_db_seeds_stock():
    rows = db_module.query_all("SELECT * FROM stock")
    assert len(rows) == 4


def test_execute_and_query_one():
    row_id = db_module.execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, ?)",
        ("Test Customer", "DRAFT"),
    )
    row = db_module.query_one("SELECT * FROM orders WHERE id = ?", (row_id,))
    assert row is not None
    assert row["customer_name"] == "Test Customer"
    assert row["status"] == "DRAFT"


def test_query_all_returns_list():
    result = db_module.query_all("SELECT * FROM warehouses")
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)


def test_query_one_returns_none_when_missing():
    row = db_module.query_one("SELECT * FROM orders WHERE id = ?", (99999,))
    assert row is None


def test_init_db_idempotent():
    """Calling init_db() a second time is a no-op (guarded by _initialized)."""
    db_module.init_db()  # already initialized in setup_function; should return immediately
    rows = db_module.query_all("SELECT * FROM warehouses")
    assert len(rows) == 3
