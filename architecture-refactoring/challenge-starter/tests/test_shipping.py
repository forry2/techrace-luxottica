import re

import app.db as db_module
import app.warehouse as warehouse_module
from app.shipping import _generate_tracking_code, create_shipment_for_order, list_shipments


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


# Sub-Task 4 tests -----------------------------------------------------------

def test_generate_tracking_code():
    code = _generate_tracking_code()
    # Format: "WF-" + 8 uppercase alphanum chars
    assert re.match(r"^WF-[A-Z0-9]{8}$", code), f"Unexpected format: {code}"


def test_list_shipments_empty():
    assert list_shipments() == []


def test_create_shipment_for_order():
    order_id = db_module.execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, 'DRAFT')", ("Acme Spa",)
    )
    order = {"id": order_id, "customer_name": "Acme Spa"}
    lines = [{"sku": "WIDGET-1", "quantity": 2}]

    shipment = create_shipment_for_order(order, lines)

    assert shipment["status"] == "PENDING"
    assert shipment["order_id"] == order_id
    assert shipment["tracking_code"].startswith("WF-")
    assert "rate" in shipment


def test_list_shipments_after_create():
    order_id = db_module.execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, 'DRAFT')", ("Beta Srl",)
    )
    order = {"id": order_id, "customer_name": "Beta Srl"}
    lines = [{"sku": "PALLET-BOX", "quantity": 1}]
    create_shipment_for_order(order, lines)

    shipments = list_shipments()
    assert len(shipments) == 1
    assert shipments[0]["order_id"] == order_id


def test_create_shipment_fallback_warehouse():
    # covers shipping.py line 24: warehouse_id = 1 when no SKU has stock
    warehouse_module._STOCK_CACHE.clear()  # empty cache → all get_stock() return 0
    order_id = db_module.execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, 'DRAFT')", ("Gamma Co",)
    )
    order = {"id": order_id, "customer_name": "Gamma Co"}
    lines = [{"sku": "NONEXISTENT-SKU", "quantity": 1}]
    shipment = create_shipment_for_order(order, lines)
    assert shipment["warehouse_id"] == 1
