from app.utils import calculate_shipping_rate, validate_order_payload


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
