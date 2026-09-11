import json
import os
import threading
import time
import urllib.parse
import urllib.request

from supabase_http import post_json

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
DATA_DIR = "/data" if os.path.isdir("/data") else "."
STATE_FILE = os.path.join(DATA_DIR, "app_cover_telegram_sync.json")
SYNC_INTERVAL = 12


def _rpc(name, payload):
    return post_json(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}",
        payload,
        {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        },
        timeout=40,
    )


def _telegram(method, payload):
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=70) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(str(result.get("description") or f"Telegram {method} xatosi"))
    return result.get("result")


def _cache_photo(image_url):
    result = _telegram(
        "sendPhoto",
        {
            "chat_id": ADMIN_ID,
            "photo": image_url,
            "disable_notification": "true",
        },
    ) or {}
    photos = result.get("photo") or []
    if not photos:
        raise RuntimeError("Telegram rasm file_id qaytarmadi")
    file_id = str((photos[-1] or {}).get("file_id") or "")
    if not file_id:
        raise RuntimeError("Telegram rasm file_id bo‘sh")

    message_id = result.get("message_id")
    if message_id:
        try:
            _telegram("deleteMessage", {"chat_id": ADMIN_ID, "message_id": message_id})
        except Exception:
            pass
    return file_id


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(data):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _rows_to_bot_books(rows, photo_overrides):
    books = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tid = _to_int(row.get("telegram_id"), 0)
        if tid <= 0:
            continue

        base_price = max(0, _to_int(row.get("price"), 0))
        discount = max(0, min(99, _to_int(row.get("discount_percent"), 0)))
        sale_price = round(base_price * (100 - discount) / 100) if discount else base_price
        old_price = base_price if discount else 0
        cloud_id = str(row.get("id") or "")
        photo_id = photo_overrides.get(cloud_id, str(row.get("telegram_photo_id") or ""))

        books.append(
            {
                "id": tid,
                "cloud_id": cloud_id,
                "name": str(row.get("title") or "Nomsiz kitob"),
                "author": str(row.get("author") or "Ko‘rsatilmagan"),
                "category": str(row.get("category") or "Boshqalar"),
                "description": str(row.get("description") or "Ma’lumot kiritilmagan."),
                "price": sale_price,
                "old_price": old_price,
                "cost_price": max(0, _to_int(row.get("cost_price"), 0)),
                "stock": max(0, _to_int(row.get("stock"), 0)),
                "discount_percent": discount,
                "image_url": str(row.get("image_url") or ""),
                "photo_id": photo_id,
                "cover": str(row.get("cover") or "Ko‘rsatilmagan"),
                "recommended": bool(row.get("recommended", False)),
                "is_active": bool(row.get("is_active", True)),
            }
        )
    return books


def sync_once(state):
    rows = _rpc("bot_sync_pull", {"p_secret": SYNC_SECRET})
    if not isinstance(rows, list):
        return state

    overrides = {}
    next_state = dict(state)
    touched = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        cloud_id = str(row.get("id") or "")
        if not cloud_id:
            continue

        image_url = str(row.get("image_url") or "").strip()
        current_photo = str(row.get("telegram_photo_id") or "").strip()
        previous = state.get(cloud_id) if isinstance(state.get(cloud_id), dict) else None

        # Telegram botdan kelgan muqova allaqachon Telegram file_id bilan ishlaydi.
        if "/book-covers/telegram/" in image_url:
            if previous is not None:
                next_state.pop(cloud_id, None)
                touched = True
            continue

        # Ilovada rasm olib tashlansa, faqat o‘sha ilovadan sync qilingan eski photo_id ni tozalaymiz.
        if not image_url:
            if previous is not None:
                old_photo = str(previous.get("photo_id") or "")
                if old_photo and current_photo == old_photo:
                    overrides[cloud_id] = ""
                next_state.pop(cloud_id, None)
                touched = True
            continue

        if (
            previous is not None
            and str(previous.get("source_url") or "") == image_url
            and str(previous.get("photo_id") or "") == current_photo
            and current_photo
        ):
            continue

        try:
            new_photo = _cache_photo(image_url)
        except Exception as e:
            print(f"Ilova → Telegram rasm sync xatosi ({row.get('title', '')}):", e)
            continue

        overrides[cloud_id] = new_photo
        next_state[cloud_id] = {"source_url": image_url, "photo_id": new_photo}
        touched = True
        print(f"Ilova → Telegram muqova tayyor: {row.get('title', cloud_id)}")

    if overrides:
        books = _rows_to_bot_books(rows, overrides)
        if books:
            _rpc("bot_sync_push_safe", {"p_secret": SYNC_SECRET, "p_books": books})
            print(f"Telegram rasmlari katalogga yozildi: {len(overrides)} ta")

    if touched:
        _save_state(next_state)
    return next_state


def _loop():
    state = _load_state()
    while True:
        try:
            state = sync_once(state)
        except Exception as e:
            print("Ilova → Telegram cover sync xatosi:", e)
        time.sleep(SYNC_INTERVAL)


if all((SUPABASE_URL, SUPABASE_ANON_KEY, SYNC_SECRET, BOT_TOKEN, ADMIN_ID)):
    threading.Thread(target=_loop, daemon=True, name="app-cover-to-telegram-sync").start()
else:
    print("Ilova → Telegram rasm sync uchun environment variablelar yetishmaydi.")

# Railway deploy trigger: final restock deep-link fix 2026-09-10.
