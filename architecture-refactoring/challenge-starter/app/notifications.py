from app.utils import log_event


def format_notification_email(order, lines):
    items = "\n".join(f"  - {l['sku']} x{l['quantity']}" for l in lines)
    return (
        f"Subject: Order #{order['id']} confirmed\n\n"
        f"Hi {order['customer_name']},\n\n"
        f"Your order has been confirmed:\n{items}\n\nThanks,\nNordShip"
    )


def notify_customer(order, lines):
    email_body = format_notification_email(order, lines)
    log_event("notification_sent", order_id=order["id"], channel="email")
    return email_body
