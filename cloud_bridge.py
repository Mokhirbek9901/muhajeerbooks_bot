import json
import os
import time
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")

_TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
_MAX_RPC_ATTEMPTS = 3


def configured():
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET)


def rpc(name, payload):
    if not configured():
        raise RuntimeError("Supabase sync sozlanmagan")

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None

    for attempt in range(_MAX_RPC_ATTEMPTS):
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
            last_error = RuntimeError(
                f"Supabase HTTP {exc.code}: {detail or str(exc)}"
            )
            if exc.code in _TRANSIENT_HTTP_CODES and attempt < _MAX_RPC_ATTEMPTS - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise last_error from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = RuntimeError(f"Supabase vaqtincha ulanmayapti: {exc}")
            if attempt < _MAX_RPC_ATTEMPTS - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise last_error from exc

    raise last_error or RuntimeError("Supabase RPC bajarilmadi")


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


def sales_list(limit=5000):
    result = rpc(
        "bot_sales_list",
        {"p_secret": SYNC_SECRET, "p_limit": int(limit)},
    )
    return result if isinstance(result, list) else []


def finance_report(period="month"):
    result = rpc(
        "bot_finance_report",
        {"p_secret": SYNC_SECRET, "p_period": str(period or "month")},
    )
    return result if isinstance(result, dict) else {}


def add_finance_expense(amount, category="postage", note="", expense_date=None):
    payload = {
        "p_secret": SYNC_SECRET,
        "p_amount": int(amount),
        "p_category": str(category or "postage"),
        "p_note": str(note or ""),
    }
    if expense_date:
        payload["p_expense_date"] = str(expense_date)
    return rpc("bot_add_finance_expense", payload)


def shipping_queue_list():
    result = rpc(
        "bot_shipping_queue_list",
        {"p_secret": SYNC_SECRET},
    )
    return result if isinstance(result, list) else []


def shipping_queue_add(name, phone, address, books, address_photo_file_id=""):
    return rpc(
        "bot_shipping_queue_add",
        {
            "p_secret": SYNC_SECRET,
            "p_name": str(name or "").strip(),
            "p_phone": str(phone or "").strip(),
            "p_address": str(address or "").strip(),
            "p_books": str(books or "").strip(),
            "p_address_photo_file_id": str(address_photo_file_id or "").strip(),
        },
    )


def shipping_queue_dismiss(kind, queue_id):
    normalized_kind = {
        "m": "manual",
        "o": "order",
        "manual": "manual",
        "order": "order",
    }.get(str(kind or "").strip())
    if not normalized_kind:
        raise ValueError("Zakas turi noto‘g‘ri")
    return rpc(
        "bot_shipping_queue_dismiss",
        {
            "p_secret": SYNC_SECRET,
            "p_kind": normalized_kind,
            "p_id": str(queue_id or "").strip(),
        },
    )


def mark_instagram_order(cloud_id):
    return rpc(
        "bot_mark_instagram_order",
        {"p_secret": SYNC_SECRET, "p_cloud_id": str(cloud_id)},
    )


def delete_book(book):
    cloud_id = str(book.get("cloud_id") or "").strip() or None
    try:
        telegram_id = int(book.get("id") or 0)
    except Exception:
        telegram_id = None
    payload = {
        "p_secret": SYNC_SECRET,
        "p_telegram_id": telegram_id if telegram_id and telegram_id > 0 else None,
        "p_cloud_id": cloud_id,
    }
    result = rpc("bot_sync_delete", payload)
    try:
        deleted = int(result or 0)
    except Exception:
        deleted = 0
    if deleted <= 0:
        raise RuntimeError("Kitob server katalogidan o‘chirilmadi. Qayta urinib ko‘ring.")
    return deleted
