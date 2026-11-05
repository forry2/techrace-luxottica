import pytest

from app.legacy_fax import FAX_GATEWAY_HOST, send_fax_notification


# Sub-Task 7 tests -----------------------------------------------------------

def test_send_fax_notification_raises():
    with pytest.raises(NotImplementedError) as exc_info:
        send_fax_notification({"id": 1}, "123456")
    assert FAX_GATEWAY_HOST in str(exc_info.value)
    assert "1" in str(exc_info.value)
    assert "123456" in str(exc_info.value)
