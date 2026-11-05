from app.notifications import format_notification_email
from app.shipping import calculate_shipping_rate
from app.utils import log_event
from app.validators import validate_order_payload


def test_validate_order_payload_rejects_missing_customer():
    error = validate_order_payload({"lines": [{"sku": "WIDGET-1", "quantity": 1}]})
    assert error is not None


def test_validate_order_payload_accepts_valid_payload():
    error = validate_order_payload(
        {"customer_name": "Acme Spa", "lines": [{"sku": "WIDGET-1", "quantity": 2}]}
    )
    assert error is None


def test_calculate_shipping_rate():
    rate = calculate_shipping_rate({}, [{"sku": "WIDGET-1", "quantity": 2}])
    assert rate == 6.40


# --- Sub-Task 1: cover remaining lines in utils.py ---

def test_log_event_prints_output(capsys):
    log_event("test_event", key="val", num=42)
    captured = capsys.readouterr()
    assert "test_event" in captured.out
    assert "key=val" in captured.out
    assert "num=42" in captured.out


def test_validate_order_payload_missing_customer_name():
    error = validate_order_payload({"customer_name": "", "lines": [{"sku": "X", "quantity": 1}]})
    assert error == "customer_name is required"


def test_validate_order_payload_lines_not_list():
    error = validate_order_payload({"customer_name": "Acme", "lines": "bad"})
    assert error == "lines must be a non-empty list"


def test_validate_order_payload_lines_empty():
    error = validate_order_payload({"customer_name": "Acme", "lines": []})
    assert error == "lines must be a non-empty list"


def test_validate_order_payload_not_a_dict():
    # covers utils.py line 11: payload must be a JSON object
    error = validate_order_payload("not a dict")
    assert error == "payload must be a JSON object"


def test_validate_order_payload_bad_line_item():
    # covers utils.py line 19: each line needs a sku and positive quantity
    error = validate_order_payload(
        {"customer_name": "Acme", "lines": [{"sku": "", "quantity": 1}]}
    )
    assert error == "each line needs a sku and a positive integer quantity"


def test_format_notification_email():
    order = {"id": 7, "customer_name": "Mario Rossi"}
    lines = [{"sku": "WIDGET-1", "quantity": 3}, {"sku": "PALLET-BOX", "quantity": 1}]
    result = format_notification_email(order, lines)
    assert "Mario Rossi" in result
    assert "WIDGET-1" in result
    assert "PALLET-BOX" in result
    assert "Order #7" in result
