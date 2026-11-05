import datetime


def log_event(event, **fields):
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"[{datetime.datetime.now().isoformat()}] {event} {extra}")
