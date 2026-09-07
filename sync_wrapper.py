import base64
import hashlib
import json
import os
import runpy
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
DATA_DIR = "/data" if os.path.isdir("/data") else "."
BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
SYNC_INTERVAL = 2


def _rpc(name, payload):
    if not (SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET):
        raise RuntimeError("Supabase sync sozlanmagan")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}",
        data=body,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return default


def _write_json(path, data):
    tmp = path + ".cloud.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_books():
    data = _read_json(BOOKS_FILE, [])
    return data if isinstance(data, list) else []


def _write_books(data):
    _write_json(BOOKS_FILE, data)


def _read_orders():
    data = _read_json(ORDERS_FILE, {})
    return data if isinstance(data, dict) else {}


def _write_orders(data):
    _write_json(ORDERS_FILE, data)


def _hash(data):
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _push(local_books):
    if not local_books:
        return 0
    return _rpc("bot_sync_push_safe", {"p_secret": SYNC_SECRET, "p_books": local_books})


def _pull_rows():
    result = _rpc("bot_sync_pull", {"p_secret": SYNC_SECRET})
    return result if isinstance(result, list) else []


def _pull_orders():
    result = _rpc("bot_orders_pull", {"p_secret": SYNC_SECRET})
    return result if isinstance(result, list) else []


def _telegram_photo(file_id):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        data=urllib.parse.urlencode({"file_id": file_id}).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    file_path = str((result.get("result") or {}).get("file_path") or "")
    if not file_path:
        raise RuntimeError("Telegram rasm fayli topilmadi")
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        content = resp.read()
    if not content:
        raise RuntimeError("Telegramdan bo‘sh rasm keldi")
    if len(content) > 7_000_000:
        raise RuntimeError("Telegram rasmi 7 MB dan katta")
    lower = file_path.lower()
    if lower.endswith(".png"):
        return content, "telegram-cover.png", "image/png"
    if lower.endswith(".webp"):
        return content, "telegram-cover.webp", "image/webp"
    return content, "telegram-cover.jpg", "image/jpeg"


