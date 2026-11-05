import threading

import pytest

import app.db as db_module
import app.warehouse as warehouse_module
from app.orders import (
    StockError,
    cancel_order,
    confirm_order,
    create_order,
    get_order,
    list_orders,
    list_pending_orders_for_sku,
)


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


# Sub-Task 6 tests -----------------------------------------------------------

def test_create_order():
    order = create_order("Acme Spa", [{"sku": "WIDGET-1", "quantity": 2}])
    assert order is not None
    assert "id" in order
    assert order["status"] == "DRAFT"
    assert order["customer_name"] == "Acme Spa"
    assert len(order["lines"]) == 1
    assert order["lines"][0]["sku"] == "WIDGET-1"


def test_get_order_existing():
    created = create_order("Beta Srl", [{"sku": "WIDGET-2", "quantity": 1}])
    fetched = get_order(created["id"])
    assert fetched is not None
    assert fetched["customer_name"] == "Beta Srl"
    assert fetched["lines"][0]["sku"] == "WIDGET-2"


def test_get_order_nonexistent():
    result = get_order(99999)
    assert result is None


def test_list_orders():
    create_order("Customer A", [{"sku": "WIDGET-1", "quantity": 1}])
    create_order("Customer B", [{"sku": "PALLET-BOX", "quantity": 2}])
    orders = list_orders()
    assert isinstance(orders, list)
    assert len(orders) >= 2


def test_list_pending_orders_for_sku():
    order = create_order("Pending Co", [{"sku": "WIDGET-1", "quantity": 5}])
    pending = list_pending_orders_for_sku("WIDGET-1")
    order_ids = [oid for oid, _qty in pending]
    assert order["id"] in order_ids


def test_confirm_order_success():
    order = create_order("Confirm Co", [{"sku": "WIDGET-1", "quantity": 3}])
    stock_before = warehouse_module.get_stock("WIDGET-1")
    confirmed = confirm_order(order["id"])
    assert confirmed["status"] == "CONFIRMED"
    assert warehouse_module.get_stock("WIDGET-1") == stock_before - 3
    assert "shipment" in confirmed


def test_confirm_order_not_found():
    # ordine inesistente → deve sollevare StockError
    with pytest.raises(StockError):
        confirm_order(99999)


def test_confirm_order_already_confirmed():
    order = create_order("Double Confirm", [{"sku": "WIDGET-2", "quantity": 1}])
    confirm_order(order["id"])
    with pytest.raises(StockError):
        confirm_order(order["id"])


def test_confirm_order_insufficient_stock():
    order = create_order("Greedy Co", [{"sku": "WIDGET-2", "quantity": 99999}])
    with pytest.raises(StockError):
        confirm_order(order["id"])


def test_confirm_order_concurrent_race_condition():
    """Two threads confirm different orders for the same SKU with limited stock.
    Esattamente uno deve riuscire, l'altro deve ricevere StockError (stock insufficiente)."""
    # WIDGET-2 ha 250 unità; ogni ordine chiede 200 → solo uno dei due può passare
    order1 = create_order("Race Alpha", [{"sku": "WIDGET-2", "quantity": 200}])
    order2 = create_order("Race Beta", [{"sku": "WIDGET-2", "quantity": 200}])

    results = {}
    errors = {}

    def confirm(name, order_id):
        try:
            results[name] = confirm_order(order_id)
        except StockError as e:
            errors[name] = e

    t1 = threading.Thread(target=confirm, args=("t1", order1["id"]))
    t2 = threading.Thread(target=confirm, args=("t2", order2["id"]))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Esattamente 1 successo e 1 StockError — il secondo non deve passare
    assert len(errors) == 1, f"Atteso 1 StockError, ricevuti {len(errors)}: {errors}"
    assert len(results) == 1, f"Atteso 1 successo, ricevuti {len(results)}"


def test_cancel_order_draft():
    order = create_order("Cancel Me", [{"sku": "WIDGET-1", "quantity": 1}])
    cancelled = cancel_order(order["id"])
    assert cancelled["status"] == "CANCELLED"


def test_cancel_order_confirmed_raises():
    order = create_order("Confirmed Co", [{"sku": "WIDGET-1", "quantity": 1}])
    confirm_order(order["id"])
    with pytest.raises(StockError):
        cancel_order(order["id"])


def test_cancel_order_not_found():
    # covers orders.py line 86: cancel_order returns None when order not found
    result = cancel_order(99999)
    assert result is None
