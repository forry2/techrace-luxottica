import pytest


# legacy_fax.py was removed as dead code: the fax gateway was decommissioned
# and the module was never called from any active code path.
@pytest.mark.skip(reason="legacy_fax module removed — fax gateway decommissioned")
def test_send_fax_notification_raises():
    pass
