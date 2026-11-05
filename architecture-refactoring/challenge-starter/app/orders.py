from app import db, shipping, warehouse
from app.notifications import notify_customer
from app.utils import log_event


class StockError(Exception):
    pass


def create_order(customer_name, lines):
    order_id = db.execute(
        "INSERT INTO orders (customer_name, status) VALUES (?, 'DRAFT')", (customer_name,)
    )
    for line in lines:
        db.execute(
            "INSERT INTO order_lines (order_id, sku, quantity) VALUES (?, ?, ?)",
            (order_id, line["sku"], line["quantity"]),
        )
    return get_order(order_id)


def get_order(order_id):
    order = db.query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if order is None:
        return None
    lines = db.query_all("SELECT sku, quantity FROM order_lines WHERE order_id = ?", (order_id,))
    order["lines"] = lines
    return order


def list_orders():
    return db.query_all("SELECT id, customer_name, status, created_at FROM orders")


def list_pending_orders_for_sku(sku):
    rows = db.query_all(
        """
        SELECT order_lines.order_id AS order_id, order_lines.quantity AS quantity
        FROM order_lines
        JOIN orders ON orders.id = order_lines.order_id
        WHERE order_lines.sku = ? AND orders.status = 'DRAFT'
        """,
        (sku,),
    )
    return [(row["order_id"], row["quantity"]) for row in rows]


def get_reserved_quantity(sku):
    """How much of this SKU is tied up in DRAFT orders that aren't shipped yet."""
    pending = list_pending_orders_for_sku(sku)
    return sum(line_qty for _order_id, line_qty in pending)


def confirm_order(order_id):
    order = get_order(order_id)
    if order is None:
        raise StockError(f"order {order_id} not found")
    if order["status"] != "DRAFT":
        raise StockError(f"order {order_id} is already {order['status']}")

    for line in order["lines"]:
        try:
            warehouse.check_and_decrement_stock(line["sku"], line["quantity"])
        except ValueError as e:
            raise StockError(str(e))

    db.execute("UPDATE orders SET status = 'CONFIRMED' WHERE id = ?", (order_id,))

    order = get_order(order_id)
    shipment = shipping.create_shipment_for_order(order, order["lines"])
    notify_customer(order, order["lines"])
    log_event("order_confirmed", order_id=order_id)

    order["shipment"] = shipment
    return order


def cancel_order(order_id):
    order = get_order(order_id)
    if order is None:
        return None
    if order["status"] == "CONFIRMED":
        raise StockError(f"order {order_id} is already confirmed, cannot cancel")
    db.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
    return get_order(order_id)
