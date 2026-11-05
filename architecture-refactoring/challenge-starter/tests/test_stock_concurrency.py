"""
Regression tests for M4 — race condition on _STOCK_CACHE.

Root cause: before the fix, `confirm_order` read the stock value from _STOCK_CACHE,
did some work (simulated by time.sleep), then wrote back a decremented value computed
from the stale read. Two concurrent threads would both read the same value and the
second write would silently overwrite the first (lost update).

Fix: `warehouse.check_and_decrement_stock()` acquires `_stock_lock` and performs
the read-check-write as a single atomic operation, so concurrent threads are
serialised at the cache level.
"""

import threading

import app.db as db_module
import app.warehouse as warehouse_module
from app.orders import StockError, confirm_order, create_order


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


# ---------------------------------------------------------------------------
# M4 regression test — 50 concurrent confirmations on the same SKU
# ---------------------------------------------------------------------------

def test_50_concurrent_confirmations_exact_stock():
    """50 threads each try to confirm an order of 1 unit for WIDGET-1.
    WIDGET-1 starts with 1300 units (seed: 1000 + 300 across two warehouses).
    All 50 should succeed. Final stock must be exactly 1300 - 50 = 1250.
    With the old lost-update bug the final value would be unpredictably wrong
    (always lower than the true remainder, as described by NordShip).
    """
    sku = "WIDGET-1"
    n_orders = 50
    qty_per_order = 1
    initial_stock = warehouse_module.get_stock(sku)

    # Pre-create all orders in DRAFT state (sequential, no concurrency yet).
    order_ids = [
        create_order(f"Customer {i}", [{"sku": sku, "quantity": qty_per_order}])["id"]
        for i in range(n_orders)
    ]

    results = {}
    errors = {}

    def confirm(order_id):
        try:
            results[order_id] = confirm_order(order_id)
        except StockError as e:
            errors[order_id] = str(e)

    threads = [threading.Thread(target=confirm, args=(oid,)) for oid in order_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_stock = warehouse_module.get_stock(sku)
    confirmed = len(results)
    failed = len(errors)
    total_decremented = confirmed * qty_per_order

    assert failed == 0, (
        f"Expected all 50 confirmations to succeed (stock was sufficient), "
        f"but {failed} failed: {list(errors.values())[:3]}"
    )
    assert confirmed == n_orders, f"Expected {n_orders} confirmed, got {confirmed}"
    assert final_stock == initial_stock - total_decremented, (
        f"Stock mismatch — lost update detected! "
        f"Expected {initial_stock - total_decremented}, got {final_stock}. "
        f"Difference: {final_stock - (initial_stock - total_decremented)} units."
    )


def test_50_concurrent_confirmations_stock_never_goes_negative():
    """50 threads each request 30 units of WIDGET-2 (seed: 250 units total).
    Only 8 can succeed (8 * 30 = 240 <= 250; 9 * 30 = 270 > 250).
    The test checks that stock never goes below 0 and that the arithmetic
    is exact: confirmed_count * 30 + final_stock == 250.
    """
    sku = "WIDGET-2"
    qty_per_order = 30
    initial_stock = warehouse_module.get_stock(sku)  # 250
    n_orders = 50

    order_ids = [
        create_order(f"Stress {i}", [{"sku": sku, "quantity": qty_per_order}])["id"]
        for i in range(n_orders)
    ]

    results = {}
    errors = {}

    def confirm(order_id):
        try:
            results[order_id] = confirm_order(order_id)
        except StockError as e:
            errors[order_id] = str(e)

    threads = [threading.Thread(target=confirm, args=(oid,)) for oid in order_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_stock = warehouse_module.get_stock(sku)
    confirmed = len(results)

    assert final_stock >= 0, f"Stock went negative: {final_stock}"
    assert final_stock == initial_stock - confirmed * qty_per_order, (
        f"Stock arithmetic is wrong — lost update detected! "
        f"initial={initial_stock}, confirmed={confirmed}, qty={qty_per_order}, "
        f"expected final={initial_stock - confirmed * qty_per_order}, got={final_stock}"
    )


def test_concurrent_restock_and_confirm_exact_result():
    """Interleave 20 restock(+10) calls with 20 confirm(1 unit) calls on WIDGET-1.
    The final stock must equal: initial + 20*10 - confirmed_count * 1.
    Checks that restock() and check_and_decrement_stock() share the same lock
    and cannot interleave incorrectly.
    """
    sku = "WIDGET-1"
    initial_stock = warehouse_module.get_stock(sku)

    order_ids = [
        create_order(f"Mix {i}", [{"sku": sku, "quantity": 1}])["id"]
        for i in range(20)
    ]

    confirm_results = {}
    confirm_errors = {}
    restock_done = []

    def do_confirm(order_id):
        try:
            confirm_results[order_id] = confirm_order(order_id)
        except StockError as e:
            confirm_errors[order_id] = str(e)

    def do_restock():
        warehouse_module.restock(sku, 10)
        restock_done.append(1)

    threads = (
        [threading.Thread(target=do_confirm, args=(oid,)) for oid in order_ids]
        + [threading.Thread(target=do_restock) for _ in range(20)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_stock = warehouse_module.get_stock(sku)
    total_restocked = len(restock_done) * 10
    total_confirmed = len(confirm_results)
    expected = initial_stock + total_restocked - total_confirmed * 1

    assert final_stock == expected, (
        f"Stock mismatch under mixed restock+confirm load. "
        f"initial={initial_stock}, restocked={total_restocked}, "
        f"confirmed={total_confirmed}, expected={expected}, got={final_stock}"
    )
