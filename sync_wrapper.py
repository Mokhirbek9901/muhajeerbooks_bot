import base64
import hashlib
import json
import os
import runpy
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()

DATA_DIR = "/data" if os.path.isdir("/data") else "."
BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
SYNC_INTERVAL = 2
CATALOG_RESET_MARKER = os.path.join(DATA_DIR, "catalog_full_reset_20260908_v1.done")


def _rpc(name, payload):
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
    with urllib.request.urlopen(req, timeout=35) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    tmp = path + ".sync.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _hash(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_books():
    data = _read_json(BOOKS_FILE, [])
    return data if isinstance(data, list) else []


def _read_orders():
    data = _read_json(ORDERS_FILE, {})
    return data if isinstance(data, dict) else {}


def _catalog_reset_once():
    """User so'ragan bir martalik to'liq katalog reset: cloud + Railway volume."""
    if os.path.exists(CATALOG_RESET_MARKER):
        return
    result = {"ok": True, "database_reset": "done_by_admin_sql"}
    _write_json(BOOKS_FILE, [])
    tmp = CATALOG_RESET_MARKER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(result or {"ok": True}, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CATALOG_RESET_MARKER)
    print("CATALOG_FULL_RESET_20260908:", result)


def _push_books(items):
    if not items:
        return
    _rpc("bot_sync_push_safe", {"p_secret": SYNC_SECRET, "p_books": items})


def _pull_books():
    rows = _rpc("bot_sync_pull", {"p_secret": SYNC_SECRET})
    return rows if isinstance(rows, list) else []


def _pull_tombstones():
    rows = _rpc("bot_sync_tombstones_pull", {"p_secret": SYNC_SECRET})
    return rows if isinstance(rows, list) else []


def _parse_iso(value):
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _remove_tombstoned_local(items, tombstones):
    tomb_by_id = {}
    for row in tombstones or []:
        try:
            tid = int(row.get('telegram_id') or 0)
        except Exception:
            continue
        if tid > 0:
            tomb_by_id[tid] = row

    cleaned = []
    removed = []
    for book in items or []:
        if not isinstance(book, dict):
            continue
        try:
            tid = int(book.get('id') or 0)
        except Exception:
            tid = 0
        tomb = tomb_by_id.get(tid)
        if not tomb:
            cleaned.append(book)
            continue

        book_cloud = str(book.get('cloud_id') or '').strip()
        tomb_cloud = str(tomb.get('cloud_id') or '').strip()
        created = _parse_iso(book.get('created_at'))
        deleted = _parse_iso(tomb.get('deleted_at'))

        # Aynan o'chirilgan cloud nusxasi yoki tombstonedan eski lokal nusxa — olib tashlanadi.
        stale_same_cloud = bool(book_cloud and tomb_cloud and book_cloud == tomb_cloud)
        stale_by_time = not (created and deleted and created > deleted)
        if stale_same_cloud or stale_by_time:
            removed.append(book)
            continue
        cleaned.append(book)
    return cleaned, removed


def _book_ids(items):
    out = set()
    for b in items:
        try:
            value = int(b.get("id") or 0)
        except Exception:
            continue
        if value > 0:
            out.add(value)
    return out


