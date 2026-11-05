from app.notifications import notify_customer


# Sub-Task 5 tests -----------------------------------------------------------

def test_notify_customer_returns_email_body():
    order = {"id": 42, "customer_name": "Giulia Bianchi"}
    lines = [{"sku": "WIDGET-1", "quantity": 1}, {"sku": "WIDGET-2", "quantity": 2}]
    result = notify_customer(order, lines)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Giulia Bianchi" in result
    assert "WIDGET-1" in result


def test_notify_customer_logs_event(capsys):
    order = {"id": 99, "customer_name": "Luca Verdi"}
    lines = [{"sku": "PALLET-BOX", "quantity": 3}]
    notify_customer(order, lines)
    captured = capsys.readouterr()
    assert "notification_sent" in captured.out
    assert "order_id=99" in captured.out
