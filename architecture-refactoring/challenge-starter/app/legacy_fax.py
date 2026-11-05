# Fax notification gateway integration. The fax line was decommissioned
# years ago when NordShip switched to email, but nobody ever removed this
# module or the code that imports it.

FAX_GATEWAY_HOST = "10.0.0.17"  # old on-prem fax server, long gone


def send_fax_notification(order, fax_number):
    raise NotImplementedError(
        f"Fax gateway at {FAX_GATEWAY_HOST} has been decommissioned - "
        f"cannot fax order #{order['id']} to {fax_number}"
    )
