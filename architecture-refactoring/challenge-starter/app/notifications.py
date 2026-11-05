from app import legacy_fax  # noqa: F401 - unused, kept from the old fax workflow
from app.utils import format_notification_email, log_event


def notify_customer(order, lines):
    email_body = format_notification_email(order, lines)
    log_event("notification_sent", order_id=order["id"], channel="email")
    return email_body
