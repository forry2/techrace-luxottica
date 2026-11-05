_VALID_SKUS = {"WIDGET-1", "WIDGET-2", "PALLET-BOX"}


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
        if line["sku"] not in _VALID_SKUS:
            return f"SKU '{line['sku']}' non valido. SKU disponibili: {', '.join(sorted(_VALID_SKUS))}"
    return None