def _norm_title(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _telegram_photo_bytes(file_id):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        data=urllib.parse.urlencode({"file_id": file_id}).encode(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    path = str((result.get("result") or {}).get("file_path") or "")
    if not path:
        raise RuntimeError("Telegram rasm fayli topilmadi")
    with urllib.request.urlopen(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}", timeout=60
    ) as resp:
        content = resp.read()
    if not content or len(content) > 7_000_000:
        raise RuntimeError("Telegram rasmi hajmi noto‘g‘ri")
    lower = path.lower()
    if lower.endswith(".png"):
        return content, "telegram-cover.png", "image/png"
    if lower.endswith(".webp"):
        return content, "telegram-cover.webp", "image/webp"
    return content, "telegram-cover.jpg", "image/jpeg"


def _upload_telegram_cover(book_id, photo_id):
    content, file_name, content_type = _telegram_photo_bytes(photo_id)
    payload = {
        "sync_secret": SYNC_SECRET,
        "telegram_id": str(book_id),
        "file_name": file_name,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }
    req = urllib.request.Request(
        f"{SUPABASE_URL}/functions/v1/bot-cover-upload",
        data=json.dumps(payload).encode(),
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    url = str(result.get("url") or "")
    if not url:
        raise RuntimeError(str(result.get("error") or "Rasm yuklanmadi"))
    return url


def _telegram_file_id_from_url(url):
    if not (BOT_TOKEN and ADMIN_ID and url):
        return ""
    data = {
        "chat_id": ADMIN_ID,
        "photo": url,
        "disable_notification": "true",
        "caption": "Muhajeer Books rasm sinxroni",
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data=urllib.parse.urlencode(data).encode(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg = result.get("result") or {}
    photos = msg.get("photo") or []
    file_id = str(photos[-1].get("file_id") or "") if photos else ""
    message_id = msg.get("message_id")
    if message_id:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
                data=urllib.parse.urlencode(
                    {"chat_id": ADMIN_ID, "message_id": message_id}
                ).encode(),
                method="POST",
            )
            urllib.request.urlopen(req, timeout=20).read()
        except Exception:
            pass
    return file_id


def _prepare_bot_image_changes(local, previous):
    prev_by_id = {
        str(b.get("id")): b for b in (previous or []) if isinstance(b, dict)
    }
    changed = False
    for book in local:
        if not isinstance(book, dict):
            continue
        prev = prev_by_id.get(str(book.get("id")))
        if not prev:
            continue
        now_photo = str(book.get("photo_id") or "").strip()
        old_photo = str(prev.get("photo_id") or "").strip()
        if now_photo == old_photo:
            continue
        try:
            if now_photo:
                book["image_url"] = _upload_telegram_cover(
                    int(book.get("id") or 0), now_photo
                )
                book["web_photo_source_id"] = now_photo
                print(f"Telegram → ilova rasm yangilandi: {book.get('name','')}")
            else:
                book["image_url"] = ""
                book["web_photo_source_id"] = ""
                print(f"Telegram → ilova rasm o‘chirildi: {book.get('name','')}")
            changed = True
        except Exception as e:
            print("Telegram rasm sync xatosi:", e)
    return changed


def _row_to_book(row, current, tid):
    base = max(0, int(row.get("price") or 0))
    discount = max(0, min(99, int(row.get("discount_percent") or 0)))
    sale = round(base * (100 - discount) / 100) if discount else base
    old = base if discount else 0
    current = dict(current or {})
    current.update(
        {
            "id": tid,
            "cloud_id": str(row.get("id") or ""),
            "name": str(row.get("title") or "Nomsiz kitob"),
            "author": str(row.get("author") or "Ko‘rsatilmagan"),
            "category": str(row.get("category") or "Boshqalar"),
            "description": str(row.get("description") or "Ma’lumot kiritilmagan."),
            "price": sale,
            "old_price": old,
            "cost_price": max(0, int(row.get("cost_price") or 0)),
            "stock": max(0, int(row.get("stock") or 0))
            if row.get("is_active", True)
            else 0,
            "discount_percent": discount,
            "image_url": str(row.get("image_url") or ""),
            "photo_id": str(row.get("telegram_photo_id") or ""),
            "cover": str(row.get("cover") or "Ko‘rsatilmagan"),
            "recommended": bool(row.get("recommended", False)),
            "is_active": bool(row.get("is_active", True)),
            "created_at": str(row.get("created_at") or current.get("created_at") or ""),
        }
    )
    return current


def _merge_books(local, rows):
    existing_by_id = {
        str(b.get("id")): dict(b) for b in local if isinstance(b, dict)
    }
    local_by_title = {}
    for b in local:
        if isinstance(b, dict):
            local_by_title.setdefault(_norm_title(b.get("name")), []).append(b)

    used = set()
    for row in rows:
        try:
            tid = int(row.get("telegram_id") or 0)
        except Exception:
            tid = 0
        if tid > 0:
            used.add(tid)
    for b in local:
        try:
            used.add(int(b.get("id") or 0))
        except Exception:
            pass
    next_id = max(used, default=0) + 1

    merged = []
    claimed = set()
    unmapped = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            tid = int(row.get("telegram_id") or 0)
        except Exception:
            tid = 0

        if tid <= 0:
            key = _norm_title(row.get("title"))
            candidates = [
                b
                for b in local_by_title.get(key, [])
                if int(b.get("id") or 0) not in claimed
            ]
            if len(candidates) == 1:
                tid = int(candidates[0].get("id") or 0)
            else:
                while next_id in claimed:
                    next_id += 1
                tid = next_id
                next_id += 1
            unmapped.append(str(row.get("id") or ""))

        claimed.add(tid)
        current = existing_by_id.get(str(tid), {})
        merged.append(_row_to_book(row, current, tid))

    dedup = {}
    for b in merged:
        dedup[str(b.get("id"))] = b
    out = sorted(dedup.values(), key=lambda x: int(x.get("id") or 0))
    return out, set(unmapped)


def _sync_app_images_to_telegram(rows, previous_rows):
    previous = {
        str(row.get("id")): row
        for row in (previous_rows or [])
        if isinstance(row, dict) and row.get("id")
    }
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        cloud_id = str(row.get("id") or "")
        if not cloud_id:
            continue
        image_url = str(row.get("image_url") or "").strip()
        photo_id = str(row.get("telegram_photo_id") or "").strip()
        old = previous.get(cloud_id, {})
        old_image = str(old.get("image_url") or "").strip()
        old_photo = str(old.get("telegram_photo_id") or "").strip()
        app_image_changed = bool(old) and image_url != old_image and photo_id == old_photo
        needs_photo = bool(image_url) and (not photo_id or app_image_changed)
        app_image_removed = bool(old) and not image_url and bool(old_image) and photo_id == old_photo
        try:
            if needs_photo:
                new_id = _telegram_file_id_from_url(image_url)
                if new_id:
                    _rpc("bot_sync_set_photo", {
                        "p_secret": SYNC_SECRET,
                        "p_cloud_id": cloud_id,
                        "p_photo_id": new_id,
                    })
                    print(f"Ilova → Telegram rasm yangilandi: {row.get('title','')}")
                    changed = True
            elif app_image_removed and photo_id:
                _rpc("bot_sync_set_photo", {
                    "p_secret": SYNC_SECRET,
                    "p_cloud_id": cloud_id,
                    "p_photo_id": "",
                })
                print(f"Ilova → Telegram rasm o‘chirildi: {row.get('title','')}")
                changed = True
        except Exception as e:
            print("Ilova rasm sync xatosi:", e)
    return changed


def _push_unmapped_books(merged, unmapped_cloud_ids):
    items = [
        b
        for b in merged
        if str(b.get("cloud_id") or "") in unmapped_cloud_ids
    ]
    if items:
        _push_books(items)


def _order_status_to_bot(status):
    return {
        "new": "pending",
        "accepted": "accepted",
        "paid": "paid",
        "shipping": "shipped",
        "done": "delivered",
        "cancelled": "cancelled",
    }.get(str(status), "pending")


def _cloud_order_to_bot(row, books_by_uuid, existing=None):
    existing = dict(existing or {})
    try:
        number = int(row.get("telegram_order_id") or 0)
    except Exception:
        return None
    if number <= 0:
        return None

    items = []
    cart = {}
    for item in row.get("items") or []:
        if not isinstance(item, dict):
            continue
        book_uuid = str(item.get("book_id") or "")
        book = books_by_uuid.get(book_uuid, {})
        try:
            tid = int(item.get("telegram_book_id") or book.get("telegram_id") or 0)
        except Exception:
            tid = 0
        qty = max(1, int(item.get("quantity") or item.get("qty") or 1))
        unit = max(0, int(item.get("unit_price") or item.get("price") or 0))
        items.append(
            {
                "book_id": str(tid) if tid > 0 else book_uuid,
                "name": str(item.get("title") or book.get("title") or "Kitob"),
                "qty": qty,
                "unit_price": unit,
                "unit_cost": max(0, int(book.get("cost_price") or 0)),
            }
        )
        if tid > 0:
            cart[str(tid)] = qty

    # Ilovadan kelgan buyurtma Telegram mijoziga avtomatik bog‘lanmaydi.
    # Telegram akkauntining SIM raqamini bot ko‘rmaydi; telefon bo‘yicha taxminiy
    # bog‘lash boshqa akkauntga xabar yuborishiga sabab bo‘lishi mumkin.
    source = str(row.get("source") or "app")
    linked_chat = 0 if source == "app" else int(
        row.get("telegram_chat_id") or existing.get("chat_id") or 0
    )

    existing.update(
        {
            "order_id": str(number),
            "cloud_order_id": str(row.get("id") or ""),
            "source": str(row.get("source") or "app"),
            "chat_id": linked_chat,
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
            "payment_declared": bool(
                row.get("payment_submitted_at")
                or row.get("telegram_receipt_file_id")
            ),
            "receipt_file_id": str(
                row.get("telegram_receipt_file_id")
                or existing.get("receipt_file_id")
                or ""
            ),
            "payment_proof_path": str(row.get("payment_proof_path") or ""),
            "created_at": str(row.get("created_at") or existing.get("created_at") or ""),
        }
    )
    return existing


def _push_order(order):
    return _rpc(
        "bot_order_sync_upsert",
        {"p_secret": SYNC_SECRET, "p_order": order},
    )


def _pull_orders():
    rows = _rpc("bot_order_sync_pull", {"p_secret": SYNC_SECRET})
    return rows if isinstance(rows, list) else []


def _telegram_send(chat_id, text, reply_markup=None):
    if not (BOT_TOKEN and chat_id):
        return
    data = {"chat_id": str(chat_id), "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=urllib.parse.urlencode(data).encode(),
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def _notify_admin_app_order(order):
    if not ADMIN_ID:
        return
    lines = [
        f"• {item.get('name','Kitob')} × {int(item.get('qty',1))} = "
        f"₩{int(item.get('unit_price',0))*int(item.get('qty',1)):,}"
        for item in order.get("items") or []
    ]
    proof_note = (
        "\n📸 To‘lov cheki: programmada yuklangan"
        if order.get("payment_proof_path")
        else ""
    )
    text = (
        f"📱 PROGRAMMADAN YANGI BUYURTMA №{order.get('order_id')}\n\n"
        f"👤 {order.get('name','—')}\n"
        f"📱 {order.get('phone','—')}\n"
        f"📍 {order.get('address','—')}\n\n"
        "📚 KITOBLAR:\n"
        + ("\n".join(lines) if lines else "• Ma’lumot yo‘q")
        + f"\n\n🚚 Yetkazib berish: ₩{int(order.get('delivery_fee',0)):,}"
        + f"\n💵 JAMI: ₩{int(order.get('grand_total',0)):,}"
        + proof_note
    )
    text += "\n\n🔒 Bu buyurtma faqat ilova admin panelidan boshqariladi."
    _telegram_send(ADMIN_ID, text)


def _book_fingerprint(book):
    if not isinstance(book, dict):
        return ""
    payload = {
        k: book.get(k)
        for k in (
            "cloud_id", "name", "author", "category", "description",
            "price", "old_price", "cost_price", "stock", "discount_percent",
            "image_url", "photo_id", "cover", "recommended", "is_active",
        )
    }
    return _hash(payload)


def sync_loop():
    initialized = False
    seen_order_ids = set()
    last_local_books = []
    last_book_ids = set()
    last_book_fingerprints = {}
    last_cloud_rows = []

    while True:
        try:
            local = _read_books()
            tombstones = _pull_tombstones()
            local, removed_stale = _remove_tombstoned_local(local, tombstones)
            if removed_stale:
                _write_json(BOOKS_FILE, local)
                print("Tombstone bo‘yicha lokal katalog tozalandi:", ", ".join(str(b.get('name') or b.get('id')) for b in removed_stale))
            if initialized and _prepare_bot_image_changes(local, last_local_books):
                _write_json(BOOKS_FILE, local)

            if not initialized:
                unsynced = [
                    b for b in local
                    if isinstance(b, dict) and not str(b.get("cloud_id") or "").strip()
                ]
                if unsynced:
                    _push_books(unsynced)
            else:
                current_ids = _book_ids(local)
                # O‘chirishni local ro‘yxatdagi farqdan taxmin qilmaymiz.
                # Botdagi haqiqiy delete cloud_bridge.delete_book(book) orqali atomik bajariladi.

                changed = []
                for book in local:
                    if not isinstance(book, dict):
                        continue
                    try:
                        tid = int(book.get("id") or 0)
                    except Exception:
                        continue
                    if tid <= 0:
                        continue
                    fp = _book_fingerprint(book)
                    if last_book_fingerprints.get(tid) != fp:
                        changed.append(book)
                if changed:
                    _push_books(changed)

            rows = _pull_books()
            if _sync_app_images_to_telegram(rows, last_cloud_rows):
                rows = _pull_books()

            merged, unmapped = _merge_books(local, rows)
            if unmapped:
                _push_unmapped_books(merged, unmapped)
                rows = _pull_books()
                merged, _ = _merge_books(merged, rows)

            latest_local = _read_books()
            if _hash(latest_local) == _hash(local):
                if _hash(merged) != _hash(latest_local):
                    _write_json(BOOKS_FILE, merged)
                local = merged
            else:
                local = latest_local

            last_local_books = [dict(b) for b in local if isinstance(b, dict)]
            last_book_ids = _book_ids(local)
            last_book_fingerprints = {
                int(b.get("id")): _book_fingerprint(b)
                for b in local
                if isinstance(b, dict) and str(b.get("id") or "").isdigit()
            }
            last_cloud_rows = [dict(r) for r in rows if isinstance(r, dict)]

            local_orders = _read_orders()
            orders_changed = False
            for key, order in list(local_orders.items()):
                if not isinstance(order, dict):
                    continue
                if str(order.get("cloud_order_id") or "").strip():
                    continue
                if str(order.get("source") or "telegram") == "app":
                    continue
                try:
                    result = _rpc("bot_order_create", {
                        "p_secret": SYNC_SECRET,
                        "p_order": order,
                        "p_preserve_stock": True,
                    })
                    if isinstance(result, dict) and result.get("id"):
                        order["cloud_order_id"] = str(result.get("id"))
                        order["source"] = "telegram"
                        local_orders[str(key)] = order
                        orders_changed = True
                except Exception as e:
                    print(f"Telegram buyurtmasini cloudga retry xatosi ({key}):", e)
            if orders_changed:
                _write_json(ORDERS_FILE, local_orders)

            cloud_orders = _pull_orders()
            books_by_uuid = {
                str(r.get("id")): r for r in rows if isinstance(r, dict) and r.get("id")
            }
            current_cloud_ids = {
                str(r.get("id"))
                for r in cloud_orders
                if isinstance(r, dict) and r.get("id")
            }
            if not initialized:
                seen_order_ids = set(current_cloud_ids)

            latest_orders = _read_orders()
            merged_orders = dict(latest_orders)
            new_app_orders = []
            for row in cloud_orders:
                if not isinstance(row, dict):
                    continue
                raw_number = row.get("telegram_order_id") or row.get("order_number")
                try:
                    key = str(int(raw_number))
                except Exception:
                    continue
                merged_order = _cloud_order_to_bot(row, books_by_uuid, latest_orders.get(key))
                if merged_order is None:
                    continue
                merged_orders[key] = merged_order
                cloud_id = str(row.get("id") or "")
                if (
                    initialized and cloud_id and cloud_id not in seen_order_ids
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(merged_order)

            if _hash(merged_orders) != _hash(latest_orders):
                _write_json(ORDERS_FILE, merged_orders)

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
    # Sync boshlanishidan OLDIN ikkala katalogni atomik reset qilamiz; aks holda
    # eski Railway books.json cloudga yana qayta push bo'lib ketishi mumkin.
    _catalog_reset_once()
    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()
else:
    print("Supabase sync environment variablelari topilmadi; bot odatdagi rejimda ishlaydi.")

runpy.run_path("bot.py", run_name="__main__")
