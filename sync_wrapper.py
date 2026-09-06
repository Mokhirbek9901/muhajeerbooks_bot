import hashlib
import json
import os
import runpy
import threading
import time
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SYNC_SECRET = os.environ.get("SUPABASE_BOT_SYNC_SECRET", "")
DATA_DIR = "/data" if os.path.isdir("/data") else "."
BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
SYNC_INTERVAL = 5


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


def _read_books():
    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_books(data):
    tmp = BOOKS_FILE + ".cloud.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, BOOKS_FILE)


def _hash(data):
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _push(local_books):
    if not local_books:
        return 0
    return _rpc("bot_sync_push", {"p_secret": SYNC_SECRET, "p_books": local_books})


def _pull_rows():
    result = _rpc("bot_sync_pull", {"p_secret": SYNC_SECRET})
    return result if isinstance(result, list) else []


def _merge_cloud(local_books, rows):
    existing = {str(b.get("id")): dict(b) for b in local_books if isinstance(b, dict)}
    used_ids = set()
    for b in local_books:
        try:
            used_ids.add(int(b.get("id")))
        except Exception:
            pass
    next_id = max(used_ids, default=0) + 1
    merged = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        tid = row.get("telegram_id")
        if tid is None:
            while next_id in used_ids:
                next_id += 1
            tid = next_id
            used_ids.add(tid)
            next_id += 1
        try:
            tid = int(tid)
        except Exception:
            continue

        current = existing.get(str(tid), {}).copy()
        base_price = max(0, int(row.get("price") or 0))
        discount = max(0, min(99, int(row.get("discount_percent") or 0)))
        sale_price = round(base_price * (100 - discount) / 100) if discount else base_price
        old_price = base_price if discount else 0

        if int(current.get("price", sale_price) or 0) != sale_price or int(current.get("old_price", old_price) or 0) != old_price:
            current.pop("global_discount_base_price", None)
            current.pop("global_discount_old_price", None)

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


def sync_loop():
    last_hash = None
    first = True
    while True:
        try:
            local = _read_books()
            current_hash = _hash(local)

            if local and (first or current_hash != last_hash):
                _push(local)

            rows = _pull_rows()
            cloud_local = _merge_cloud(local, rows)
            if _hash(cloud_local) != current_hash:
                _write_books(cloud_local)
                local = cloud_local
                current_hash = _hash(local)

            last_hash = current_hash
            first = False
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
    threading.Thread(target=sync_loop, daemon=True, name="supabase-books-sync").start()
else:
    print("Supabase sync environment variablelari topilmadi; bot odatdagi rejimda ishlaydi.")

# Railway production starts from this wrapper so bot va ilova bitta katalogdan foydalanadi.
runpy.run_path("bot.py", run_name="__main__")
