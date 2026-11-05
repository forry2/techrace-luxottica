import datetime


def log_event(event, **fields):
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"[{datetime.datetime.now().isoformat()}] {event} {extra}")


def validate_order_payload(payload):
    if not isinstance(payload, dict):
        return "payload must be a JSON object"
    if not payload.get("customer_name"):
        return "customer_name is required"
    lines = payload.get("lines")
    if not lines or not isinstance(lines, list):
        return "lines must be a non-empty list"
    for line in lines:
        if not line.get("sku") or not isinstance(line.get("quantity"), int) or line["quantity"] <= 0:
            return "each line needs a sku and a positive integer quantity"
    return None


def format_notification_email(order, lines):
    items = "\n".join(f"  - {l['sku']} x{l['quantity']}" for l in lines)
    return (
        f"Subject: Order #{order['id']} confirmed\n\n"
        f"Hi {order['customer_name']},\n\n"
        f"Your order has been confirmed:\n{items}\n\nThanks,\nNordShip"
    )


def calculate_shipping_rate(order, lines):
    base_rate = 4.90
    per_item = 0.75
    total_items = sum(l["quantity"] for l in lines)
    return round(base_rate + per_item * total_items, 2)