def _upload_telegram_cover(book_id, photo_id):
    content, file_name, content_type = _telegram_photo(photo_id)
    payload = {
        "sync_secret": SYNC_SECRET,
        "telegram_id": str(book_id),
        "file_name": file_name,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/functions/v1/bot-cover-upload",
        data=body,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
        result = json.loads(raw) if raw else {}
    url = str(result.get("url") or "")
    if not url:
        raise RuntimeError(str(result.get("error") or "Rasm Supabase'ga yuklanmadi"))
    return url


def _sync_telegram_covers(local_books):
    """Telegram photo_id -> Supabase public image URL."""
    if not (BOT_TOKEN and SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET):
        return False
    changed = False
    for book in local_books:
        if not isinstance(book, dict):
            continue
        photo_id = str(book.get("photo_id") or "").strip()
        image_url = str(book.get("image_url") or "").strip()
        source_photo_id = str(book.get("web_photo_source_id") or "").strip()
        if photo_id:
            should_upload = not image_url or (source_photo_id and source_photo_id != photo_id)
            if should_upload:
                try:
                    book_id = int(book.get("id") or 0)
                    if book_id <= 0:
                        continue
                    new_url = _upload_telegram_cover(book_id, photo_id)
                    book["image_url"] = new_url
                    book["web_photo_source_id"] = photo_id
                    changed = True
                    print(f"Telegram → ilova rasm: {book.get('name', book_id)}")
                except Exception as e:
                    print(f"Telegram muqova sync xatosi ({book.get('name', '')}):", e)
        elif source_photo_id:
            if "/book-covers/telegram/" in image_url:
                book["image_url"] = ""
            book["web_photo_source_id"] = ""
            changed = True
    return changed


def _merge_cloud(local_books, rows):
    existing = {str(b.get("id")): dict(b) for b in local_books if isinstance(b, dict)}
    merged = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            tid = int(row.get("telegram_id") or 0)
        except Exception:
            continue
        if tid <= 0:
            continue
        current = existing.get(str(tid), {}).copy()
        base_price = max(0, int(row.get("price") or 0))
        discount = max(0, min(99, int(row.get("discount_percent") or 0)))
        sale_price = round(base_price * (100 - discount) / 100) if discount else base_price
        old_price = base_price if discount else 0
        if int(current.get("price", sale_price) or 0) != sale_price or int(current.get("old_price", old_price) or 0) != old_price:
            current.pop("global_discount_base_price", None)
            current.pop("global_discount_old_price", None)
        # Appdan rasm kelganda image_url doim saqlanadi. Bot sendPhoto URLni ham qabul qiladi.
        current.update({
            "id": tid,
            "cloud_id": str(row.get("id") or ""),
            "name": str(row.get("title") or "Nomsiz kitob"),
            "author": str(row.get("author") or "Ko‘rsatilmagan"),
            "category": str(row.get("category") or "Boshqalar"),
            "description": str(row.get("description") or "Ma’lumot kiritilmagan."),
            "price": sale_price,
            "old_price": old_price,
            "cost_price": max(0, int(row.get("cost_price") or 0)),
            "stock": max(0, int(row.get("stock") or 0)) if row.get("is_active", True) else 0,
            "discount_percent": discount,
            "image_url": str(row.get("image_url") or ""),
            "photo_id": str(row.get("telegram_photo_id") or current.get("photo_id") or ""),
            "cover": str(row.get("cover") or "Ko‘rsatilmagan"),
            "recommended": bool(row.get("recommended", False)),
            "is_active": bool(row.get("is_active", True)),
            "created_at": str(row.get("created_at") or current.get("created_at") or ""),
        })
        merged.append(current)
    merged.sort(key=lambda x: int(x.get("id", 0)))
    return merged


def _book_ids(items):
    result = set()
    for book in items:
        if not isinstance(book, dict):
            continue
        try:
            tid = int(book.get("id") or 0)
        except Exception:
            continue
        if tid > 0:
            result.add(tid)
    return result


def _order_status_to_bot(status):
    return {
        "new": "pending",
        "accepted": "paid",
        "paid": "paid",
        "shipping": "shipped",
        "done": "delivered",
        "cancelled": "cancelled",
    }.get(str(status), "pending")


def _cloud_order_to_bot(row, books_by_uuid, existing=None):
    existing = dict(existing or {})
    try:
        order_number = int(row.get("telegram_order_id") or row.get("order_number") or 0)
    except Exception:
        return None
    if order_number <= 0:
        return None
    items = []
    cart = {}
    for item in row.get("items") or []:
        if not isinstance(item, dict):
            continue
        book_uuid = str(item.get("book_id") or "")
        book = books_by_uuid.get(book_uuid, {})
        try:
            tid = int(book.get("telegram_id") or 0)
        except Exception:
            tid = 0
        qty = max(1, int(item.get("quantity") or item.get("qty") or 1))
        unit_price = max(0, int(item.get("unit_price") or item.get("price") or 0))
        name = str(item.get("title") or book.get("title") or "Kitob")
        item_data = {
            "book_id": str(tid) if tid > 0 else book_uuid,
            "name": name,
            "qty": qty,
            "unit_price": unit_price,
            "unit_cost": max(0, int(book.get("cost_price") or 0)),
        }
        items.append(item_data)
        if tid > 0:
            cart[str(tid)] = qty
    existing.update({
        "order_id": str(order_number),
        "cloud_order_id": str(row.get("id") or ""),
        "source": str(row.get("source") or "app"),
        "chat_id": int(row.get("telegram_chat_id") or existing.get("chat_id") or 0),
        "username": str(row.get("telegram_username") or existing.get("username") or ""),
        "name": str(row.get("customer_name") or ""),
        "phone": str(row.get("phone") or ""),
        "address": str(row.get("address") or ""),
        "cart": cart,
        "items": items,
        "total": int(row.get("subtotal") or 0),
        "delivery_fee": int(row.get("delivery_fee") or 0),
        "grand_total": int(row.get("total") or 0),
        "discount": 0,
        "status": _order_status_to_bot(row.get("status")),
        "payment_declared": bool(row.get("payment_submitted_at") or row.get("telegram_receipt_file_id")),
        "receipt_file_id": str(row.get("telegram_receipt_file_id") or existing.get("receipt_file_id") or ""),
        "payment_proof_path": str(row.get("payment_proof_path") or ""),
        "created_at": str(row.get("created_at") or existing.get("created_at") or ""),
    })
    return existing


def _import_unsynced_orders(local_orders):
    changed = False
    for key, order in list(local_orders.items()):
        if not isinstance(order, dict):
            continue
        if str(order.get("cloud_order_id") or "").strip():
            continue
        if str(order.get("source") or "telegram") == "app":
            continue
        try:
            result = _rpc(
                "bot_order_create",
                {"p_secret": SYNC_SECRET, "p_order": order, "p_preserve_stock": True},
            )
            if isinstance(result, dict) and result.get("id"):
                order["cloud_order_id"] = str(result.get("id"))
                order["source"] = "telegram"
                local_orders[str(key)] = order
                changed = True
        except Exception as e:
            print(f"Eski bot buyurtmasini cloudga ko‘chirish xatosi ({key}):", e)
    return changed


def _telegram_send(chat_id, text, reply_markup=None):
    if not (BOT_TOKEN and chat_id):
        return
    data = {"chat_id": str(chat_id), "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=urllib.parse.urlencode(data).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def _notify_admin_app_order(order):
    if not ADMIN_ID:
        return
    lines = []
    for item in order.get("items") or []:
        lines.append(f"• {item.get('name','Kitob')} × {int(item.get('qty',1))} = ₩{int(item.get('unit_price',0))*int(item.get('qty',1)):,}")
    text = (
        f"📱 PROGRAMMADAN YANGI BUYURTMA №{order.get('order_id')}\n\n"
        f"👤 {order.get('name','—')}\n"
        f"📱 {order.get('phone','—')}\n"
        f"📍 {order.get('address','—')}\n\n"
        "📚 KITOBLAR:\n" + ("\n".join(lines) if lines else "• Ma’lumot yo‘q") +
        f"\n\n🚚 Yetkazib berish: ₩{int(order.get('delivery_fee',0)):,}"
        f"\n💵 JAMI: ₩{int(order.get('grand_total',0)):,}"
    )
    kb = {"inline_keyboard": [[{"text": "📦 Buyurtmani ochish", "callback_data": f"adminorder_{order.get('order_id')}"}]]}
    _telegram_send(ADMIN_ID, text, kb)


def sync_loop():
    last_hash = None
    last_ids = set()
    initialized = False
    seen_order_ids = set()

    while True:
        try:
            # BOOKS: bot va app uchun bitta Supabase katalog.
            local = _read_books()
            current_hash = _hash(local)
            if local and _sync_telegram_covers(local):
                _write_books(local)
                current_hash = _hash(local)

            if not initialized:
                unsynced = [b for b in local if isinstance(b, dict) and not str(b.get("cloud_id") or "").strip()]
                if unsynced:
                    _push(unsynced)
                rows = _pull_rows()
                cloud_local = _merge_cloud(local, rows)
                if _hash(cloud_local) != current_hash:
                    _write_books(cloud_local)
                    local = cloud_local
                    current_hash = _hash(local)
                last_hash = current_hash
                last_ids = _book_ids(local)
            else:
                local_ids = _book_ids(local)
                deleted_ids = sorted(last_ids - local_ids)
                for tid in deleted_ids:
                    try:
                        _rpc("bot_sync_delete", {"p_secret": SYNC_SECRET, "p_telegram_id": tid, "p_cloud_id": None})
                        print(f"Bot → ilova kitob o‘chirildi: telegram_id={tid}")
                    except Exception as e:
                        print(f"Bot delete sync xatosi ({tid}):", e)
                if local and current_hash != last_hash:
                    _push(local)
                rows = _pull_rows()
                cloud_local = _merge_cloud(local, rows)
                if _hash(cloud_local) != current_hash:
                    _write_books(cloud_local)
                    local = cloud_local
                    current_hash = _hash(local)
                last_hash = current_hash
                last_ids = _book_ids(local)

            # ORDERS: Supabase authoritative; Telegramdagi eski buyurtmalar bir marta import qilinadi.
            local_orders = _read_orders()
            if _import_unsynced_orders(local_orders):
                _write_orders(local_orders)
            cloud_orders = _pull_orders()
            books_rows = rows if isinstance(rows, list) else _pull_rows()
            books_by_uuid = {str(b.get("id")): b for b in books_rows if isinstance(b, dict)}

            # Birinchi siklda mavjud buyurtmalar notification bermaydi.
            current_cloud_ids = {str(r.get("id")) for r in cloud_orders if isinstance(r, dict) and r.get("id")}
            if not initialized:
                seen_order_ids = set(current_cloud_ids)

            latest_local = _read_orders()
            merged_orders = dict(latest_local)
            new_app_orders = []
            for row in cloud_orders:
                if not isinstance(row, dict):
                    continue
                raw_number = row.get("telegram_order_id") or row.get("order_number")
                try:
                    key = str(int(raw_number))
                except Exception:
                    continue
                merged = _cloud_order_to_bot(row, books_by_uuid, latest_local.get(key))
                if merged is None:
                    continue
                merged_orders[key] = merged
                cloud_id = str(row.get("id") or "")
                if initialized and cloud_id and cloud_id not in seen_order_ids and str(row.get("source") or "app") == "app":
                    new_app_orders.append(merged)

            if _hash(merged_orders) != _hash(latest_local):
                _write_orders(merged_orders)

            for order in new_app_orders:
                try:
                    _notify_admin_app_order(order)
                    print(f"Ilova → bot yangi buyurtma: {order.get('order_id')}")
                except Exception as e:
                    print("Ilova buyurtmasi admin notification xatosi:", e)
            seen_order_ids.update(current_cloud_ids)
            initialized = True

        except urllib.error.HTTPError as e:
            try:
                details = e.read().decode("utf-8")
            except Exception:
                details = str(e)
            print("Supabase sync HTTP xatosi:", e.code, details)
        except Exception as e:
            print("Supabase sync xatosi:", e)

        time.sleep(SYNC_INTERVAL)


if SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:
    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()
else:
    print("Supabase sync environment variablelari topilmadi; bot odatdagi rejimda ishlaydi.")

runpy.run_path("bot.py", run_name="__main__")