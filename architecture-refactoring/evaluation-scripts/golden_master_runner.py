#!/usr/bin/env python3
"""Fixed request sequence for check_golden_master.sh's capture/verify modes.

Usage:
    python3 golden_master_runner.py capture|verify <base_url> <file>

Assumes a freshly started app instance (seed data intact, nothing posted yet).
The expected values follow WareFlow's seed data (challenge-starter/app/db.py):
WIDGET-1=1300 (1000+300 across two warehouses), WIDGET-2=250, PALLET-BOX=500,
3 warehouses, no orders.

Two fields differ on every run and are stripped before comparing:
orders.created_at (wall-clock timestamp) and shipments.tracking_code (random).
"""
import json
import sys
import urllib.error
import urllib.request

VOLATILE_FIELDS = {"created_at", "tracking_code"}


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def request(base_url, method, path, body=None):
    url = base_url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            payload = json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = json.loads(e.read().decode("utf-8") or "null")
        except Exception:
            payload = None
    except Exception as e:
        status = 0
        payload = {"_runner_error": str(e)}
    return status, payload


def build_sequence():
    return [
        {"name": "list_warehouses", "method": "GET", "path": "/warehouses"},
        {"name": "stock_widget1", "method": "GET", "path": "/stock/WIDGET-1"},
        {"name": "stock_widget2", "method": "GET", "path": "/stock/WIDGET-2"},
        {"name": "stock_palletbox", "method": "GET", "path": "/stock/PALLET-BOX"},
        {"name": "list_orders_empty", "method": "GET", "path": "/orders"},
        {"name": "get_missing_order", "method": "GET", "path": "/orders/999"},
        {
            "name": "create_order_invalid",
            "method": "POST",
            "path": "/orders",
            "body": {"lines": [{"sku": "WIDGET-2", "quantity": 1}]},
        },
        {
            "name": "create_order_valid",
            "method": "POST",
            "path": "/orders",
            "body": {"customer_name": "Golden Master Probe", "lines": [{"sku": "WIDGET-2", "quantity": 2}]},
        },
        {"name": "confirm_order_1", "method": "POST", "path": "/orders/1/confirm"},
        {"name": "stock_widget2_after_confirm", "method": "GET", "path": "/stock/WIDGET-2"},
        {"name": "cancel_confirmed_order_1", "method": "POST", "path": "/orders/1/cancel"},
        {"name": "list_shipments_after", "method": "GET", "path": "/shipments"},
    ]


def run_sequence(base_url):
    results = []
    for step in build_sequence():
        status, payload = request(base_url, step["method"], step["path"], step.get("body"))
        results.append(
            {
                "name": step["name"],
                "method": step["method"],
                "path": step["path"],
                "body": step.get("body"),
                "status": status,
                "response": strip_volatile(payload),
            }
        )
    return results


def capture(base_url, outfile):
    results = run_sequence(base_url)
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"[GOLDEN] captured {len(results)} steps to {outfile}")
    return 0


def verify(base_url, golden_file):
    try:
        with open(golden_file) as f:
            golden = json.load(f)
    except FileNotFoundError:
        print(f"[GOLDEN] golden master file not found: {golden_file}")
        return 1

    current = run_sequence(base_url)
    if len(current) != len(golden):
        print(f"[GOLDEN] step count mismatch: golden={len(golden)} current={len(current)}")
        return 1

    ok = True
    for expected, actual in zip(golden, current):
        name = expected["name"]
        if expected["status"] != actual["status"]:
            print(f"[GOLDEN]   MISMATCH {name}: status {expected['status']} -> {actual['status']}")
            ok = False
            continue
        if expected["response"] != actual["response"]:
            print(f"[GOLDEN]   MISMATCH {name}: response changed")
            print(f"[GOLDEN]     expected: {json.dumps(expected['response'])}")
            print(f"[GOLDEN]     actual:   {json.dumps(actual['response'])}")
            ok = False
    if ok:
        print(f"[GOLDEN] all {len(golden)} steps match")
    return 0 if ok else 1


def main():
    if len(sys.argv) != 4:
        print("usage: golden_master_runner.py capture|verify <base_url> <file>", file=sys.stderr)
        return 2
    mode, base_url, file_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    if mode == "capture":
        return capture(base_url, file_arg)
    return verify(base_url, file_arg)


if __name__ == "__main__":
    sys.exit(main())
