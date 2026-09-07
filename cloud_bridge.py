import json
import os
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")


def configured():
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET)


def rpc(name, payload):
    if not configured():
        raise RuntimeError("Supabase sync sozlanmagan")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}",
        data=body,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        raise RuntimeError(detail or str(exc)) from exc


def create_order(order, preserve_stock=False):
    return rpc(
        "bot_order_create",
        {
            "p_secret": SYNC_SECRET,
            "p_order": order,
            "p_preserve_stock": bool(preserve_stock),
        },
    )


def set_order_status(order, status):
    cloud_id = str(order.get("cloud_order_id") or "").strip() or None
    try:
        order_number = int(order.get("order_id") or 0)
    except Exception:
        order_number = None
    return rpc(
        "bot_order_set_status",
        {
            "p_secret": SYNC_SECRET,
            "p_status": status,
            "p_cloud_id": cloud_id,
            "p_order_number": order_number,
        },
    )


def delete_book(book):
    cloud_id = str(book.get("cloud_id") or "").strip() or None
    try:
        telegram_id = int(book.get("id") or 0)
    except Exception:
        telegram_id = None
    return rpc(
        "bot_sync_delete",
        {
            "p_secret": SYNC_SECRET,
            "p_telegram_id": telegram_id if telegram_id and telegram_id > 0 else None,
            "p_cloud_id": cloud_id,
        },
    )
