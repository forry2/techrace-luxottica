import random
import string

from app import db, warehouse
from app.utils import log_event


def _generate_tracking_code():
    return "WF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def calculate_shipping_rate(order, lines):
    base_rate = 4.90
    per_item = 0.75
    total_items = sum(l["quantity"] for l in lines)
    return round(base_rate + per_item * total_items, 2)


def create_shipment_for_order(order, lines):
    # Relies on warehouse._STOCK_CACHE already being populated (via
    # warehouse.initialize_stock_cache(), called once at app startup) even
    # though nothing here declares that dependency - calling this before
    # startup has run (e.g. in an isolated unit test) doesn't raise an
    # error, it just silently treats every SKU as having zero stock.
    warehouse_id = None
    for line in lines:
        if warehouse.get_stock(line["sku"]) > 0:
            warehouse_id = warehouse.get_warehouse_for_sku(line["sku"])
            break
    if warehouse_id is None:
        warehouse_id = 1

    rate = calculate_shipping_rate(order, lines)
    tracking_code = _generate_tracking_code()

    shipment_id = db.execute(
        "INSERT INTO shipments (order_id, warehouse_id, tracking_code, status) VALUES (?, ?, ?, 'PENDING')",
        (order["id"], warehouse_id, tracking_code),
    )

    log_event("shipment_created", order_id=order["id"], tracking_code=tracking_code, rate=rate)
    return {
        "id": shipment_id,
        "order_id": order["id"],
        "warehouse_id": warehouse_id,
        "tracking_code": tracking_code,
        "status": "PENDING",
        "rate": rate,
    }


def create_shipment_for_line(order, line):
    """Crea una spedizione dedicata per una singola riga ordine (un articolo)."""
    warehouse_id = warehouse.get_warehouse_for_sku(line["sku"])
    if warehouse_id is None:
        warehouse_id = 1

    rate = calculate_shipping_rate(order, [line])
    tracking_code = _generate_tracking_code()

    shipment_id = db.execute(
        "INSERT INTO shipments (order_id, warehouse_id, tracking_code, status) VALUES (?, ?, ?, 'PENDING')",
        (order["id"], warehouse_id, tracking_code),
    )

    log_event(
        "shipment_created",
        order_id=order["id"],
        sku=line["sku"],
        tracking_code=tracking_code,
        rate=rate,
    )
    return {
        "id": shipment_id,
        "order_id": order["id"],
        "warehouse_id": warehouse_id,
        "tracking_code": tracking_code,
        "sku": line["sku"],
        "quantity": line["quantity"],
        "status": "PENDING",
        "rate": rate,
    }


def list_shipments():
    return db.query_all("SELECT * FROM shipments")
