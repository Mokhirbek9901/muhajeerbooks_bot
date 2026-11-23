Warning: truncated output (original token count: 64781)
Total output lines: 6876

import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import io
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cloud_bridge
import mini_app

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher


def _local_datetime(raw):
    """ISO vaqtni timezone aralashmasidan xoli, taqqoslanadigan local datetimega aylantiradi."""
    value = str(raw or '').strip()
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()

# Bitta rasmiy havola: iOS -> App Store, Android -> Play Market.
APP_DOWNLOAD_URL = os.environ.get(
    "APP_DOWNLOAD_URL", "https://muhajeerbooks-link-production.up.railway.app/"
).strip()
ORDER_APP_BUTTON = "📚 Kitob buyurtma qilish"

API = f"https://api.telegram.org/bot{TOKEN}"

# Railway Volume ishlatilsa /data doimiy saqlanadi
DATA_DIR = "/data" if os.path.isdir("/data") else "."

BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")
RATINGS_FILE = os.path.join(DATA_DIR, "ratings.json")
RESTOCK_FILE = os.path.join(DATA_DIR, "restock.json")
EXPENSES_FILE = os.path.join(DATA_DIR, "expenses.json")
SHIPPING_QUEUE_FILE = os.path.join(DATA_DIR, "shipping_queue.json")
BOOK_IMPORT_MARKER = os.path.join(DATA_DIR, "books_import_20260906_v1.done")
LOW_STOCK_LIMIT = 2
STATS_RESET_ORDER_ID = 1788893918395  # 2026-09-08 final production reset

# =========================
# TO'LOV / YETKAZIB BERISH
# =========================

DELIVERY_FEE = 4000
CARD_NUMBER = "100068127720"
BANK_NAME = "Toss Bank"
CARD_OWNER = "Ismoilov M"

# =========================
# BOSHLANG'ICH KITOBLAR
# =========================

DEFAULT_BOOKS = [
    {"id": 1, "name": "Istiqlol jallodlari", "price": 0, "stock": 0},
    {"id": 2, "name": "Yovuz daho 2-qism", "price": 0, "stock": 0},
    {"id": 3, "name": "Sunniy intelekt asoslari", "price": 0, "stock": 0},
    {"id": 4, "name": "Yuqumlilik", "price": 0, "stock": 0},
    {"id": 5, "name": "Binafsha 1-qism", "price": 0, "stock": 0},
    {"id": 6, "name": "Jinni binafsha 2-qism", "price": 0, "stock": 0},
]

books = []
carts = {}
states = {}
orders = {}
users = {}
favorites = {}
ratings = {}
restock_subscribers = {}
expenses = {}
ORDER_HISTORY_RESET_MARKER = os.path.join(DATA_DIR, "order_history_reset_20260908_v2.done")
if not os.path.exists(ORDER_HISTORY_RESET_MARKER):
    tmp_orders = ORDERS_FILE + ".history_reset.tmp"
    with open(tmp_orders, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_orders, ORDERS_FILE)
    tmp_ratings = RATINGS_FILE + ".history_reset.tmp"
    with open(tmp_ratings, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_ratings, RATINGS_FILE)
    marker_tmp = ORDER_HISTORY_RESET_MARKER + ".tmp"
    with open(marker_tmp, "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat() + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(marker_tmp, ORDER_HISTORY_RESET_MARKER)
    print("ORDER_HISTORY_RESET_20260908: local orders cleared")



# =========================
# TELEGRAM API
# =========================

def api(method, data=None):
    if data is None:
        data = {}

    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{API}/{method}", data=encoded)
    try:
        http_timeout = 65 if method == "getUpdates" else 40
        with urllib.request.urlopen(req, timeout=http_timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            body = ""
        print(f"Telegram API HTTP {e.code} [{method}]: {body}")
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Telegram API tarmoq xatosi [{method}]: {e}")
        raise

def _telegram_message_chunks(text, max_utf16_units=3000):
    """Xabarni Telegram chegarasidan oshirmasdan, matn yo‘qotmay bo‘ladi."""
    content = str(text)
    if len(content.encode("utf-16-le")) // 2 <= max_utf16_units:
        return [content]
    chunks = []
    current = []
    units = 0
    for char in content:
        char_units = 2 if ord(char) > 0xFFFF else 1
        if current and units + char_units > max_utf16_units:
            chunks.append("".join(current))
            current = []
            units = 0
        current.append(char)
        units += char_units
    if current:
        chunks.append("".join(current))
    return chunks


def send(chat_id, text, reply_markup=None):
    # Telegram 4096 UTF-16 birlikdan uzun sendMessage matnini rad etadi.
    # Menyu faqat yakuniy xabarga beriladi; hech bir kitob tushib qolmaydi.
    chunks = _telegram_message_chunks(text)
    result = None
    for index, chunk in enumerate(chunks):
        data = {"chat_id": chat_id, "text": chunk}
        if reply_markup is not None and index == len(chunks) - 1:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        result = api("sendMessage", data)
    return result


def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    return api("editMessageText", data)


def send_document(chat_id, filename, content, caption=""):
    """Telegramga JSON backup faylini multipart orqali yuboradi."""
    boundary = "----WebKitFormBoundaryBackupBot"
    body = bytearray()

    def add_field(name, value):
        body.extend((f"--{boundary}\r\n").encode())
        body.extend((f'Content-Disposition: form-data; name="{name}"\r\n\r\n').encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)

    body.extend((f"--{boundary}\r\n").encode())
    body.extend((f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n').encode())
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(content.encode("utf-8"))
    body.extend(b"\r\n")
    body.extend((f"--{boundary}--\r\n").encode())

    request = urllib.request.Request(
        f"{API}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def create_books_backup():
    """Faqat kitoblar katalogini alohida JSON backup qiladi."""
    refresh_books()
    return json.dumps({
        "backup_version": 2,
        "backup_type": "books",
        "created_at": datetime.now().isoformat(),
        "books": books,
    }, ensure_ascii=False, indent=2)


def create_data_backup():
    """Kitoblardan tashqari doimiy ma'lumotlarni alohida JSON backup qiladi."""
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()
    load_expenses()
    return json.dumps({
        "backup_version": 2,
        "backup_type": "data",
        "created_at": datetime.now().isoformat(),
        "orders": orders,
        "users": users,
        "favorites": favorites,
        "ratings": ratings,
        "restock_subscribers": restock_subscribers,
        "expenses": expenses,
    }, ensure_ascii=False, indent=2)


def restore_backup_file(path):
    """Books/data v2 backup yoki eski full backupni xavfsiz tiklaydi."""
    global books, orders, users, favorites, ratings, restock_subscribers, expenses

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Backup fayli noto'g'ri formatda.")

    backup_type = str(data.get("backup_type") or "").strip().lower()
    is_books = backup_type == "books"
    is_data = backup_type == "data"
    is_legacy = not backup_type and isinstance(data.get("books"), list)
    if not (is_books or is_data or is_legacy):
        raise ValueError("Backup turi aniqlanmadi.")

    payloads = {}

    if is_books or is_legacy:
        if not isinstance(data.get("books"), list):
            raise ValueError("Kitoblar backupida books ro'yxati yo'q.")
        restored_books = []
        for raw_book in data.get("books", []):
            if not isinstance(raw_book, dict):
                continue
            restored_book = dict(raw_book)
            restored_book.pop("cloud_id", None)
            restored_book.pop("web_photo_source_id", None)
            restored_books.append(restored_book)
        payloads[BOOKS_FILE] = restored_books

    if is_data or is_legacy:
        load_expenses()
        raw_orders = data.get("orders", {})
        if not isinstance(raw_orders, dict):
            raw_orders = {}
        restored_orders = {}
        for key, value in raw_orders.items():
            if not isinstance(value, dict):
                continue
            try:
                oid = int(value.get("order_id", key) or 0)
            except Exception:
                oid = 0
            if oid >= STATS_RESET_ORDER_ID:
                restored_orders[str(key)] = value
        raw_ratings = data.get("ratings", {})
        if not isinstance(raw_ratings, dict):
            raw_ratings = {}
        restored_order_ids = {
            str(v.get("order_id", k)) for k, v in restored_orders.items()
            if isinstance(v, dict)
        }
        restored_ratings = {
            str(k): v for k, v in raw_ratings.items()
            if str(k) in restored_order_ids
        }
        payloads.update({
            ORDERS_FILE: restored_orders,
            USERS_FILE: data.get("users", {}),
            FAVORITES_FILE: data.get("favorites", {}),
            RATINGS_FILE: restored_ratings,
            RESTOCK_FILE: data.get("restock_subscribers", {}),
            EXPENSES_FILE: data.get("expenses", expenses),
        })

    temp_files = []
    try:
        for target, value in payloads.items():
            tmp = target + ".restore.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            temp_files.append((tmp, target))
        for tmp, target in temp_files:
            os.replace(tmp, target)
    except Exception:
        for tmp, _ in temp_files:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
        raise

    if is_books or is_legacy:
        load_books()
    if is_data or is_legacy:
        load_orders()
        load_users()
        load_favorites()
        load_ratings()
        load_restock()
        load_expenses()

    carts.clear()
    states.clear()
    return len(books), len(orders), len(users)


def download_telegram_file(file_id, destination):
    """Telegram documentini botga yuklab oladi."""
    result = api("getFile", {"file_id": file_id})
    file_path = result.get("result", {}).get("file_path")
    if not file_path:
        raise ValueError("Telegram fayl manzili topilmadi.")

    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()

    with open(destination, "wb") as f:
        f.write(content)


# =========================
# SAQLASH / YUKLASH
# =========================

def save_books():
    # Atomik yozish: boshqa process o'qiyotgan paytda books.json yarimta holatda qolmaydi.
    tmp_file = BOOKS_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, BOOKS_FILE)


def sync_book_stock_from_disk():
    """Faqat qoldiqni diskdagi eng yangi books.json bilan sinxronlaydi."""
    global books
    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            disk_books = json.load(f)
        disk_by_id = {str(b.get("id")): b for b in disk_books}
        for b in books:
            db = disk_by_id.get(str(b.get("id")))
            if db is not None:
                b["stock"] = int(db.get("stock", 0))
    except Exception as e:
        print("Stock sync xatosi:", e)


def refresh_books():
    """books.json ni har safar qayta o'qib, barcha foydalanuvchilarga eng yangi qoldiqni beradi."""
    load_books()
    return books


def _apply_cloud_stocks(stocks):
    """Supabase qaytargan aniq qoldiqni botning local katalogiga yozadi."""
    if not isinstance(stocks, dict) or not stocks:
        return
    refresh_books()
    changed = False
    for book in books:
        key = str(book.get("id"))
        if key in stocks:
            value = max(0, int(stocks[key]))
            if int(book.get("stock", 0)) != value:
                book["stock"] = value
                changed = True
    if changed:
        save_books()


def _cloud_set_order_status(order, status):
    result = cloud_bridge.set_order_status(order, status)
    if isinstance(result, dict):
        if result.get("id"):
            order["cloud_order_id"] = str(result["id"])
        _apply_cloud_stocks(result.get("stocks"))
    if status == "cancelled":
        try:
            refresh_display_order_numbers(force=True)
        except Exception:
            pass
    return result


_order_display_cache = {}
_order_display_cache_at = 0.0


_app_status_sync_at = 0.0


def sync_app_order_status_notifications(force=False):
    """Ilovadan boshqarilgan Telegram zakas holatini botga olib, mijozga xabar beradi."""
    global _app_status_sync_at
    now = time.time()
    if not force and now - _app_status_sync_at < 8:
        return
    _app_status_sync_at = now
    try:
        rows = cloud_bridge.order_status_changes()
    except Exception as exc:
        print("Ilova zakas status sync xatosi:", exc)
        return

    local_by_id = {str(o.get("order_id") or k): o for k, o in orders.items()}
    changed = False
    for row in rows:
        order_id = str(row.get("order_id") or "").strip()
        order = local_by_id.get(order_id)
        if not order:
            continue
        cloud_status = str(row.get("status") or "").strip()
        local_status = str(order.get("status") or "pending").strip()
        bot_status = "shipped" if cloud_status == "shipping" else cloud_status
        if bot_status not in ("accepted", "paid", "shipped", "cancelled") or bot_status == local_status:
            continue

        # Ilovadan qabul/yuborildi qilingan holat botdagi local nusxaga ham o'tadi.
        order["status"] = bot_status
        changed = True
        chat_id = int(order.get("chat_id") or row.get("chat_id") or 0)
        if chat_id <= 0:
            continue
        try:
            if bot_status == "accepted":
                send(chat_id, "📦 Buyurtmangiz qabul qilindi.", main_menu(chat_id))
            elif bot_status == "shipped":
                name = str(order.get("name") or "").strip() or "—"
                phone = str(order.get("phone") or "").strip() or "—"
                address = str(order.get("address") or "").strip() or "—"
                send(
                    chat_id,
                    "🚚 Buyurtmangiz yuborildi.\\n\\n"
                    f"👤 Ism: {name}\\n"
                    f"📞 Telefon: {phone}\\n"
                    f"📍 Manzil: {address}\\n\\n"
                    "Muhajeer Books 📚",
                    main_menu(chat_id),
                )
        except Exception as exc:
            print("Mijozga status xabari yuborish xatosi:", exc)
    if changed:
        save_orders()


def refresh_display_order_numbers(force=False):
    global _order_display_cache, _order_display_cache_at
    now = time.time()
    if not force and _order_display_cache and now - _order_display_cache_at < 10:
        return _order_display_cache
    try:
        result = cloud_bridge.order_number_map()
        if isinstance(result, dict):
            clean = {}
            for key, value in result.items():
                try:
                    number = int(value)
                except Exception:
                    continue
                if number > 0:
                    clean[str(key)] = number
            _order_display_cache = clean
            _order_display_cache_at = now
    except Exception as exc:
        print("Zakas tartib raqamlari sync xatosi:", exc)
    return _order_display_cache


def display_order_number(order):
    if str(order.get("status") or "").strip() == "cancelled":
        return ""
    try:
        stored = int(order.get("display_order_number") or 0)
    except Exception:
        stored = 0
    if stored > 0:
        return str(stored)

    key = str(order.get("order_id") or "").strip()
    if key:
        mapping = refresh_display_order_numbers(False)
        number = mapping.get(key)
        if number is None:
            mapping = refresh_display_order_numbers(True)
            number = mapping.get(key)
        if number:
            return str(int(number))
    return key


def find_order_by_display_number(text, chat_id=None):
    needle = str(text or "").strip()
    if not needle.isdigit():
        return None
    normalized = str(int(needle))
    refresh_display_order_numbers(False)
    for order in orders.values():
        if chat_id is not None and int(order.get("chat_id", -1)) != int(chat_id):
            continue
        if str(order.get("order_id") or "") == needle:
            return order
        if display_order_number(order) == normalized:
            return order
    return None


def normalize_cover(text):
    value = str(text or "").strip().lower()

    if value in ("-", "—", "ko‘rsatilmagan", "korsatilmagan"):
        return "Ko‘rsatilmagan"

    if value in ("qattiq", "hardcover", "hard cover"):
        return "Qattiq"

    if value in ("yumshoq", "softcover", "soft cover"):
        return "Yumshoq"

    if value in ("flexible", "flex"):
        return "Flexible"

    return None


def normalize_category(value):
    value = str(value or "").strip()
    if value in ("", "-", "—", "Boshqa", "Boshqalar"):
        return "Boshqalar"
    return value


def load_books():
    global books

    books_file_exists = os.path.exists(BOOKS_FILE)
    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            loaded_books = json.load(f)
        if not isinstance(loaded_books, list):
            raise ValueError("books.json ro‘yxat formatida emas")
        books = loaded_books
    except Exception as e:
        print("books.json o‘qish xatosi:", e)
        # Mavjud persistent fayl o‘qilmasa, uning ustidan default bilan yozmaymiz.
        if books_file_exists:
            if not isinstance(books, list):
                books = []
            return
        books = []

    changed = False

    # 2026-09-06: foydalanuvchi bergan yangi partiyani persistent omborga
    # xavfsiz, bir martalik merge qilamiz. Mavjud nomlar dublikat bo‘lmaydi
    # va ularning narxi/qoldig‘i ustidan yozilmaydi.
    if False and not os.path.exists(BOOK_IMPORT_MARKER):
        import_items = [
            ("Dafina", 2, 12000),
            ("57-polk Falastin", 1, 13000),
            ("Falsafa devor ortidagi sir", 2, 8000),
            ("Professor o‘rdakburun", 1, 8000),
            ("G‘ildiraklar ostida", 1, 13000),
            ("Vavilondagi eng boy odam", 2, 14000),
            ("Boy ota kambag‘al ota", 1, 14000),
            ("O‘yla va boy bo‘l", 2, 15000),
            ("Yuksalish strategiyasi", 2, 20000),
            ("Daftar hoshiyasidagi bitiklar", 3, 9000),
            ("Pul alifbosi", 2, 11000),
            ("Rizq kalitlari", 2, 15000),
            ("Ulamolar naznida vaqtning qadri", 2, 14000),
            ("Fursat (o‘zgarish oni)", 4, 8000),
            ("Halovat hissini tuy", 2, 8000),
            ("Men Yusuf", 2, 23000),
            ("O'limdan keyingi hayot", 1, 14000),
            ("Ochilmagan maktublar", 1, 15000),
            ("Qonini sotgan odam", 2, 16000),
            ("Yettinchi kun", 2, 17000),
            ("Baxt yelkanlari", 2, 8000),
            ("Buyuk haqiqat yoxud fitrat qichqirig'i", 3, 8000),
            ("Sovchilikdan turmushga qadar", 1, 18000),
            ("Qanday buyuk bo‘lishgan", 2, 13000),
            ("Otalar yig‘lamaydi", 1, 9000),
            ("Cho‘pon yutib ketdi", 1, 9000),
            ("Oyoqyalang bolalar", 2, 9000),
            ("O‘g‘irlangan diqqat", 1, 19000),
            ("Hadis va hayot 1-qism", 1, 13000),
            ("Islom psixologiyasi", 1, 22000),
            ("12 stul", 1, 17000),
            ("Oqshom go‘zalliklari", 1, 23000),
            ("Binafsha 2-qism", 4, 23000),
            ("Til sayqali", 1, 21000),
            ("Metin qoyalar", 2, 20000),
            ("Er xotinga nasihat", 4, 26000),
            ("Shaxmat ustidagi qotillik", 2, 16000),
            ("Qur’on qalbiga safar", 1, 21000),
            ("Muallim soniy yashil", 3, 10000),
            ("Insonlar sayyorasi", 2, 15000),
            ("Uzrnoma", 2, 14000),
        ]

        def import_name_key(value):
            s = str(value or "").strip().casefold()
            for ch in ("’", "‘", "`", "ʻ", "ʼ"):
                s = s.replace(ch, "'")
            return " ".join(s.split())

        existing_names = {import_name_key(b.get("name", "")) for b in books}
        next_id = max(
            [int(b.get("id", 0)) for b in books if str(b.get("id", "")).isdigit()],
            default=0
        ) + 1
        added = 0
        skipped = 0
        now_iso = datetime.now().isoformat()
        for name, stock, price in import_items:
            key = import_name_key(name)
            if key in existing_names:
                skipped += 1
                continue
            books.append({
                "id": next_id,
                "name": name,
                "price": int(price),
                "stock": int(stock),
                "category": "Boshqalar",
                "author": "Ko‘rsatilmagan",
                "description": "Ma’lumot kiritilmagan.",
                "old_price": 0,
                "cost_price": 0,
                "photo_id": "",
                "cover": "Ko‘rsatilmagan",
                "recommended": False,
                "created_at": now_iso
            })
            existing_names.add(key)
            next_id += 1
            added += 1
            changed = True

        # Marker faqat books.json muvaffaqiyatli yozilgandan keyin yaratiladi.
        if changed:
            save_books()
        marker_tmp = BOOK_IMPORT_MARKER + ".tmp"
        with open(marker_tmp, "w", encoding="utf-8") as f:
            f.write(f"added={added};skipped={skipped};at={datetime.now().isoformat()}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(marker_tmp, BOOK_IMPORT_MARKER)
        print(f"BOOK_IMPORT_20260906: added={added} skipped={skipped}")

    # ASSASIN_LEGACY_CLEANUP_20260908
    # Eski versiyada Assasin hardcoded tarzda har load_books() da qayta qo‘shilardi.
    # Endi bu avtomatik qo‘shish butunlay olib tashlangan. Bir martalik migratsiya
    # Railway volume ichida qolgan eski Assasin nusxasini ham tozalaydi.
    assasin_cleanup_marker = os.path.join(DATA_DIR, "assasin_cleanup_20260908_v1.done")
    if not os.path.exists(assasin_cleanup_marker):
        before_count = len(books)
        books[:] = [
            b for b in books
            if str(b.get("name", "")).strip().casefold() != "assasin"
        ]
        removed_count = before_count - len(books)
        if removed_count:
            changed = True
        marker_tmp = assasin_cleanup_marker + ".tmp"
        with open(marker_tmp, "w", encoding="utf-8") as f:
            f.write(f"removed={removed_count};at={datetime.now().isoformat()}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(marker_tmp, assasin_cleanup_marker)
        print(f"ASSASIN_LEGACY_CLEANUP_20260908: removed={removed_count}")

    for b in books:
        category = normalize_category(b.get("category", "Boshqalar"))
        if b.get("category") != category:
            b["category"] = category
            changed = True

        defaults = {
            "category": "Boshqalar",
            "author": "Ko‘rsatilmagan",
            "description": "Ma’lumot kiritilmagan.",
            "old_price": 0,
            "cost_price": 0,
            "photo_id": "",
            "cover": "Ko‘rsatilmagan",
            "recommended": False,
            "created_at": ""
        }
        for key, value in defaults.items():
            if key not in b:
                b[key] = value
                changed = True

    if changed or not os.path.exists(BOOKS_FILE):
        save_books()


def save_orders():
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)


def load_orders():
    global orders

    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)
        if orders.pop("1789499997196", None) is not None:
            save_orders()
    except Exception:
        orders = {}
        save_orders()


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Users saqlash xatosi:", e)


def load_users():
    global users

    file_exists = os.path.exists(USERS_FILE)

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        if not isinstance(loaded, dict):
            raise ValueError("users.json lug‘at formatida emas")

        users = loaded

        # Eski users.json uchun faoliyat vaqtini bir marta boshlang‘ich qilib qo‘yamiz.
        # Shunda botdagi mavjud mijozlar ham funksiyaga qo‘shiladi, lekin darhol xabar olmaydi.
        changed = False
        now = int(time.time())
        for key, item in users.items():
            if not isinstance(item, dict):
                continue
            if not item.get("last_active"):
                item["last_active"] = now
                item["inactive_message_sent"] = False
                changed = True
            elif "inactive_message_sent" not in item:
                item["inactive_message_sent"] = False
                changed = True
            if not item.get("last_bot_active") and item.get("last_active"):
                item["last_bot_active"] = item["last_active"]
                changed = True
        if changed:
            save_users()

    except Exception as e:
        print("users.json o‘qish xatosi:", e)

        # Fayl mavjud bo‘lsa, vaqtinchalik o‘qish xatosi sabab
        # foydalanuvchilar ro‘yxatini bo‘shatib, ustidan yozmaymiz.
        # Xotirada oldingi ma’lumot bo‘lsa, uni saqlab qolamiz.
        if not file_exists:
            users = {}
            save_users()
        elif not isinstance(users, dict):
            users = {}


def save_expenses():
    tmp_file = EXPENSES_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(expenses, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp_file, EXPENSES_FILE)

def load_expenses():
    global expenses
    try:
        with open(EXPENSES_FILE, "r", encoding="utf-8") as f: loaded=json.load(f)
        expenses = loaded if isinstance(loaded, dict) else {}
    except Exception:
        expenses={}
        if not os.path.exists(EXPENSES_FILE): save_expenses()

def add_postage_expense(amount):
    load_expenses(); key=datetime.now().date().isoformat(); items=expenses.setdefault(key, [])
    if not isinstance(items, list): items=[]; expenses[key]=items
    items.append({"amount":int(amount),"created_at":datetime.now().isoformat(timespec="seconds")}); save_expenses()

def postage_expense_for_period(period="all"):
    load_expenses(); now=datetime.now(); total=0
    for date_key, items in expenses.items():
        try: day=_local_datetime(str(date_key)).date()
        except Exception: continue
        include = period=="all" or (period=="today" and day==now.date()) or (period=="week" and day >= (now-timedelta(days=7)).date()) or (period=="month" and day.year==now.year and day.month==now.month)
        if include and isinstance(items,list):
            for item in items:
                try: total += int(item.get("amount",0) if isinstance(item,dict) else item)
                except Exception: pass
    return total


# =========================
# YORDAMCHI
# =========================

def save_favorites():
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Favorites save xatosi:", e)


def load_favorites():
    global favorites
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            favorites = json.load(f)
    except Exception:
        favorites = {}
        save_favorites()


def save_ratings():
    try:
        with open(RATINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(ratings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Ratings save xatosi:", e)


def load_ratings():
    global ratings
    try:
        with open(RATINGS_FILE, "r", encoding="utf-8") as f:
            ratings = json.load(f)
    except Exception:
        ratings = {}
        save_ratings()


def save_restock():
    try:
        with open(RESTOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(restock_subscribers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Restock save xatosi:", e)


def load_restock():
    global restock_subscribers
    try:
        with open(RESTOCK_FILE, "r", encoding="utf-8") as f:
            restock_subscribers = json.load(f)
    except Exception:
        restock_subscribers = {}
        save_restock()






def book_rating(book_id):
    values = []
    for item in ratings.values():
        try:
            value = item.get("ratings", {}).get(str(book_id))
            if value:
                values.append(int(value))
        except Exception:
            pass
    if not values:
        return 0, 0
    return sum(values) / len(values), len(values)


def book_reviews(book_id, limit=2):
    result = []
    for item in reversed(list(ratings.values())):
        review = item.get("reviews", {}).get(str(book_id))
        if isinstance(review, dict):
            review_text = str(review.get("text", "") or "").strip()
            if review_text:
                result.append({
                    "name": str(review.get("name", "Mijoz") or "Mijoz"),
                    "text": review_text[:150]
                })
        if len(result) >= limit:
            break
    return result


def user_has_rated(chat_id, order_id, book_id):
    item = ratings.get(str(order_id), {})
    if str(item.get("chat_id")) != str(chat_id):
        return False
    return str(book_id) in item.get("ratings", {})


def effective_price(book):
    price = int(book.get("price", 0) or 0)
    old = int(book.get("old_price", 0) or 0)
    ends_at = str(book.get("discount_ends_at") or "").strip()
    if ends_at:
        try:
            if _local_datetime(ends_at) <= datetime.now():
                return old if old > price > 0 else price
        except Exception:
            pass
    if old > price > 0:
        return price
    return price


def apply_global_discount(percent):
    """Barcha kitoblarga berilgan foiz chegirmani qo‘llaydi."""
    percent = int(percent)
    if percent < 1 or percent > 99:
        raise ValueError("Chegirma 1 dan 99 gacha bo‘lsin.")

    changed = 0
    for book in books:
        price = int(book.get("price", 0) or 0)
        if price <= 0:
            continue

        # Bir necha marta chegirma berilganda ustma-ust hisoblamaymiz.
        if "global_discount_base_price" not in book:
            book["global_discount_base_price"] = price
            book["global_discount_old_price"] = int(book.get("old_price", 0) or 0)

        base_price = int(book.get("global_discount_base_price", price) or price)
        discounted = max(1, (base_price * (100 - percent)) // 100)
        book["old_price"] = base_price
        book["price"] = discounted
        book["discount_percent"] = percent
        changed += 1

    save_books()
    return changed


def remove_global_discount():
    """Global chegirmani bekor qilib, kitoblarni avvalgi narxlariga qaytaradi."""
    changed = 0
    for book in books:
        if "global_discount_base_price" not in book:
            continue

        base_price = int(book.get("global_discount_base_price", book.get("price", 0)) or 0)
        previous_old_price = int(book.get("global_discount_old_price", 0) or 0)
        book["price"] = base_price
        book["old_price"] = previous_old_price
        book.pop("global_discount_base_price", None)
        book.pop("global_discount_old_price", None)
        book.pop("discount_percent", None)
        changed += 1

    save_books()
    return changed


def _strike_text(text):
    """Matnni Telegram parse_mode ishlatmasdan ustidan chiziq bilan ko‘rsatadi."""
    return "".join(ch + "\u0336" for ch in str(text))


def price_text(book):
    price = effective_price(book)
    old = int(book.get("old_price", 0) or 0)
    if old > price > 0:
        old_price = _strike_text(f"₩{old:,}")
        return f"🔴 Eski narx: {old_price}\n🟢🔥 Chegirmadagi narx: ₩{price:,}"
    return f"💰 Narx: ₩{price:,}"


def subscribe_restock(chat_id, book_id):
    key = str(book_id)
    users_list = set(str(x) for x in restock_subscribers.get(key, []))
    users_list.add(str(chat_id))
    restock_subscribers[key] = sorted(users_list)
    save_restock()


def notify_restock(book):
    key = str(book.get("id"))
    targets = list(restock_subscribers.get(key, []))
    if not targets or int(book.get("stock", 0)) <= 0:
        return

    failed_targets = []
    for uid in targets:
        try:
            send(
                int(uid),
                f"🔔 YAXSHI YANGILIK!\n\n"
                f"📖 {book['name']} qayta sotuvda!\n"
                f"📦 Omborda: {int(book['stock'])} ta\n\n"
                "Kitob buyurtma qilish uchun ilovamizga kiring.",
                {"inline_keyboard": [[{"text": ORDER_APP_BUTTON, "url": APP_DOWNLOAD_URL}]]}
            )
        except Exception as e:
            failed_targets.append(str(uid))
            print("Restock xatosi:", uid, e)

    if failed_targets:
        restock_subscribers[key] = sorted(set(failed_targets))
    else:
        restock_subscribers.pop(key, None)
    save_restock()


def best_sellers():
    sold = {}
    for o in orders.values():
        if o.get("status") == "shipped":
            for bid, qty in o.get("cart", {}).items():
                try:
                    sold[int(bid)] = sold.get(int(bid), 0) + int(qty)
                except Exception:
                    pass
    return sorted(sold.items(), key=lambda x: x[1], reverse=True)


def best_sellers_keyboard(limit=10):
    buttons = []
    for bid, qty in best_sellers()[:limit]:
        b = find_book(bid)
        if b:
            buttons.append([{"text": f"🏆 {b['name']} — {qty} dona", "callback_data": f"book_{b['id']}"}])
    buttons.append([{ "text": "🏠 Bosh menyu", "callback_data": "home" }])
    return {"inline_keyboard": buttons}












def order_receipt_text(order):
    lines = ["🧾 BUYURTMA CHEKI", "", f"🔢 Buyurtma №{display_order_number(order)}",
             f"👤 {order.get('name', '')}", f"📱 {order.get('phone', '')}",
             f"📍 {order.get('address', '')}", ""]
    total = 0
    saved_items = order.get("items")
    if isinstance(saved_items, list) and saved_items:
        for item in saved_items:
            name = str(item.get("name", "Kitob"))
            qty = int(item.get("qty", 0))
            unit_price = int(item.get("unit_price", 0))
            subtotal = unit_price * qty
            total += subtotal
            lines.append(f"📖 {name} × {qty} — ₩{subtotal:,}")
        total = int(order.get("total", total))
    else:
        for bid, qty in order.get("cart", {}).items():
            book = find_book(bid)
            if not book:
                continue
            qty = int(qty)
            subtotal = effective_price(book) * qty
            total += subtotal
            lines.append(f"📖 {book['name']} × {qty} — ₩{subtotal:,}")
    delivery = int(order.get("delivery_fee", DELIVERY_FEE))
    discount = int(order.get("discount", 0))
    grand = int(order.get("grand_total", total + delivery - discount))
    lines += [
        "",
        f"💰 Kitoblar: ₩{total:,}",
        f"🚚 Yetkazib berish: {delivery_text(delivery)}",
        "⏱ Yetkazish muddati: 1–3 ish kuni"
    ]
    if discount:
        lines.append(f"🎁 Chegirma: ₩{discount:,}")
    lines += [f"💵 JAMI: ₩{grand:,}", "", f"Holati: {status_name(order.get('status'))}"]
    return "\n".join(lines)


def status_name(status):
    return {
        "pending": "🟡 To‘lov kutilmoqda",
        "accepted": "📦 Buyurtma qabul qilingan",
        "paid": "🟢 To‘lov tasdiqlangan",
        "shipped": "🚚 Jo‘natildi",
        "delivered": "🚚 Jo‘natildi",
        "cancelled": "❌ Bekor qilindi",
        "stock_problem": "⚠️ Ombor muammosi"
    }.get(status, "❓ Noma’lum")


def favorite_ids(chat_id):
    return set(int(x) for x in favorites.get(str(chat_id), []))


def toggle_favorite(chat_id, book_id):
    key = str(chat_id)
    current = set(int(x) for x in favorites.get(key, []))
    if int(book_id) in current:
        current.remove(int(book_id))
        added = False
    else:
        current.add(int(book_id))
        added = True
    favorites[key] = sorted(current)
    save_favorites()
    return added


def category_list():
    cats = []
    for b in books:
        c = normalize_category(b.get("category", "Boshqalar"))
        if c not in cats:
            cats.append(c)
    return cats or ["Boshqalar"]


def categories_keyboard():
    buttons = []
    for i, c in enumerate(category_list()):
        buttons.append([{
            "text": f"📂 {c}",
            "callback_data": f"catidx_{i}"
        }])
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}


def book_detail_text(book):
    stock = int(book.get("stock", 0))
    category = normalize_category(book.get("category", "Boshqalar"))
    author = str(book.get("author", "") or "").strip()
    cover = str(book.get("cover", "") or "").strip()
    desc = str(book.get("description", "") or "").strip()
    avg, count = book_rating(book["id"])

    lines = [
        "📚 MUHAJEER BOOKS",
        "━━━━━━━━━━━━━━",
        f"📖 {book['name']}",
    ]

    if book.get("recommended"):
        lines.append("🔥 Muhajeer Books tavsiya qiladi")

    lines.extend([
        "",
        price_text(book),
        f"📦 Holati: {'Sotuvda — ' + str(stock) + ' ta' if stock > 0 else 'Hozircha mavjud emas'}",
    ])

    if category and category != "Boshqalar":
        lines.append(f"📂 Kategoriya: {category}")
    if author and author != "Ko‘rsatilmagan":
        lines.append(f"✍️ Muallif: {author}")
    if cover and cover != "Ko‘rsatilmagan":
        lines.append(f"📕 Muqova: {cover}")

    lines.append(
        f"⭐ Reyting: {avg:.1f}/5 · {count} ta baho"
        if count else "⭐ Hali baholanmagan"
    )

    reviews = book_reviews(book["id"])
    if reviews:
        lines.extend(["", "💬 MIJOZLAR FIKRI"])
        for review in reviews:
            lines.append(f"• {review['name']}: {review['text']}")

    if desc and desc != "Ma’lumot kiritilmagan.":
        lines.extend(["", "📝 KITOB HAQIDA", desc])

    lines.extend(["", "━━━━━━━━━━━━━━", "Kerakli amalni quyidan tanlang 👇"])
    return "\n".join(lines)


def book_detail_keyboard(book, chat_id):
    fav = int(book["id"]) in favorite_ids(chat_id)
    fav_text = "💔 Sevimlilardan olib tashlash" if fav else "❤️ Sevimlilarga qo‘shish"
    buttons = []
    if int(book.get("stock", 0)) > 0 and int(book.get("price", 0)) > 0:
        buttons.append([{ "text": "🛒 Xaridga qo‘shish", "callback_data": f"addcart_{book['id']}" }])
    elif int(book.get("stock", 0)) <= 0:
        if str(chat_id) in [str(x) for x in restock_subscribers.get(str(book["id"]), [])]:
            buttons.append([{ "text": "🔔 Xabar berish yoqilgan", "callback_data": "cart_noop" }])
        else:
            buttons.append([{ "text": "🔔 Kelganda xabar bering", "callback_data": f"restock_{book['id']}" }])
    buttons.append([{ "text": fav_text, "callback_data": f"fav_{book['id']}" }])
    buttons.append([{ "text": "📚 Kitoblar", "callback_data": "books" }, {"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}


def send_book_detail(chat_id, book):
    text = book_detail_text(book)
    markup = book_detail_keyboard(book, chat_id)
    # Text-only Telegram catalog; preserve image fields for the app.
    send(chat_id, text, markup)


def favorites_keyboard(chat_id):
    ids = favorite_ids(chat_id)
    buttons = []
    for b in books:
        if int(b["id"]) in ids:
            buttons.append([{ "text": f"❤️ {b['name']}", "callback_data": f"book_{b['id']}" }])
    buttons.append([{ "text": "📚 Kitoblar", "callback_data": "books" }, {"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}


def category_books_keyboard(category, chat_id, page=0):
    category = normalize_category(category)
    items = [
        b for b in books
        if normalize_category(b.get("category", "Boshqalar")) == category
    ]

    per_page = 8
    total_pages = max(1, (len(items) + per_page - 1) // per_page)

    try:
        page = int(page)
    except Exception:
        page = 0

    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    page_items = items[start:start + per_page]

    buttons = []

    for b in page_items:
        stock = int(b.get("stock", 0))
        p = effective_price(b)
        icon = "📖" if stock > 0 and p > 0 else "❌"
        label = f"{icon} {b['name']} — ₩{p:,}" if p else f"{icon} {b['name']}"
        buttons.append([{
            "text": label,
            "callback_data": f"book_{b['id']}" if stock > 0 and p > 0 else f"none_{b['id']}"
        }])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback_data": f"catpage_{page - 1}_{urllib.parse.quote(category, safe='')}"})
        nav.append({"text": f"{page + 1}/{total_pages}", "callback_data": "cart_noop"})
        if page < total_pages - 1:
            nav.append({"text": "▶️", "callback_data": f"catpage_{page + 1}_{urllib.parse.quote(category, safe='')}"})
        buttons.append(nav)

    buttons.append([{"text": "📂 Kategoriyalar", "callback_data": "categories"}])
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])

    return {"inline_keyboard": buttons}


def order_cart_keyboard(chat_id):
    kb = cart_keyboard(chat_id)
    rows = kb.get("inline_keyboard", [])
    rows.insert(0, [{"text": "⬅️ Buyurtmaga qaytish", "callback_data": "orderback_cart"}])
    return {"inline_keyboard": rows}


def order_edit_keyboard(state=None):
    paid_declared = bool((state or {}).get("payment_declared", False))

    # To‘lovdan oldin mijozni chalg‘itmaslik uchun faqat chek yuborish ko‘rsatiladi.
    if not paid_declared:
        return {
            "inline_keyboard": [
                [{"text": "📸 To‘lov chekini yuborish", "callback_data": "order_payment_done"}],
                [{"text": "❌ Bekor qilish", "callback_data": "order_cancel_cb"}],
            ]
        }

    # Chek yuborilgach mijoz ma’lumotlarni tekshirishi va kerak bo‘lsa tahrirlashi mumkin.
    return {
        "inline_keyboard": [
            [{"text": "✏️ Ism", "callback_data": "orderedit_name"},
             {"text": "📱 Telefon", "callback_data": "orderedit_phone"}],
            [{"text": "📍 Manzilni tahrirlash", "callback_data": "orderedit_address"}],
            [{"text": "✅ Buyurtmani tasdiqlash", "callback_data": "order_confirm_cb"}],
        ]
    }


def order_customer_info_text(state):
    return (
        "👤 Ism: " + str(state.get("name", "—")) + "\n"
        "📱 Telefon: " + str(state.get("phone", "—")) + "\n"
        "📍 Manzil: " + str(state.get("address", "—"))
    )

def order_status_keyboard():
    return {"inline_keyboard": [[{"text": "🔎 Buyurtma raqami bilan tekshirish", "callback_data": "order_lookup"}], [{"text": "🏠 Bosh menyu", "callback_data": "home"}]]}


def is_admin(chat_id):
    return str(chat_id) == ADMIN_ID


def find_book(book_id):
    refresh_books()
    for book in books:
        if int(book["id"]) == int(book_id):
            return book
    return None



# =========================
# POCHTA UCHUN ZAKASLAR
# =========================

def _shipping_queue_load():
    try:
        with open(SHIPPING_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        data = {}
    manual = data.get("manual")
    dismissed = data.get("dismissed_order_ids")
    return {
        "manual": manual if isinstance(manual, dict) else {},
        "dismissed_order_ids": [str(x) for x in dismissed] if isinstance(dismissed, list) else [],
    }


def _shipping_queue_save(data):
    safe = {
        "manual": data.get("manual", {}) if isinstance(data.get("manual", {}), dict) else {},
        "dismissed_order_ids": sorted(set(str(x) for x in data.get("dismissed_order_ids", []))),
    }
    tmp = SHIPPING_QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, SHIPPING_QUEUE_FILE)


def _shipping_books_text(order):
    lines = []
    items = order.get("items")
    if isinstance(items, list) and items:
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or "Kitob").strip() or "Kitob"
            try:
                qty = max(1, int(item.get("qty") or item.get("quantity") or 1))
            except Exception:
                qty = 1
            lines.append(f"• {name} × {qty}")
    if not lines:
        for bid, qty_raw in (order.get("cart") or {}).items():
            try:
                qty = max(1, int(qty_raw))
            except Exception:
                qty = 1
            book = find_book(bid)
            name = str((book or {}).get("name") or f"Kitob #{bid}")
            lines.append(f"• {name} × {qty}")
    return "\n".join(lines) if lines else "• Kitob ma’lumoti yo‘q"


def _shipping_source_label(source):
    return {
        "telegram": "🤖 Telegram bot",
        "app": "📱 Ilova / Web",
        "manual": "✍️ Qo‘lda",
    }.get(str(source), "📦 Zakas")


def _shipping_status_label(status):
    return {
        "pending": "🟡 Kutilmoqda",
        "accepted": "📦 Qabul qilingan",
        "paid": "🟢 To‘langan",
        "shipped": "🚚 Jo‘natilgan",
    }.get(str(status), str(status or "—"))


def shipping_queue_entries(source_filter="all"):
    rows = cloud_bridge.shipping_queue_list()
    entries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "")
        if source_filter not in ("all", source):
            continue
        entry = dict(row)
        entry["queue_kind"] = str(entry.get("queue_kind") or ("manual" if source == "manual" else "order"))
        entry["queue_id"] = str(entry.get("queue_id") or "")
        entry["name"] = str(entry.get("name") or "Noma’lum")
        entry["phone"] = str(entry.get("phone") or "—")
        entry["address"] = str(entry.get("address") or "—")
        entry["books"] = str(entry.get("books") or "• Kitob ma’lumoti yo‘q")
        entry["address_photo_file_id"] = str(entry.get("address_photo_file_id") or "")
        entries.append(entry)
    return entries


def shipping_queue_menu():
    return {
        "keyboard": [
            [{"text": "📋 Barcha zakaslar"}, {"text": "➕ SMS / rasm"}],
            [{"text": "🤖 Bot zakaslari"}, {"text": "📱 Ilova zakaslari"}],
            [{"text": "✍️ Qo‘lda kiritilgan"}],
            [{"text": "⬅️ Admin panel"}],
        ],
        "resize_keyboard": True,
    }


def _shipping_copy_button(label, value):
    value = str(value or "").strip()
    if not value or value == "—" or len(value) > 256:
        return None
    return {"text": label, "copy_text": {"text": value}}


def shipping_entry_keyboard(entry):
    rows = []
    name_btn = _shipping_copy_button("👤 Ismni nusxalash", entry.get("name"))
    phone_btn = _shipping_copy_button("📞 Telefonni nusxalash", entry.get("phone"))
    address_btn = _shipping_copy_button("📍 Manzilni nusxalash", entry.get("address"))
    if name_btn:
        rows.append([name_btn])
    if phone_btn:
        rows.append([phone_btn])
    if address_btn:
        rows.append([address_btn])
    kind = "m" if entry.get("queue_kind") == "manual" else "o"
    rows.append([{
        "text": "🗑 Zakasni o‘chirish",
        "callback_data": f"shipdel_{kind}_{entry.get('queue_id')}",
    }])
    return {"inline_keyboard": rows}


def shipping_entry_text(entry, index=None):
    head = f"📦 ZAKAS {index}" if index is not None else "📦 ZAKAS"
    source = _shipping_source_label(entry.get("source"))
    lines = [
        head,
        f"{source}",
        "",
        f"👤 Ism: {entry.get('name') or '—'}",
        f"📞 Telefon: {entry.get('phone') or '—'}",
        f"📍 Manzil: {entry.get('address') or '—'}",
        "",
        "📚 Kitoblar:",
        str(entry.get("books") or "• Kitob ma’lumoti yo‘q"),
    ]
    if entry.get("queue_kind") == "order":
        lines.extend(["", f"Holati: {_shipping_status_label(entry.get('status'))}"])
    return "\n".join(lines)


def send_shipping_queue(chat_id, source_filter="all"):
    entries = shipping_queue_entries(source_filter)
    labels = {
        "all": "BARCHA ZAKASLAR",
        "telegram": "BOT ZAKASLARI",
        "app": "ILOVA ZAKASLARI",
        "manual": "QO‘LDA KIRITILGAN",
    }
    if not entries:
        send(chat_id, f"📦 {labels.get(source_filter, 'ZAKASLAR')}\n\nHozircha zakas yo‘q.", shipping_queue_menu())
        return
    send(chat_id, f"📦 {labels.get(source_filter, 'ZAKASLAR')} — {len(entries)} ta\n\nTelefon va manzilni alohida tugma bilan nusxalashingiz mumkin.")
    for index, entry in enumerate(entries[:40], 1):
        text = shipping_entry_text(entry, index)
        markup = shipping_entry_keyboard(entry)
        photo_id = str(entry.get("address_photo_file_id") or "").strip()
        if photo_id:
            try:
                api("sendPhoto", {
                    "chat_id": chat_id,
                    "photo": photo_id,
                    "caption": text,
                    "reply_markup": json.dumps(markup, ensure_ascii=False),
                })
                continue
            except Exception as exc:
                print("Zakas manzil rasmini yuborish xatosi:", exc)
        send(chat_id, text, markup)
    if len(entries) > 40:
        send(chat_id, f"ℹ️ Hozir birinchi 40 ta ko‘rsatildi. Jami {len(entries)} ta.", shipping_queue_menu())
    else:
        send(chat_id, "✅ Pochta uchun zakaslar shu yerda.", shipping_queue_menu())


def save_manual_shipping_order(state):
    result = cloud_bridge.shipping_queue_add(
        state.get("name"),
        state.get("phone"),
        state.get("address"),
        state.get("books"),
        state.get("address_photo_file_id", ""),
    )
    if not isinstance(result, dict):
        raise RuntimeError("Zakas serverga saqlanmadi")
    return result


def delete_shipping_queue_entry(kind, queue_id):
    return bool(cloud_bridge.shipping_queue_dismiss(kind, queue_id))



def _shipping_clean_line(value):
    return ' '.join(str(value or '').replace('\u200b', ' ').split()).strip()


def _shipping_phone_from_text(raw):
    raw = str(raw or '')
    patterns = [
        r'(?<!\d)(?:\+?82[-\s]?)?0?10[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)',
        r'(?<!\d)\+?\d[\d\s()\-]{7,18}\d(?!\d)',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw)
        if not m:
            continue
        value = m.group(0).strip()
        digits = ''.join(ch for ch in value if ch.isdigit())
        if 8 <= len(digits) <= 15:
            if value.startswith('+'):
                return '+' + digits
            return digits
    return ''


def _shipping_is_address_line(line):
    line = _shipping_clean_line(line)
    if not line:
        return False
    low = line.casefold()
    if any(key in low for key in ('manzil', 'address', '주소', '배송지', '받는 주소', '받는주소')):
        return True
    # Korean postal-address signals.
    if re.search(r'(특별시|광역시|특별자치시|특별자치도|[가-힣]+도|[가-힣]+시|[가-힣]+군|[가-힣]+구)', line):
        if re.search(r'(로|길|동|읍|면|리|번길|대로|\d+-\d+|\d+호)', line):
            return True
    if re.search(r'\b\d{5}\b', line) and re.search(r'[가-힣]', line):
        return True
    return False


def _shipping_extract_address(lines):
    labels = ('manzil', 'address', '주소', '배송지', '받는 주소', '받는주소')
    for i, raw in enumerate(lines):
        line = _shipping_clean_line(raw)
        low = line.casefold()
        if any(key in low for key in labels):
            value = re.sub(r'^(?:📍\s*)?(?:manzil|address|주소|배송지|받는\s*주소)\s*[:：\-]?\s*', '', line, flags=re.I).strip()
            parts = [value] if value else []
            for nxt in lines[i + 1:i + 3]:
                nxt = _shipping_clean_line(nxt)
                if not nxt or _shipping_phone_from_text(nxt):
                    break
                if _shipping_is_address_line(nxt) or re.search(r'(\d+호|층|동\s*\d+|\d+동|\d+[-–]\d+)', nxt):
                    parts.append(nxt)
                else:
                    break
            if parts:
                return ', '.join(parts)

    for i, raw in enumerate(lines):
        line = _shipping_clean_line(raw)
        if not _shipping_is_address_line(line):
            continue
        parts = [line]
        for nxt in lines[i + 1:i + 3]:
            nxt = _shipping_clean_line(nxt)
            if not nxt or _shipping_phone_from_text(nxt):
                break
            if _shipping_is_address_line(nxt) or re.search(r'(\d+호|층|\d+동|\d+[-–]\d+)', nxt):
                parts.append(nxt)
            else:
                break
        return ', '.join(parts)
    return ''


def _shipping_extract_name(lines, phone='', address=''):
    label_re = re.compile(r'^(?:👤\s*)?(?:ism|name|이름|성명|수취인|받는\s*분|받는\s*사람)\s*[:：\-]?\s*(.+)$', re.I)
    for raw in lines:
        line = _shipping_clean_line(raw)
        m = label_re.match(line)
        if m:
            value = _shipping_clean_line(m.group(1))
            if 1 < len(value) <= 80:
                return value

    # Common screenshot shape: name / phone / address on separate lines.
    for raw in lines:
        line = _shipping_clean_line(raw)
        if not line or len(line) > 60:
            continue
        low = line.casefold()
        if _shipping_phone_from_text(line) or _shipping_is_address_line(line):
            continue
        if address and line in address:
            continue
        if any(key in low for key in ('주문', '배송', '주소', '전화', 'phone', 'tel', 'mobile', 'order', 'manzil', 'kitob', 'book', '₩', '원')):
            continue
        if re.search(r'[A-Za-z가-힣А-Яа-яʻʼ’‘`\']', line):
            return line.strip(' -:：')
    return ''


def _shipping_qty_from_line(line, book_name):
    line = str(line or '')
    # Prefer quantity close to a book line; ignore prices/phones by capping at 99.
    candidates = []
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*(?:ta|dona|x|×)?(?!\d)', line, flags=re.I):
        try:
            value = int(m.group(1))
        except Exception:
            continue
        if 1 <= value <= 99:
            candidates.append(value)
    return candidates[-1] if candidates else 1


def _shipping_extract_books(lines, whole_text):
    refresh_books()
    found = {}
    whole_key = _search_key(whole_text)

    # High-confidence exact/substring matches first.
    for book in books:
        name = str(book.get('name') or '').strip()
        key = _search_key(name)
        if len(key.replace(' ', '')) < 4 or not key:
            continue
        match_line = ''
        for raw in lines:
            line_key = _search_key(raw)
            if key == line_key or key in line_key:
                match_line = str(raw)
                break
        if not match_line and key in whole_key:
            match_line = str(whole_text)
        if match_line:
            found[str(book.get('id'))] = {
                'name': name,
                'qty': _shipping_qty_from_line(match_line, name),
            }

    # If no exact title was present, try conservative fuzzy matching on short lines.
    if not found:
        for raw in lines:
            line = _shipping_clean_line(raw)
            if not line or len(line) > 90:
                continue
            if _shipping_phone_from_text(line) or _shipping_is_address_line(line):
                continue
            query = re.sub(r'(?<!\d)\d{1,2}\s*(?:ta|dona|x|×)?\s*$', '', line, flags=re.I).strip(' -:：•')
            if len(_search_key(query).replace(' ', '')) < 4:
                continue
            matches = _instagram_fuzzy_matches(query)
            if not matches:
                continue
            book = matches[0]
            if _fuzzy_ratio(query, book.get('name', '')) < 0.80:
                continue
            found[str(book.get('id'))] = {
                'name': str(book.get('name') or 'Kitob'),
                'qty': _shipping_qty_from_line(line, book.get('name', '')),
            }

    if not found:
        return ''
    return '\n'.join(f"• {item['name']} × {int(item['qty'])}" for item in found.values())


def parse_smart_shipping_text(raw):
    raw = str(raw or '').strip()
    lines = [_shipping_clean_line(x) for x in raw.splitlines() if _shipping_clean_line(x)]
    phone = _shipping_phone_from_text(raw)
    address = _shipping_extract_address(lines)
    name = _shipping_extract_name(lines, phone, address)
    book_text = _shipping_extract_books(lines, raw)
    return {
        'name': name,
        'phone': phone,
        'address': address,
        'books': book_text,
        'raw_text': raw,
    }


def _shipping_ocr_photo(file_id):
    tmp = os.path.join(DATA_DIR, f"shipping_ocr_{int(time.time() * 1000)}.jpg")
    try:
        download_telegram_file(file_id, tmp)
        last_error = ''
        for lang in ('kor+eng', 'eng'):
            try:
                result = subprocess.run(
                    ['tesseract', tmp, 'stdout', '-l', lang, '--psm', '6'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=30,
                    check=False,
                )
                text = str(result.stdout or '').strip()
                if text:
                    return text
                last_error = str(result.stderr or '').strip()
            except Exception as exc:
                last_error = str(exc)
        raise RuntimeError(last_error or 'Rasmdagi matn aniqlanmadi')
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def smart_shipping_preview(state):
    return (
        '📦 ZAKAS — TEKSHIRING\n\n'
        f"👤 Ism: {state.get('name') or '—'}\n"
        f"📞 Telefon: {state.get('phone') or '—'}\n"
        f"📍 Manzil: {state.get('address') or '—'}\n\n"
        '📚 Kitoblar:\n'
        f"{state.get('books') or '—'}"
    )


def smart_shipping_confirm_keyboard():
    return {'inline_keyboard': [
        [{'text': '✅ Saqlash', 'callback_data': 'shipsmart_save'}],
        [{'text': '❌ Bekor qilish', 'callback_data': 'shipsmart_cancel'}],
    ]}


def _smart_shipping_ask_next(chat_id, state):
    if not str(state.get('name') or '').strip():
        state['action'] = 'shipping_smart_missing_name'
        send(chat_id, '👤 Ismni topolmadim. Faqat mijoz ismini yozing:')
        return
    if not str(state.get('phone') or '').strip():
        state['action'] = 'shipping_smart_missing_phone'
        send(chat_id, '📞 Telefon raqamini topolmadim. Faqat raqamni yozing:')
        return
    if not str(state.get('address') or '').strip():
        state['action'] = 'shipping_smart_missing_address'
        send(chat_id, '📍 Manzilni topolmadim. Faqat to‘liq manzilni yozing:')
        return
    if not str(state.get('books') or '').strip():
        state['action'] = 'shipping_smart_missing_books'
        send(
            chat_id,
            '📚 Matn/rasm ichida kitob nomi yo‘q ekan.\n\n'
            'Faqat qaysi kitob(lar)ga zakas qilganini yozing.\n'
            'Masalan:\nDafina 1 ta\nSaodat asri 2 ta'
        )
        return
    state['action'] = 'shipping_smart_confirm'
    send(chat_id, smart_shipping_preview(state), smart_shipping_confirm_keyboard())


def _send_saved_shipping_entry(chat_id, entry):
    send(chat_id, '✅ Zakas Zakaslar bo‘limiga saqlandi.')
    photo_id = str(entry.get('address_photo_file_id') or '').strip()
    if photo_id:
        try:
            api('sendPhoto', {
                'chat_id': chat_id,
                'photo': photo_id,
                'caption': shipping_entry_text(entry),
                'reply_markup': json.dumps(shipping_entry_keyboard(entry), ensure_ascii=False),
            })
        except Exception:
            send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))
    else:
        send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))
    send(chat_id, '📦 Zakaslar', shipping_queue_menu())


# =========================
# MENYULAR
# =========================

def main_menu(chat_id):
    storefront = mini_app.menu_button() if int(chat_id) > 0 else None
    buttons = [[storefront or {"text": ORDER_APP_BUTTON}]]
    if is_admin(chat_id):
        buttons.append([{"text": "⚙️ Admin panel"}])

    return {
        "keyboard": buttons,
        "resize_keyboard": True
    }


def send_app_download_link(chat_id):
    if int(chat_id) > 0 and mini_app.menu_button():
        send(
            chat_id,
            "📚 Do‘konni ochish tugmasini bosib, Telegram ichida buyurtma bering.\n\n"
            f"📲 Muhajeer Books ilovasi: {APP_DOWNLOAD_URL}",
            main_menu(chat_id),
        )
        return
    send(
        chat_id,
        "📚 Muhajeer Books ilovasida kitoblarni tanlang va buyurtma bering.\n\n"
        f"📲 Ilovani yuklab olish: {APP_DOWNLOAD_URL}",
        main_menu(chat_id),
    )


def global_discount_active():
    return any("global_discount_base_price" in book for book in books)


def admin_menu():
    # Ixcham ikki ustunli admin menyu. Avtomatik/random sinov va
    # test-chek tugmalari olib tashlandi; ma'lumotlar saqlanadi.
    return {
        "keyboard": [
            [{"text": "🔎 Kitob qidirish"}],
            [{"text": "📚 Sotilgan kitoblar"}, {"text": "📷 Instagram savdo"}],
            [{"text": "📦 Buyurtmalar"}, {"text": "👥 Foydalanuvchilar"}],
            [{"text": "📢 Xabar yuborish"}, {"text": "💾 Backup"}],
            [{"text": "📥 Backup tiklash"}, {"text": "🏠 Asosiy menyu"}],
        ],
        "resize_keyboard": True
    }


def order_keyboard():
    return {
        "keyboard": [[{"text": "❌ Bekor qilish"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }


def admin_order_keyboard(order_id):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💳 To‘lov qilindi",
                    "callback_data": f"paid_{order_id}"
                }
            ],
            [
                {
                    "text": "❌ Bekor qilish",
                    "callback_data": f"cancelorder_{order_id}"
                }
            ]
        ]
    }


def catalog_intro_text(page=0):
    available = sum(
        1 for b in books
        if int(b.get("stock", 0)) > 0 and effective_price(b) > 0
    )
    return (
        "📚 MUHAJEER BOOKS KATALOGI\n"
        "━━━━━━━━━━━━━━\n"
        f"✅ Sotuvda: {available} xil kitob\n"
        f"📖 Jami katalogda: {len(books)} xil\n\n"
        "Kitobni tanlang — narxi, muqovasi va batafsil ma’lumotini ko‘rasiz 👇"
    )


def catalog_book_label(book):
    stock = int(book.get("stock", 0))
    price = effective_price(book)
    if stock > 0 and price > 0:
        flame = "🔥 " if book.get("recommended") else ""
        return f"{flame}📗 {book['name']} · ₩{price:,}", f"book_{book['id']}"
    return f"▫️ {book['name']} · Mavjud emas", f"none_{book['id']}"


def books_menu(page=0):
    refresh_books()

    # Sotuvdagi kitoblar tepada, mavjud bo‘lmaganlari esa pastda ko‘rinadi.
    ordered_books = sorted(
        books,
        key=lambda b: (
            not (int(b.get("stock", 0)) > 0 and effective_price(b) > 0),
            str(b.get("name", "")).casefold()
        )
    )

    per_page = 7
    total_pages = max(1, (len(ordered_books) + per_page - 1) // per_page)

    try:
        page = int(page)
    except Exception:
        page = 0

    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    page_books = ordered_books[start:start + per_page]

    buttons = []
    for book in page_books:
        label, callback = catalog_book_label(book)
        buttons.append([{"text": label, "callback_data": callback}])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append({"text": "⬅️ Oldingi", "callback_data": f"books_page_{page - 1}"})
        nav.append({"text": f"📄 {page + 1} / {total_pages}", "callback_data": "cart_noop"})
        if page < total_pages - 1:
            nav.append({"text": "Keyingi ➡️", "callback_data": f"books_page_{page + 1}"})
        buttons.append(nav)

    buttons.append([
        {"text": "📂 Kategoriyalar", "callback_data": "categories"},
        {"text": "❤️ Sevimlilar", "callback_data": "favorites"}
    ])
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])

    return {"inline_keyboard": buttons}


# =========================
# SAVATCHA
# =========================
# SAVATCHA
# =========================


def recommended_books_keyboard():
    items = [b for b in books if b.get("recommended") and int(b.get("stock", 0)) > 0 and int(b.get("price", 0)) > 0]
    buttons = [[{"text": f"🔥 {b['name']} — ₩{effective_price(b):,}", "callback_data": f"book_{b['id']}"}] for b in items]
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}


def new_books_keyboard():
    def key(b):
        raw = b.get("created_at", "")
        try:
            return _local_datetime(raw)
        except Exception:
            return datetime.min
    items = sorted(books, key=key, reverse=True)[:10]
    buttons = []
    for b in items:
        p = effective_price(b)
        icon = "🆕" if int(b.get("stock", 0)) > 0 and p > 0 else "❌"
        buttons.append([{"text": f"{icon} {b['name']} — ₩{p:,}" if p else f"{icon} {b['name']}",
                         "callback_data": f"book_{b['id']}" if icon == "🆕" else f"none_{b['id']}"}])
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}





def cart_quantity(cart):
    return sum(max(0, int(qty)) for qty in cart.values())


def delivery_fee_for_cart(cart):
    # 4 ta yoki undan ko‘p kitob xarid qilinsa yetkazib berish bepul.
    return 0 if cart_quantity(cart) >= 4 else int(DELIVERY_FEE)


def delivery_text(fee):
    return "BEPUL 🎁" if int(fee) == 0 else f"₩{int(fee):,}"


def saved_customer_info(chat_id):
    profile = users.get(str(chat_id), {})
    name = str(profile.get("saved_name", "") or "").strip()
    phone = str(profile.get("saved_phone", "") or "").strip()
    address = str(profile.get("saved_address", "") or "").strip()
    if name and phone and address and valid_phone_number(phone):
        return {"name": name, "phone": phone, "address": address}
    return None


def cart_text(chat_id):
    cart = carts.get(chat_id, {})
    if not cart:
        return "🛒 SAVATCHA\n\nHozircha savatchangiz bo‘sh."

    lines = []
    total = 0
    for book_id, qty in cart.items():
        book = find_book(book_id)
        if not book:
            continue
        subtotal = effective_price(book) * int(qty)
        total += subtotal
        lines.append(f"📖 {book['name']} × {qty} — ₩{subtotal:,}")

    fee = delivery_fee_for_cart(cart)
    grand_total = total + fee
    delivery_note = (
        "🎁 4+ kitob: yetkazib berish BEPUL!"
        if fee == 0
        else "🎁 4 ta yoki ko‘proq kitob olsangiz, yetkazib berish bepul."
    )

    return (
        "🛒 SAVATCHA\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Kitoblar: ₩{total:,}"
        + f"\n🚚 Yetkazish: {delivery_text(fee)}"
        + "\n⏱ Yetkazish muddati: 1–3 ish kuni"
        + f"\n💳 JAMI: ₩{grand_total:,}"
        + f"\n\n{delivery_note}"
    )


def cart_keyboard(chat_id):
    cart = carts.get(chat_id, {})

    if not cart:
        return {
            "inline_keyboard": [
                [{"text": "➕ Kitob qo‘shish", "callback_data": "books"}],
                [{"text": "🏠 Bosh menyu", "callback_data": "home"}]
            ]
        }

    buttons = []
    for book_id, qty in list(cart.items()):
        book = find_book(book_id)
        if not book:
            continue

        # 1 dona paytida ➖ bosilsa kitob savatdan butunlay chiqadi.
        buttons.append([
            {"text": "➖", "callback_data": f"cartminus_{book_id}"},
            {"text": f"{book['name']} · {qty} ta", "callback_data": "cart_noop"},
            {"text": "➕", "callback_data": f"cartplus_{book_id}"},
        ])

    buttons.append([
        {"text": "➕ Yana kitob qo‘shish", "callback_data": "books"}
    ])
    buttons.append([
        {"text": "✅ BUYURTMA BERISH", "callback_data": "cart_order"}
    ])
    buttons.append([
        {"text": "🗑 Tozalash", "callback_data": "cartclear"},
        {"text": "🏠 Bosh menyu", "callback_data": "home"}
    ])

    return {"inline_keyboard": buttons}


# =========================
# ADMIN KITOBLAR
# =========================

def admin_books_text():
    refresh_books()
    if not books:
        return "📚 Hozircha kitob yo‘q."

    lines = ["📚 Kitoblar:"]

    for b in books:
        lines.append(
            f"\n#{b['id']} {b['name']}\n"
            f"{price_text(b)}\n"
            f"📦 Qoldiq: {int(b['stock'])} ta"
        )

    return "\n".join(lines)


ADMIN_PAGE_SIZE = 12


def _admin_page(items, page=0, size=ADMIN_PAGE_SIZE):
    total = max(1, (len(items) + size - 1) // size)
    try:
        page = int(page)
    except Exception:
        page = 0
    page = max(0, min(page, total - 1))
    start = page * size
    return items[start:start + size], page, total


def _page_nav(prefix, page, total):
    if total <= 1:
        return []
    row = []
    if page > 0:
        row.append({"text": "⬅️", "callback_data": f"{prefix}_{page - 1}"})
    row.append({"text": f"📄 {page + 1}/{total}", "callback_data": "page_noop"})
    if page + 1 < total:
        row.append({"text": "➡️", "callback_data": f"{prefix}_{page + 1}"})
    return [row]

def edit_book_menu(page=0):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"✏️ {b['name']}",
        "callback_data": f"edit_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("editpage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}

def delete_book_menu(page=0):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"🗑 {b['name']}",
        "callback_data": f"delete_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("deletepage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}

def edit_fields_menu(book_id):
    return {
        "inline_keyboard": [
            [{"text": "✏️ Nomini o‘zgartirish", "callback_data": f"ename_{book_id}"}],
            [{"text": "💰 Narxini o‘zgartirish", "callback_data": f"eprice_{book_id}"}],
            [{"text": "💵 Tannarxni o‘zgartirish", "callback_data": f"ecost_{book_id}"}],
            [{"text": "📦 Qoldig‘ini o‘zgartirish", "callback_data": f"estock_{book_id}"}],
            [{"text": "📂 Kategoriyani o‘zgartirish", "callback_data": f"ecat_{book_id}"}],
            [{"text": "📕 Muqovani o‘zgartirish", "callback_data": f"ecover_{book_id}"}],
            [{"text": "✍️ Muallifni o‘zgartirish", "callback_data": f"eauthor_{book_id}"}],
            [{"text": "📄 Tavsifni o‘zgartirish", "callback_data": f"edesc_{book_id}"}],
            [{"text": "📸 Rasmni o‘zgartirish", "callback_data": f"ephoto_{book_id}"}],
            [{"text": "🛠 Hammasini tahrirlash", "callback_data": f"eall_{book_id}"}],
            [{"text": "🔥 Tavsiya etilgan ON/OFF", "callback_data": f"erec_{book_id}"}],
            [{"text": "⬅️ Orqaga", "callback_data": "editlist"}],
        ]
    }


def low_stock_admin_text():
    refresh_books(); low=sorted([b for b in books if 0<int(b.get("stock",0))<=LOW_STOCK_LIMIT],key=lambda b:int(b.get("stock",0))); empty=sorted([b for b in books if int(b.get("stock",0))<=0],key=lambda b:str(b.get("name","")).casefold())
    lines=["⚠️ KAM QOLGAN KITOBLAR",""] + ([f"• {b['name']} — {int(b.get('stock',0))} ta" for b in low] or ["Kam qolgan kitob yo‘q."]) + ["","❌ TUGAGAN KITOBLAR",""] + ([f"• {b['name']} — 0 ta" for b in empty] or ["Tugagan kitob yo‘q."])
    return "\n".join(lines)

def low_stock_admin_keyboard():
    refresh_books(); items=sorted([b for b in books if int(b.get("stock",0))<=LOW_STOCK_LIMIT],key=lambda b:(int(b.get("stock",0)),str(b.get("name","")).casefold()))
    buttons=[[{"text":f"📦 {b['name']} — {int(b.get('stock',0))} ta","callback_data":f"qstock_book_{b['id']}"}] for b in items[:40]]; buttons.append([{"text":"⬅️ Admin panel","callback_data":"admin"}]); return {"inline_keyboard":buttons}

def quick_stock_list_keyboard(chat_id=None, page=None):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    state = states.get(chat_id, {}) if chat_id is not None else {}
    draft = state.get("stock_draft", {}) if isinstance(state, dict) else {}
    if page is None:
        page = state.get("stock_page", 0) if isinstance(state, dict) else 0
    current, page, total = _admin_page(items, page, 8)
    if isinstance(state, dict):
        state["stock_page"] = page

    buttons = []
    for b in current:
        bid = int(b["id"])
        value = int(draft.get(str(bid), b.get("stock", 0)))
        buttons.append([{
            "text": f"📦 {b['name']} — {value} ta",
            "callback_data": f"qstock_book_{bid}"
        }])
        buttons.append([
            {"text": "➖1", "callback_data": f"qstock_batch_{bid}_-1"},
            {"text": f"{value} ta", "callback_data": "qstock_noop"},
            {"text": "➕1", "callback_data": f"qstock_batch_{bid}_1"},
        ])
    buttons.extend(_page_nav("qstock_page", page, total))
    buttons.append([{"text": "✅ OK — Saqlash", "callback_data": "qstock_save"}])
    buttons.append([{"text": "❌ Bekor qilish", "callback_data": "qstock_cancel"}])
    return {"inline_keyboard": buttons}

def quick_stock_adjust_keyboard(book_id):
    return {"inline_keyboard":[[{"text":"➖5","callback_data":f"qstock_adj_{book_id}_-5"},{"text":"➖1","callback_data":f"qstock_adj_{book_id}_-1"}],[{"text":"➕1","callback_data":f"qstock_adj_{book_id}_1"},{"text":"➕5","callback_data":f"qstock_adj_{book_id}_5"}],[{"text":"✏️ Aniq son yozish","callback_data":f"qstock_set_{book_id}"}],[{"text":"⬅️ Kitoblar","callback_data":"qstock_list"}]]}

def order_cost_summary(order):
    total_cost=0; missing_qty=0; items=order.get("items")
    if isinstance(items,list) and items:
        for item in items:
            qty=int(item.get("qty",0) or 0)
            try:
                unit_cost=int(item.get("unit_cost") or 0)
            except Exception:
                unit_cost=0
            # Buyurtma vaqtida tannarx 0 bo'lgan bo'lsa, keyinchalik kitobga
            # tannarx kiritilganda tarixiy hisobot ham avtomatik aniqlashadi.
            if unit_cost <= 0:
                b=find_book(item.get("book_id"))
                current_cost=int(b.get("cost_price",0) or 0) if b else 0
                if current_cost > 0:
                    unit_cost=current_cost
            total_cost += unit_cost*qty
            missing_qty += qty if unit_cost<=0 else 0
        return total_cost,missing_qty
    for bid,qty in order.get("cart",{}).items():
        qty=int(qty); b=find_book(bid); unit_cost=int(b.get("cost_price",0) or 0) if b else 0; total_cost += unit_cost*qty; missing_qty += qty if unit_cost<=0 else 0
    return total_cost,missing_qty

def _order_report_total(order):
    if str(order.get("source", "")) == "instagram":
        received = int(order.get("instagram_received_total", 0) or 0)
        if received > 0:
            return received
    return int(order.get("grand_total", 0) or 0)


def _order_report_delivery(order):
    if str(order.get("source", "")) == "instagram":
        received = int(order.get("instagram_received_total", 0) or 0)
        if received > 0:
            return int(DELIVERY_FEE) if str(order.get("postage_paid_by", "")) == "customer" else 0
    return int(order.get("delivery_fee", DELIVERY_FEE) or 0)


def _order_report_books(order):
    if str(order.get("source", "")) == "instagram":
        received = int(order.get("instagram_received_total", 0) or 0)
        if received > 0:
            return max(0, received - _order_report_delivery(order))
    return int(order.get("total", 0) or 0)


def daily_admin_report_text():
    try:
        r = cloud_bridge.finance_report("today")
    except Exception as exc:
        return f"❌ Bugungi moliya hisoboti serverdan olinmadi: {exc}"

    def n(key):
        try:
            return int(float(r.get(key, 0) or 0))
        except Exception:
            return 0

    net = n("net_profit")
    margin = float(r.get("margin_percent", 0) or 0)
    return "\n".join([
        "📅 BUGUNGI HISOBOT",
        "",
        f"📦 Jo‘natilgan buyurtma: {n('shipped_orders')} ta",
        f"📚 Sotilgan kitoblar: {n('sold_books')} dona",
        "",
        f"💰 Jami tushum: ₩{n('total_revenue'):,}",
        f"📖 Hisobga kiradigan kitob savdosi: ₩{n('books_revenue'):,}",
        f"🚚 Mijozlardan yetkazish puli: ₩{n('delivery_revenue'):,}",
        f"💵 Kitob tannarxi: ₩{n('cost_of_goods'):,}",
        f"📚 Kitobdan qolgan foyda: ₩{n('book_profit'):,}",
        f"📦 Yangi partiya kitoblar: ₩{n('inventory_purchases'):,}",
        f"📮 Do‘kon hisobidan pochta: ₩{n('store_postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        "━━━━━━━━━━━━━━",
        f"{'✅ BUGUNGI SOF FOYDA' if net >= 0 else '🔻 BUGUNGI SOF ZARAR'}: {'-' if net < 0 else ''}₩{abs(net):,}",
        f"📈 Marja: {margin:.1f}%",
        "━━━━━━━━━━━━━━",
        "ℹ️ Natija = kitob savdosi − yangi partiya − do‘kon hisobidan pochta − boshqa chiqimlar.",
    ])


# =========================
# BUYURTMA HISOBI
# =========================

def calculate_cart(chat_id):
    cart=carts.get(chat_id,{})
    lines=[]; total=0
    for book_id,qty in cart.items():
        book=find_book(book_id)
        if not book: continue
        subtotal=effective_price(book)*int(qty); total+=subtotal
        lines.append(f"📖 {book['name']} × {qty} = ₩{subtotal:,}")
    return lines,total



def order_preview_text(state, show_payment_info=True):
    lines = []
    total = 0
    payment_declared = bool(state.get("payment_declared", False))
    saved_items = state.get("payment_items") if payment_declared else None

    if isinstance(saved_items, list) and saved_items:
        for item in saved_items:
            name = str(item.get("name", "Kitob"))
            qty = int(item.get("qty", 0))
            unit_price = int(item.get("unit_price", 0))
            subtotal = unit_price * qty
            total += subtotal
            lines.append(f"📖 {name} × {qty} = ₩{subtotal:,}")
    else:
        for book_id, qty in state.get("cart", {}).items():
            book = find_book(book_id)
            if not book:
                continue
            subtotal = effective_price(book) * int(qty)
            total += subtotal
            lines.append(f"📖 {book['name']} × {qty} = ₩{subtotal:,}")

    fee = delivery_fee_for_cart(state.get("cart", {}))
    grand_total = total + fee
    # Chek yuborilgach buyurtma yakuniy tekshiruvda bo‘ladi:
    # bu bosqichda aksiya reklamasini qayta ko‘rsatmaymiz.
    if payment_declared:
        free_note = ""
    elif fee == 0:
        free_note = "\n🎁 Aksiya qo‘llandi: 4 ta yoki undan ko‘p kitob — yetkazib berish bepul!"
    else:
        free_note = "\nℹ️ 4 ta yoki undan ko‘p kitob xarid qilsangiz, yetkazib berish bepul."
    text = (
        "🧾 BUYURTMANGIZ\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Kitoblar: ₩{total:,}"
        + f"\n🚚 Yetkazib berish: {delivery_text(fee)}"
        + "\n⏱ Yetkazish muddati: 1–3 ish kuni"
        + free_note
        + f"\n\n━━━━━━━━━━━━━━\n💵 JAMI TO‘LOV: ₩{grand_total:,}\n━━━━━━━━━━━━━━"
    )

    if show_payment_info:
        text += (
            "\n\n💳 TO‘LOV MA‘LUMOTLARI\n"
            f"💳 Karta raqami: {CARD_NUMBER}\n"
            f"🏦 {BANK_NAME}\n"
            f"👤 {CARD_OWNER}\n\n"
            "⚠️ Jami summani yuqoridagi karta raqamiga o‘tkazing.\n"
            "So‘ng «📸 To‘lov chekini yuborish» tugmasini bosing."
        )
    return text, total, grand_total



# =========================
# MIJOZLAR / QIDIRUV / HISOBOT
# =========================
# MIJOZLAR / QIDIRUV / HISOBOT
# =========================

def valid_phone_number(value):
    """Telefon raqamida 8–15 ta raqam bo‘lishini tekshiradi."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return 8 <= len(digits) <= 15


def register_user(chat_id, user):
    key = str(chat_id)
    now = int(time.time())
    old = users.get(key, {})
    profile = dict(old) if isinstance(old, dict) else {}

    # Telegram ma’lumotlarini yangilaymiz, buyurtmadan saqlangan ism,
    # telefon va manzil kabi boshqa maydonlarni esa yo‘qotmaymiz.
    profile.update({
        "chat_id": chat_id,
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "last_active": now,
        "last_bot_active": now,
        "inactive_message_sent": False
    })
    users[key] = profile
    save_users()


def register_mini_app_user(chat_id, user):
    """Verified Mini App visits are separate from bot message activity."""
    key = str(chat_id)
    old = users.get(key, {})
    profile = dict(old) if isinstance(old, dict) else {}
    profile.update({
        "chat_id": chat_id,
        "first_name": user.get("first_name", profile.get("first_name", "")),
        "last_name": user.get("last_name", profile.get("last_name", "")),
        "username": user.get("username", profile.get("username", "")),
        "last_mini_app_active": int(time.time()),
    })
    users[key] = profile
    save_users()


def format_user_activity(value):
    try:
        timestamp = int(value)
        if timestamp <= 0:
            raise ValueError
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(
            ZoneInfo("Asia/Seoul")
        ).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OverflowError):
        return "hali kirmagan"


def admin_users_texts():
    # Telegram bitta xabarda 4096 belgidan oshirmaydi, shuning uchun ro‘yxat
    # katta bo‘lsa uni bir nechta xabarga bo‘lib yuboramiz.
    load_users()
    people = sorted(users.items(), key=lambda item: max(
        int(item[1].get("last_bot_active") or item[1].get("last_active") or 0),
        int(item[1].get("last_mini_app_active") or 0),
    ), reverse=True)

    header = (
        "👥 BOT FOYDALANUVCHILARI\n\n"
        f"Jami foydalanuvchilar: {len(people)} ta\n"
    )
    if not people:
        return [header + "\nHozircha foydalanuvchi yo‘q."]

    chunks = []
    current = header
    for number, (user_id, profile) in enumerate(people, 1):
        full_name = " ".join(
            part for part in [
                str(profile.get("first_name", "") or "").strip(),
                str(profile.get("last_name", "") or "").strip()
            ]
            if part
        ) or "Noma’lum"
        username = str(profile.get("username", "") or "").strip().lstrip("@")
        username_text = f"@{username}" if username else "username yo‘q"
        telegram_id = profile.get("chat_id", user_id)
        bot_active = format_user_activity(profile.get("last_bot_active") or profile.get("last_active"))
        mini_active = format_user_activity(profile.get("last_mini_app_active"))
        entry = (
            f"\n{number}. 👤 {full_name}\n"
            f"   🔗 {username_text}\n"
            f"   🆔 {telegram_id}\n"
            f"   🤖 Bot: {bot_active} (Koreya)\n"
            f"   🛍 Mini App: {mini_active} (Koreya)\n"
        )

        if len(current) + len(entry) > 3800:
            chunks.append(current)
            current = "👥 DAVOMI\n" + entry
        else:
            current += entry

    if current:
        chunks.append(current)
    return chunks


def search_books(query):
    refresh_books()
    q = _search_key(query)
    if not q:
        return []

    ranked = []
    threshold = _fuzzy_threshold(q)

    for b in books:
        name = _search_key(b.get("name", ""))
        author = _search_key(b.get("author", ""))
        category = _search_key(b.get("category", ""))

        # Exact/partial results always rank first.
        exact_score = 0.0
        for field in (name, author, category):
            if not field:
                continue
            if q == field:
                exact_score = max(exact_score, 1.0)
            elif len(q) >= 2 and q in field:
                exact_score = max(exact_score, 0.97)

        fuzzy_score = max(
            _fuzzy_ratio(q, name),
            _fuzzy_ratio(q, author) if author else 0.0,
        )
        score = max(exact_score, fuzzy_score)

        if exact_score > 0 or score >= threshold:
            ranked.append((score, b))

    ranked.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("name", "")).casefold()
        )
    )
    return [b for _, b in ranked[:30]]



def search_books_keyboard(items):
    buttons = []
    for b in items:
        stock = int(b.get("stock", 0))
        price = int(effective_price(b))
        if stock > 0 and price > 0:
            buttons.append([{
                "text": f"📖 {b['name']} — ₩{price:,} ({stock} ta)",
                "callback_data": f"book_{b['id']}"
            }])
        else:
            buttons.append([{
                "text": f"❌ {b['name']} — mavjud emas",
                "callback_data": f"none_{b['id']}"
            }])
    buttons.append([{
        "text": "🏠 Bosh menyu", "callback_data": "home"
    }])
    return {"inline_keyboard": buttons}


def user_orders_text(chat_id):
    mine = [o for o in orders.values() if int(o.get("chat_id", -1)) == int(chat_id)]
    if not mine:
        return "📜 Sizda hali buyurtmalar yo‘q."

    mine.sort(key=lambda o: int(o.get("order_id", 0)), reverse=True)
    lines = ["📜 BUYURTMALARIM\n"]
    status_names = {
        "pending": "🟡 To‘lov kutilmoqda",
        "accepted": "📦 Buyurtma qabul qilingan",
        "paid": "🟢 To‘lov tasdiqlangan",
        "shipped": "🚚 Jo‘natildi",
        "delivered": "🚚 Jo‘natildi",
        "cancelled": "❌ Bekor qilingan",
        "stock_problem": "⚠️ Ombor muammosi"
    }
    for o in mine[:20]:
        status = status_names.get(o.get("status"), o.get("status", "noma’lum"))
        number = display_order_number(o)
        number_prefix = f"🔢 №{number} — " if number else ""
        lines.append(
            f"{number_prefix}{status}\n"
            f"💵 ₩{int(o.get('grand_total', 0)):,}"
        )
    return "\n\n".join(lines)


def user_orders_keyboard(chat_id):
    mine = [o for o in orders.values() if int(o.get("chat_id", -1)) == int(chat_id)]
    buttons = []
    for o in sorted(mine, key=lambda x: int(x.get("order_id", 0)), reverse=True)[:20]:
        if o.get("status") == "shipped":
            for bid, qty in o.get("cart", {}).items():
                b = find_book(bid)
                if b and not user_has_rated(chat_id, o.get("order_id"), bid):
                    buttons.append([{
                        "text": f"⭐ {b['name']}ni baholash",
                        "callback_data": f"ratebook_{o.get('order_id')}_{bid}"
                    }])
    buttons.append([{"text": "🔎 Buyurtma raqami bilan tekshirish", "callback_data": "order_lookup"}])
    buttons.append([{"text": "🏠 Bosh menyu", "callback_data": "home"}])
    return {"inline_keyboard": buttons}


def rating_keyboard(order_id, book_id):
    return {"inline_keyboard": [
        [{"text": "⭐1", "callback_data": f"rate_{order_id}_{book_id}_1"},
         {"text": "⭐2", "callback_data": f"rate_{order_id}_{book_id}_2"},
         {"text": "⭐3", "callback_data": f"rate_{order_id}_{book_id}_3"},
         {"text": "⭐4", "callback_data": f"rate_{order_id}_{book_id}_4"},
         {"text": "⭐5", "callback_data": f"rate_{order_id}_{book_id}_5"}],
        [{"text": "📜 Buyurtmalarim", "callback_data": "myorders"}]
    ]}


ORDER_STATUS_NAMES = {
    "pending": "🟡 Kutilmoqda", "accepted": "📦 Qabul qilingan", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "🚚 Jo‘natilgan",
    "cancelled": "❌ Bekor qilingan", "stock_problem": "⚠️ Ombor muammosi"
}

def admin_order_counts():
    # Bekor qilingan zakazlar admin Buyurtmalar papkasida umuman ko‘rinmaydi.
    visible = [o for o in orders.values() if o.get("status") != "cancelled"]
    return {status: sum(1 for o in visible if o.get("status") == status) for status in ORDER_STATUS_NAMES}

def admin_orders_text(status_filter="all"):
    if not orders:
        return "📦 Hozircha buyurtmalar yo‘q."
    selected = [o for o in orders.values() if o.get("status") != "cancelled" and (status_filter == "all" or o.get("status") == status_filter)]
    selected.sort(key=lambda x: int(x.get("order_id", 0)), reverse=True)
    title = "📦 BARCHA BUYURTMALAR" if status_filter == "all" else f"📦 {ORDER_STATUS_NAMES.get(status_filter, status_filter).upper()}"
    lines = [f"{title} — {len(selected)} ta", ""]
    for o in selected[:30]:
        lines.append(f"№{display_order_number(o)} | {o.get('name', 'Noma’lum')} | ₩{int(o.get('grand_total', 0)):,} | {ORDER_STATUS_NAMES.get(o.get('status'), o.get('status'))}")
    if not selected:
        lines.append("Bu statusda buyurtma yo‘q.")
    return "\n".join(lines)


def admin_report_keyboard():
    return {"inline_keyboard": [
        [{"text":"📅 Bugun", "callback_data":"report_today"}, {"text":"📆 Shu hafta", "callback_data":"report_week"}],
        [{"text":"🗓 Shu oy", "callback_data":"report_month"}, {"text":"📊 Hammasi", "callback_data":"report_all"}],
        [{"text":"⬅️ Admin panel", "callback_data":"admin"}]
    ]}

def admin_report_text(period="all"):
    load_users()
    now = datetime.now()

    def included(o):
        if period == "all":
            return True
        raw = o.get("created_at", "")
        try:
            dt = _local_datetime(raw)
        except Exception:
            return False
        if period == "today":
            return dt.date() == now.date()
        if period == "week":
            return dt >= now - timedelta(days=7)
        if period == "month":
            return dt.year == now.year and dt.month == now.month
        return True

    selected = [o for o in orders.values() if included(o) and int(o.get("order_id", 0) or 0) >= STATS_RESET_ORDER_ID]
    paid_statuses = ("accepted", "paid", "shipped")
    successful = [o for o in selected if o.get("status") in paid_statuses]

    pending = sum(1 for o in selected if o.get("status") == "pending")
    paid = sum(1 for o in selected if o.get("status") == "paid")
    shipped = sum(1 for o in selected if o.get("status") == "shipped")
    delivered = sum(1 for o in selected if o.get("status") == "delivered")
    cancelled = sum(1 for o in selected if o.get("status") == "cancelled")
    # Moliyaviy raqamlar web/APK bilan aynan bir xil markaziy hisobotdan olinadi.
    # Local buyurtmalar faqat TOP kitob/mijoz va status statistikasiga xizmat qiladi.
    try:
        cloud_finance = cloud_bridge.finance_report(period)
    except Exception as exc:
        print("Statistika moliya cloud xatosi:", exc)
        cloud_finance = {}

    def finance_n(key, default=0):
        try:
            return int(float(cloud_finance.get(key, default) or 0))
        except Exception:
            return int(default or 0)

    if cloud_finance:
        revenue = finance_n("total_revenue")
        books_revenue = finance_n("books_revenue")
        delivery_revenue = finance_n("delivery_revenue")
        cost_of_goods = finance_n("cost_of_goods")
        book_profit = finance_n("book_profit")
        inventory_purchases = finance_n("inventory_purchases")
        postage_expense = finance_n("postage_expense")
        store_postage_expense = finance_n("store_postage_expense")
        other_expenses = finance_n("other_expenses")
        cash_outflow_total = finance_n("cash_outflow_total")
        net_profit = finance_n("net_profit")
        missing_cost_qty = 0
    else:
        # Server bo‘lmasa eski local raqamni "sof foyda" deb ko‘rsatmaymiz.
        revenue = sum(_order_report_total(o) for o in successful)
        books_revenue = sum(_order_report_books(o) for o in successful)
        delivery_revenue = sum(_order_report_delivery(o) for o in successful)
        cost_of_goods = 0
        missing_cost_qty = 0
        for o in successful:
            order_cost, missing_qty = order_cost_summary(o)
            cost_of_goods += order_cost
            missing_cost_qty += missing_qty
        book_profit = books_revenue - cost_of_goods
        inventory_purchases = 0
        postage_expense = len(successful) * int(DELIVERY_FEE)
        store_postage_expense = max(0, postage_expense - delivery_revenue)
        other_expenses = 0
        cash_outflow_total = store_postage_expense
        net_profit = books_revenue - cash_outflow_total

    avg_order = revenue / len(successful) if successful else 0
    free_delivery_orders = [
        o for o in successful
        if _order_report_delivery(o) == 0
    ]
    free_delivery_cost = len(free_delivery_orders) * int(DELIVERY_FEE)

    sold = {}
    category_sales = {}
    customer_totals = {}
    customer_order_counts = {}
    for o in successful:
        if o.get("source") != "instagram":
            cid = str(o.get("chat_id"))
            customer_totals[cid] = customer_totals.get(cid, 0) + int(o.get("grand_total", 0))
            customer_order_counts[cid] = customer_order_counts.get(cid, 0) + 1
        for bid, qty in o.get("cart", {}).items():
            qty = int(qty)
            sold[int(bid)] = sold.get(int(bid), 0) + qty
            b = find_book(bid)
            category = normalize_category(b.get("category")) if b else "Boshqalar"
            category_sales[category] = category_sales.get(category, 0) + qty

    top = sorted(sold.items(), key=lambda x: x[1], reverse=True)[:10]
    top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    if category_sales:
        top_category_name, top_category_qty = max(category_sales.items(), key=lambda x: x[1])
    else:
        top_category_name, top_category_qty = "Hali sotuv yo‘q", 0

    repeat_customers = sum(1 for count in customer_order_counts.values() if count >= 2)
    unique_customers = len(customer_order_counts)
    repeat_pct = (repeat_customers / unique_customers * 100) if unique_customers else 0

    all_successful_after_reset = [
        o for o in orders.values()
        if int(o.get("order_id", 0) or 0) >= STATS_RESET_ORDER_ID
        and o.get("status") in paid_statuses
        and o.get("source") != "instagram"
    ]
    first_order_by_customer = {}
    for o in all_successful_after_reset:
        cid = str(o.get("chat_id"))
        oid = int(o.get("order_id", 0) or 0)
        if cid not in first_order_by_customer or oid < first_order_by_customer[cid]:
            first_order_by_customer[cid] = oid

    selected_success_ids = {int(o.get("order_id", 0) or 0) for o in successful}
    new_customers = sum(
        1 for oid in first_order_by_customer.values()
        if oid in selected_success_ids
    )

    label = {"all":"Barcha vaqt", "today":"Bugun", "week":"Oxirgi 7 kun", "month":"Shu oy"}.get(period, "Barcha vaqt")
    lines = [
        f"📊 KUCHLI SAVDO STATISTIKASI — {label}", "",
        f"👥 Bot foydalanuvchilari: {len(us…14781 tokens truncated…\n\n"
                "❌ Bekor qilish uchun tugmani bosing.",
                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
            return

        if text in ("🛑 Chegirmani to‘xtatish", "❌ Chegirmani bekor qilish"):
            try:
                changed = remove_global_discount()
                if changed:
                    send(chat_id, f"✅ Chegirma bekor qilindi. {changed} ta kitob avvalgi narxiga qaytarildi.", admin_menu())
                else:
                    send(chat_id, "ℹ️ Hozir global chegirma yo‘q.", admin_menu())
            except Exception as e:
                send(chat_id, f"❌ Chegirmani bekor qilib bo‘lmadi: {e}", admin_menu())
            return

        if text == "➕ Kitob qo‘shish":
            states[chat_id] = {"action": "add_name"}
            send(
                chat_id,
                "➕ Yangi kitob nomini yozing:"
            )
            return

        if text == "✏️ Kitob tahrirlash":
            states.pop(chat_id, None)
            send(
                chat_id,
                "Tahrir qilinadigan kitobni tanlang:",
                edit_book_menu()
            )
            return

        if text == "🗑 Kitob o‘chirish":
            states.pop(chat_id, None)
            send(
                chat_id,
                "O‘chiriladigan kitobni tanlang:",
                delete_book_menu()
            )
            return

        if text == "❌ Bekor qilish" and state:
            states.pop(chat_id, None)
            send(
                chat_id,
                "Bekor qilindi.",
                admin_menu()
            )
            return

        if state:
            action = state.get("action")

            if action == "shipping_smart_input":
                photos = message.get("photo") or []
                caption = str(message.get("caption") or "").strip()
                raw = text
                photo_id = ""
                if photos:
                    photo_id = str(photos[-1].get("file_id") or "")
                    try:
                        ocr_text = _shipping_ocr_photo(photo_id)
                    except Exception as exc:
                        print("Zakas OCR xatosi:", exc)
                        ocr_text = ""
                    raw = "\n".join(x for x in (ocr_text, caption) if x).strip()
                    state["address_photo_file_id"] = photo_id
                if not raw:
                    send(chat_id, "❌ Matnni o‘qiy olmadim. Xabarni matn ko‘rinishida yuboring yoki tiniqroq screenshot yuboring.")
                    return
                parsed = parse_smart_shipping_text(raw)
                for key in ("name", "phone", "address", "books", "raw_text"):
                    if key == "books" and state.get("lock_books"):
                        continue
                    if parsed.get(key):
                        state[key] = parsed[key]
                _smart_shipping_ask_next(chat_id, state)
                return

            if action == "shipping_smart_missing_name":
                if not text:
                    send(chat_id, "❌ Ismni yozing.")
                    return
                state["name"] = text.strip()
                _smart_shipping_ask_next(chat_id, state)
                return

            if action == "shipping_smart_missing_phone":
                phone = _shipping_phone_from_text(text)
                if not phone:
                    send(chat_id, "❌ Telefon raqamini to‘g‘ri yozing. Masalan: 01012345678")
                    return
                state["phone"] = phone
                _smart_shipping_ask_next(chat_id, state)
                return

            if action == "shipping_smart_missing_address":
                if not text:
                    send(chat_id, "❌ To‘liq manzilni yozing.")
                    return
                state["address"] = text.strip()
                _smart_shipping_ask_next(chat_id, state)
                return

            if action == "shipping_smart_missing_books":
                if not text:
                    send(chat_id, "❌ Kitob nomi va sonini yozing.")
                    return
                # Admin yozgan kitob nomini imkon qadar katalogdagi to‘liq nomga aylantiramiz.
                parsed_books = _shipping_extract_books([text], text)
                state["books"] = parsed_books or text.strip()
                _smart_shipping_ask_next(chat_id, state)
                return

            if action == "shipping_smart_confirm":
                send(chat_id, smart_shipping_preview(state), smart_shipping_confirm_keyboard())
                return

            if action == "instagram_shipping_offer":
                if text == "Yo‘q":
                    states.pop(chat_id, None)
                    send(
                        chat_id,
                        "✅ Instagram savdo saqlandi.\n\n📮 Pochta uchun manzil kiritilmadi.",
                        admin_menu(),
                    )
                    return
                if text == "📮 Kiritaman":
                    state["action"] = "shipping_smart_input"
                    send(
                        chat_id,
                        "📮 Pochta uchun ma’lumot yuboring.\n\n"
                        "📸 Mijoz yuborgan screenshotni jo‘natishingiz mumkin.\n"
                        "Yoki qo‘lda bir xabarda quyidagicha yozing:\n\n"
                        "Ism Familiya\n"
                        "01012345678\n"
                        "To‘liq manzil, xona raqami\n\n"
                        "📚 Kitoblar avtomatik qo‘shiladi.",
                        {"remove_keyboard": True},
                    )
                    return
                send(chat_id, "📮 Pochta uchun manzil kiritasizmi?", instagram_shipping_offer_keyboard())
                return

            if action == "instagram_items":
                try:
                    cart, errors = parse_instagram_sale_items(text)
                except Exception as exc:
                    send(chat_id, f"❌ Ilova ombori bilan bog‘lanib bo‘lmadi: {exc}\nQayta urinib ko‘ring.")
                    return
                if errors:
                    send(
                        chat_id,
                        "❌ Ayrim kitoblarni aniqlay olmadim:\n\n" + "\n".join(errors) +
                        "\n\nQaytadan yozing. Masalan:\nDafina 1"
                    )
                    return

                shortages = []
                live_by_id = {str(b.get("id")): b for b in books}
                for bid, qty in cart.items():
                    b = live_by_id.get(str(bid))
                    if not b or int(b.get("stock", 0)) < int(qty):
                        shortages.append(
                            f"• {(b or {}).get('name','Kitob')} — kerak {qty}, omborda {int((b or {}).get('stock',0))} ta"
                        )
                if shortages:
                    send(chat_id, "❌ Omborda yetarli emas:\n\n" + "\n".join(shortages))
                    return

                state["cart"] = cart
                state["action"] = "instagram_amount"
                send(
                    chat_id,
                    "✅ Kitoblar topildi:\n\n" +
                    instagram_sale_items_text(cart) +
                    "\n\n💰 Mijozdan olgan JAMI summani yozing.\n"
                    "Pochta puli ham ichida bo‘lsa, qo‘shib yozing.\n"
                    "Masalan: 22000",
                    {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
                )
                return

            if action == "instagram_amount":
                try:
                    amount = int(text.replace("₩", "").replace(",", "").replace(".", "").replace(" ", ""))
                    if amount <= 0:
                        raise ValueError
                except ValueError:
                    send(chat_id, "❌ Jami summani son bilan yozing. Masalan: 22000")
                    return

                state["received_total"] = amount
                state["action"] = "instagram_postage"
                send(
                    chat_id,
                    f"💰 Mijozdan olindi: ₩{amount:,}\n\n🚚 Pochta pulini kim to‘ladi?",
                    instagram_postage_keyboard()
                )
                return

            if action == "instagram_postage":
                if text not in ("👤 Pochtani mijoz to‘ladi", "🎁 Pochtani men to‘ladim"):
                    send(chat_id, "Quyidagi 2 ta tugmadan birini tanlang.", instagram_postage_keyboard())
                    return

                customer_pays = text == "👤 Pochtani mijoz to‘ladi"
                state["customer_pays_postage"] = customer_pays
                received = int(state.get("received_total", 0) or 0)
                if customer_pays and received < int(DELIVERY_FEE):
                    send(chat_id, "❌ Jami summa ₩4,000 pochta pulidan kam. Summani qayta kiriting.")
                    state["action"] = "instagram_amount"
                    return

                fee = int(DELIVERY_FEE) if customer_pays else 0
                books_total = max(0, received - fee)
                state["books_total"] = books_total
                state["action"] = "instagram_confirm"
                postage_text = "Mijoz to‘ladi — ₩4,000" if customer_pays else "Siz to‘ladingiz — ₩4,000 xarajat"

                send(
                    chat_id,
                    "🧾 INSTAGRAM SAVDO — TEKSHIRING\n\n" +
                    instagram_sale_items_text(state.get("cart", {})) +
                    f"\n\n💵 Mijozdan jami: ₩{received:,}" +
                    f"\n🚚 Pochta: {postage_text}" +
                    f"\n📚 Kitob savdosi: ₩{books_total:,}" +
                    "\n\n✅ Saqlasangiz ombordan kitoblar ayriladi va savdo barcha statistikaga qo‘shiladi.",
                    instagram_confirm_keyboard()
                )
                return

            if action == "instagram_confirm":
                if text != "✅ Savdoni saqlash":
                    send(chat_id, "Saqlash uchun «✅ Savdoni saqlash»ni bosing.", instagram_confirm_keyboard())
                    return
                try:
                    order = save_instagram_sale(state)
                    fee = int(order.get("delivery_fee", 0))
                    state["instagram_cloud_order_id"] = str(order.get("cloud_order_id") or "").strip()
                    state["books"] = instagram_shipping_books_text(order.get("cart", {}))
                    state["lock_books"] = True
                    state["address_photo_file_id"] = ""
                    state.pop("name", None)
                    state.pop("phone", None)
                    state.pop("address", None)
                    state["action"] = "instagram_shipping_offer"
                    send(
                        chat_id,
                        f"✅ Instagram savdo saqlandi.\n\n"
                        f"🔢 №{display_order_number(order)}\n"
                        f"📚 {sum(int(q) for q in order.get('cart',{}).values())} ta kitob\n"
                        f"💵 Mijozdan jami: ₩{int(order.get('grand_total',0)):,}\n"
                        f"🚚 Pochta: {'mijoz to‘ladi' if fee else 'siz to‘ladingiz'}\n"
                        f"📖 Kitob savdosi: ₩{int(order.get('total',0)):,}\n\n"
                        "📦 Ombor yangilandi va savdo statistikaga qo‘shildi.\n\n"
                        "📮 Pochta uchun ism, telefon va manzilni ham kiritasizmi?",
                        instagram_shipping_offer_keyboard(),
                    )
                except Exception as e:
                    send(chat_id, f"❌ Savdo saqlanmadi: {e}\n\nHali ombordan ayrilmadi. Qayta urinib ko‘ring.", instagram_confirm_keyboard())
                return

            if action == "quick_stock_set":
                try:
                    value=int(text.replace(",","").replace(" ",""))
                    if value<0: raise ValueError
                except ValueError: send(chat_id,"❌ Qoldiq 0 yoki undan katta son bo‘lsin."); return
                refresh_books(); book=next((b for b in books if int(b.get("id",-1))==int(state.get("book_id",-1))),None)
                if not book: states.pop(chat_id,None); send(chat_id,"❌ Kitob topilmadi.",admin_menu()); return
                old_stock=int(book.get("stock",0)); book["stock"]=value; save_books()
                if old_stock<=0<value: notify_restock(book)
                states.pop(chat_id,None); send(chat_id,f"✅ {book['name']} — {value} ta",quick_stock_adjust_keyboard(book["id"])); return

            if action == "global_discount":
                try:
                    percent = int(text.replace("%", "").strip())
                    if percent < 1 or percent > 99:
                        raise ValueError
                except ValueError:
                    send(chat_id, "❌ Chegirma 1 dan 99 gacha bo‘lgan foiz bo‘lsin.\nMasalan: 20")
                    return

                try:
                    changed = apply_global_discount(percent)
                    states.pop(chat_id, None)
                    send(
                        chat_id,
                        f"✅ {changed} ta kitobga {percent}% chegirma qo‘yildi.\n\n"
                        "Mijozlarga narx eski narx → chegirmadagi narx ko‘rinishida chiqadi.",
                        admin_menu()
                    )
                except Exception as e:
                    send(chat_id, f"❌ Chegirma qo‘yilmadi: {e}", admin_menu())
                return

            if action == "admin_search":
                result = search_books(text)
                states.pop(chat_id, None)
                if not result:
                    send(chat_id, f"🔎 «{text}» bo‘yicha kitob topilmadi.", admin_menu())
                else:
                    buttons = []
                    for b in result[:30]:
                        buttons.append([{"text": f"✏️ #{b['id']} {b['name']}", "callback_data": f"edit_{b['id']}"}])
                    buttons.append([{ "text":"⬅️ Admin panel","callback_data":"admin" }])
                    send(chat_id, f"🔎 Topildi: {len(result)} ta", {"inline_keyboard":buttons})
                return

            if action == "broadcast":
                if text == "❌ Bekor qilish":
                    states.pop(chat_id, None)
                    send(chat_id, "Bekor qilindi.", admin_menu())
                    return

                message_id = message.get("message_id")
                if not message_id:
                    send(chat_id, "❌ Xabarni aniqlab bo‘lmadi.", admin_menu())
                    return

                sent = 0
                failed = 0
                for uid in list(users.keys()):
                    try:
                        result = api("copyMessage", {"chat_id": int(uid), "from_chat_id": chat_id, "message_id": int(message_id)})
                        if result.get("ok"):
                            sent += 1
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                        print("Broadcast xatosi:", uid, e)

                states.pop(chat_id, None)
                send(chat_id, f"📢 Xabar yuborildi.\n\n✅ Yuborildi: {sent}\n❌ Yetkazilmadi: {failed}", admin_menu())
                return

            if action in ("full_edit_name", "full_edit_price", "full_edit_stock", "full_edit_cover", "full_edit_category", "full_edit_author", "full_edit_description", "full_edit_photo"):
                book = find_book(state.get("book_id"))
                if not book:
                    states.pop(chat_id, None)
                    send(chat_id, "❌ Kitob topilmadi.", admin_menu())
                    return

                if action == "full_edit_name":
                    if not text.strip():
                        send(chat_id, "❌ Nom bo‘sh bo‘lmasin.")
                        return
                    book["name"] = text.strip()
                    state["action"] = "full_edit_price"
                    send(chat_id, f"💰 Yangi narxni yozing (₩).\nHozirgi: ₩{int(book.get('price', 0)):,}")
                    return

                if action == "full_edit_price":
                    try:
                        value = int(text.replace(",", "").replace(" ", ""))
                        if value <= 0:
                            raise ValueError
                    except ValueError:
                        send(chat_id, "❌ Narx musbat son bo‘lsin. Masalan: 25000")
                        return
                    book["price"] = value
                    state["action"] = "full_edit_stock"
                    send(chat_id, f"📦 Yangi qoldiq sonini yozing.\nHozirgi: {int(book.get('stock', 0))} ta")
                    return

                if action == "full_edit_stock":
                    try:
                        value = int(text.replace(",", "").replace(" ", ""))
                        if value < 0:
                            raise ValueError
                    except ValueError:
                        send(chat_id, "❌ Qoldiq 0 yoki undan katta son bo‘lsin.")
                        return
                    old_stock = int(book.get("stock", 0))
                    book["stock"] = value
                    if old_stock <= 0 < value:
                        notify_restock(book)
                    state["action"] = "full_edit_cover"
                    send(chat_id, f"📕 Muqova turini yozing: Qattiq / Yumshoq / Flexible\nO‘chirish uchun: —\nHozirgi: {book.get('cover', 'Ko‘rsatilmagan')}")
                    return

                if action == "full_edit_cover":
                    cover = normalize_cover(text)
                    if cover is None:
                        send(chat_id, "❌ Faqat Qattiq, Yumshoq yoki Flexible deb yozing. O‘chirish uchun: —")
                        return
                    book["cover"] = cover
                    state["action"] = "full_edit_category"
                    send(chat_id, f"📂 Yangi kategoriyani yozing.\nHozirgi: {book.get('category', 'Boshqalar')}")
                    return

                if action == "full_edit_category":
                    book["category"] = normalize_category(text)
                    state["action"] = "full_edit_author"
                    send(chat_id, f"✍️ Yangi muallifni yozing. Bilinmasa: —\nHozirgi: {book.get('author', 'Ko‘rsatilmagan')}")
                    return

                if action == "full_edit_author":
                    book["author"] = "Ko‘rsatilmagan" if text.strip() in ("-", "—") else text.strip()
                    state["action"] = "full_edit_description"
                    send(chat_id, f"📄 Yangi tavsifni yozing. Bo‘lmasa: —\n\nHozirgi: {book.get('description', 'Ma’lumot kiritilmagan.')}")
                    return

                if action == "full_edit_description":
                    book["description"] = "Ma’lumot kiritilmagan." if text.strip() in ("-", "—") else text.strip()
                    state["action"] = "full_edit_photo"
                    send(chat_id, "📸 Yangi rasmni yuboring.\nRasmni o‘chirish uchun: —\nHozirgi rasmni saqlash uchun: 0")
                    return

                photos = message.get("photo") or []
                if photos:
                    book["photo_id"] = photos[-1].get("file_id", "")
                elif text.strip() == "—":
                    book["photo_id"] = ""
                elif text.strip() == "0":
                    pass
                else:
                    send(chat_id, "📸 Rasm yuboring, o‘chirish uchun — yoki hozirgisini saqlash uchun 0 yozing.")
                    return

                save_books()
                load_books()
                states.pop(chat_id, None)
                refreshed = find_book(book.get("id")) or book
                send(chat_id, f"✅ {refreshed['name']} — barcha ma’lumotlar yangilandi.", edit_fields_menu(refreshed["id"]))
                return

            if action == "add_name":
                if not text:
                    send(chat_id, "❌ Kitob nomi bo‘sh bo‘lmasin.")
                    return

                state["name"] = text
                state["action"] = "add_price"

                send(
                    chat_id,
                    "💰 Endi narxini yozing.\nMasalan: 25000"
                )
                return

            if action == "add_price":
                try:
                    price = int(
                        text.replace(",", "").replace(" ", "")
                    )
                    if price <= 0:
                        raise ValueError
                except ValueError:
                    send(
                        chat_id,
                        "❌ Narx faqat musbat son bo‘lsin.\n"
                        "Masalan: 25000"
                    )
                    return

                state["price"] = price
                state["action"] = "add_cost_price"
                send(chat_id,"💵 Endi kitob tannarxini yozing (₩).\nMasalan: 10000\nTannarx hali ma’lum bo‘lmasa: 0")
                return

            if action == "add_cost_price":
                try:
                    cost_price=int(text.replace(",","").replace(" ",""))
                    if cost_price<0: raise ValueError
                except ValueError: send(chat_id,"❌ Tannarx 0 yoki undan katta son bo‘lsin."); return
                state["cost_price"]=cost_price; state["action"]="add_stock"; send(chat_id,"📦 Endi qoldiq sonini yozing.\nMasalan: 10"); return

            if action == "add_stock":
                try:
                    stock = int(text.replace(",", "").replace(" ", ""))
                    if stock < 0: raise ValueError
                except ValueError:
                    send(chat_id, "❌ Qoldiq 0 yoki undan katta son bo‘lsin.")
                    return
                state["stock"] = stock
                state["action"] = "add_cover"
                send(
                    chat_id,
                    "📕 Muqova turini yozing:\n"
                    "• Qattiq\n"
                    "• Yumshoq\n"
                    "• Flexible\n"
                    "Muqova ma’lum bo‘lmasa: —"
                )
                return

            if action == "add_cover":
                cover = normalize_cover(text)
                if cover is None:
                    send(
                        chat_id,
                        "❌ Faqat Qattiq, Yumshoq yoki Flexible deb yozing.\n"
                        "Muqova ma’lum bo‘lmasa: —"
                    )
                    return
                state["cover"] = cover
                state["action"] = "add_category"
                send(chat_id, "📂 Kategoriyasini yozing. Masalan: Badiiy\nO‘tkazib yuborish: —")
                return

            if action == "add_category":
                state["category"] = normalize_category(text)
                state["action"] = "add_author"
                send(chat_id, "✍️ Muallifini yozing. Bilinmasa: —")
                return

            if action == "add_author":
                state["author"] = "Ko‘rsatilmagan" if text.strip() in ("-", "—") else text.strip()
                state["action"] = "add_description"
                send(chat_id, "📄 Qisqa tavsifini yozing. Bo‘lmasa: —")
                return

            if action == "add_description":
                state["description"] = "Ma’lumot kiritilmagan." if text.strip() in ("-", "—") else text.strip()
                state["action"] = "add_old_price"
                send(chat_id, "🎁 Eski narxni yozing (chegirma bo‘lsa). Chegirma yo‘q bo‘lsa: 0")
                return

            if action == "add_old_price":
                try:
                    old_price = int(text.replace(",", "").replace(" ", ""))
                    if old_price < 0 or (old_price > 0 and old_price <= int(state["price"])): raise ValueError
                except ValueError:
                    send(chat_id, "❌ Eski narx 0 yoki hozirgi narxdan katta bo‘lsin.")
                    return
                state["old_price"] = old_price
                state["action"] = "add_photo"
                send(chat_id, "📸 Kitob rasmini yuboring. Rasm kerak bo‘lmasa: —")
                return

            if action == "add_photo":
                photos = message.get("photo") or []
                if photos:
                    state["photo_id"] = photos[-1].get("file_id", "")
                elif text == "—":
                    state["photo_id"] = ""
                else:
                    send(chat_id, "📸 Iltimos, kitob rasmini yuboring yoki — deb yozing.")
                    return
                # O‘chirilgan kitob IDsi qayta ishlatilmasin. Timestamp-asosli ID
                # eski tombstone bilan to‘qnashmaydi va cloud syncda kitob qayta tirilmaydi.
                new_id = max(
                    max([int(b["id"]) for b in books], default=0) + 1,
                    int(time.time() * 1000),
                )
                new_book = {"id": new_id, "name": state["name"], "price": state["price"], "cost_price": state.get("cost_price", 0), "stock": state["stock"],
                            "category": state.get("category", "Boshqalar"), "cover": state.get("cover", "Ko‘rsatilmagan"),
                            "author": state.get("author", "Ko‘rsatilmagan"),
                            "description": state.get("description", "Ma’lumot kiritilmagan."), "old_price": state.get("old_price", 0),
                            "photo_id": state.get("photo_id", ""), "recommended": False,
                            "created_at": datetime.now().isoformat(timespec="seconds")}
                books.append(new_book)
                save_books()
                states.pop(chat_id, None)
                send(
                    chat_id,
                    f"✅ Kitob qo‘shildi!\n\n"
                    f"📖 {new_book['name']}\n"
                    f"{price_text(new_book)}\n"
                    f"📦 {new_book['stock']} ta\n"
                    f"📕 Muqova: {new_book['cover']}\n"
                    f"📂 {new_book['category']}",
                    admin_menu()
                )
                return

            if action in ("change_old_price", "change_cost_price", "change_category", "change_cover", "change_author", "change_description", "change_photo"):
                book = find_book(state.get("book_id"))
                if not book:
                    states.pop(chat_id, None)
                    send(chat_id, "❌ Kitob topilmadi.", admin_menu())
                    return
                if action == "change_photo":
                    photos = message.get("photo") or []
                    if photos:
                        book["photo_id"] = photos[-1].get("file_id", "")
                    elif text == "—":
                        book["photo_id"] = ""
                    else:
                        send(chat_id, "📸 Rasm yuboring yoki — deb yozing.")
                        return
                elif action == "change_old_price":
                    try:
                        value = int(text.replace(",", "").replace(" ", ""))
                        if value < 0 or (value > 0 and value <= effective_price(book)): raise ValueError
                    except ValueError:
                        send(chat_id, "❌ Eski narx 0 yoki hozirgi narxdan katta bo‘lsin.")
                        return
                    book["old_price"] = value
                elif action == "change_cost_price":
                    try:
                        value=int(text.replace(",","").replace(" ",""))
                        if value<0: raise ValueError
                    except ValueError: send(chat_id,"❌ Tannarx 0 yoki undan katta son bo‘lsin."); return
                    book["cost_price"]=value
                elif action == "change_category":
                    book["category"] = normalize_category(text)
                elif action == "change_cover":
                    cover = normalize_cover(text)
                    if cover is None:
                        send(
                            chat_id,
                            "❌ Faqat Qattiq, Yumshoq yoki Flexible deb yozing.\n"
                            "Muqovani o‘chirish uchun: —"
                        )
                        return
                    book["cover"] = cover
                elif action == "change_author":
                    book["author"] = "Ko‘rsatilmagan" if text.strip() in ("-", "—") else text.strip()
                else:
                    book["description"] = "Ma’lumot kiritilmagan." if text.strip() in ("-", "—") else text.strip()
                save_books()
                states.pop(chat_id, None)
                send(chat_id, f"✅ {book['name']} ma’lumoti yangilandi.", admin_menu())
                return

            if action in ("rename", "change_price", "change_stock"):
                book = find_book(state["book_id"])

                if not book:
                    states.pop(chat_id, None)
                    send(
                        chat_id,
                        "❌ Kitob topilmadi.",
                        admin_menu()
                    )
                    return

                if action == "rename":
                    if not text:
                        send(
                            chat_id,
                            "❌ Nom bo‘sh bo‘lmasin."
                        )
                        return

                    book["name"] = text
                    msg = f"✅ Kitob nomi o‘zgartirildi: {text}"

                elif action == "change_price":
                    try:
                        value = int(
                            text.replace(",", "").replace(" ", "")
                        )
                        if value <= 0:
                            raise ValueError
                    except ValueError:
                        send(
                            chat_id,
                            "❌ Narx faqat musbat son bo‘lsin.\n"
                            "Masalan: 30000"
                        )
                        return

                    book["price"] = value
                    msg = f"✅ Yangi narx: ₩{value:,}"

                else:
                    try:
                        value = int(
                            text.replace(",", "").replace(" ", "")
                        )
                        if value < 0:
                            raise ValueError
                    except ValueError:
                        send(
                            chat_id,
                            "❌ Qoldiq 0 yoki undan katta son bo‘lsin."
                        )
                        return

                    # Eng so‘nggi books.json ni bir marta o‘qiymiz va aynan shu
                    # kitobning qoldig‘ini o‘zgartiramiz.
                    refresh_books()
                    book = next(
                        (b for b in books if int(b.get("id", -1)) == int(state["book_id"])),
                        None
                    )
                    if not book:
                        states.pop(chat_id, None)
                        send(chat_id, "❌ Kitob topilmadi.", admin_menu())
                        return

                    old_stock = int(book.get("stock", 0))
                    book["stock"] = value
                    msg = f"✅ Yangi qoldiq: {value} ta"

                    if old_stock <= 0 < value:
                        notify_restock(book)

                # Yangi qoldiqni diskka atomik yozamiz va yozilgan holatni
                # darhol qayta yuklab tekshiramiz.
                save_books()
                load_books()
                states.pop(chat_id, None)

                send(
                    chat_id,
                    msg,
                    admin_menu()
                )
                return

        # Admin bo‘lmasa, oddiy mijoz menyusiga o'tishi mumkin.
        # Noma'lum admin xabarini shu yerda qaytaramiz.
        if text not in (
            "📚 Kitoblar",
            "📂 Kategoriyalar",
            "🔎 Qidirish",
            "❤️ Sevimlilar",
            "🔥 Tavsiya etilgan",
            "🆕 Yangi kitoblar",
            "🏆 Eng ko‘p sotilgan",
            "🎯 Menga kitob tanla",
            "🛒 Savatcha",
            "📜 Mening buyurtmalarim",
            "🔢 Buyurtmani tekshirish",
            "📦 Zakaz berish",
            "📞 Bog‘lanish",
            "📦 Zakaslar",
            "📋 Barcha zakaslar",
            "➕ Qo‘lda zakas",
            "➕ SMS / rasm",
            "🤖 Bot zakaslari",
            "📱 Ilova zakaslari",
            "✍️ Qo‘lda kiritilgan",
            "⬅️ Admin panel"
        ):
            send(
                chat_id,
                "Admin paneldan kerakli bo‘limni tanlang.",
                admin_menu()
            )
            return

    # Admin ham eski mijoz funksiyalarini asosiy menyudan ishlatmaydi.
    # Admin bo‘limining yuqoridagi barcha amallari o‘z holicha saqlanadi.
    send(chat_id, "⚙️ Admin paneldagi bo‘limni tanlang.", admin_menu())
    return

    # =========================
    # CUSTOMER: KITOB TAVSIYACHISI (eski kod, ishlatilmaydi)
    # =========================
    if text == "🎯 Menga kitob tanla":
        states[chat_id] = {"action": "recommend_interest"}
        send(
            chat_id,
            "🎯 Sizga mos kitob topib beraman!\n\n"
            "Avval ayting, qaysi mavzu sizni ko‘proq qiziqtiradi?",
            recommender_interest_keyboard()
        )
        return

    if state and state.get("action") == "recommend_interest":
        send(chat_id, "🎯 Quyidagi tugmalardan birini tanlang:", recommender_interest_keyboard())
        return

    if state and state.get("action") == "recommend_style":
        send(chat_id, "✨ Quyidagi tugmalardan birini tanlang:", recommender_style_keyboard())
        return

    # =========================
    # =========================
    # CUSTOMER: SEARCH RESULT
    # =========================

    if state and state.get("action") == "search":
        result = search_books(text)
        states.pop(chat_id, None)
        if not result:
            send(chat_id, f"🔎 «{text}» bo‘yicha kitob topilmadi.", main_menu(chat_id))
        else:
            send(chat_id, f"🔎 «{text}» bo‘yicha {len(result)} ta kitob topildi:", search_books_keyboard(result))
        return

    # CUSTOMER: KATEGORIYALAR
    # =========================
    if text == "📂 Kategoriyalar":
        send(chat_id, "📂 Kategoriyani tanlang:", categories_keyboard())
        return

    # =========================
    # CUSTOMER: SEVIMLILAR
    # =========================
    if text == "❤️ Sevimlilar":
        ids = favorite_ids(chat_id)
        if not ids:
            send(chat_id, "❤️ Sevimlilar hozircha bo‘sh.", main_menu(chat_id))
        else:
            send(chat_id, "❤️ SEVIMLI KITOBLAR", favorites_keyboard(chat_id))
        return

    # =========================
    # CUSTOMER: TAVSIYA ETILGAN / YANGI
    # =========================
    if text == "🔥 Tavsiya etilgan":
        items = [b for b in books if b.get("recommended") and int(b.get("stock", 0)) > 0 and int(b.get("price", 0)) > 0]
        if not items:
            send(chat_id, "🔥 Hozircha tavsiya etilgan kitoblar yo‘q.", main_menu(chat_id))
        else:
            send(chat_id, "🔥 TAVSIYA ETILGAN KITOBLAR", recommended_books_keyboard())
        return

    if text == "🆕 Yangi kitoblar":
        send(chat_id, "🆕 YANGI QO‘SHILGAN KITOBLAR", new_books_keyboard())
        return

    if text == "🏆 Eng ko‘p sotilgan":
        if not best_sellers():
            send(chat_id, "🏆 Hozircha sotuvlar yetarli emas.", main_menu(chat_id))
        else:
            send(chat_id, "🏆 ENG KO‘P SOTILGAN KITOBLAR", best_sellers_keyboard())
        return

    # =========================
    # CUSTOMER: QIDIRUV
    # =========================

    if text == "🔎 Qidirish":
        states[chat_id] = {"action": "search"}
        send(
            chat_id,
            "🔎 Kitob nomini yozing.\nMasalan: Yovuz daho\n\nBir-ikki harf xato bo‘lsa ham topishga harakat qilaman."
        )
        return

    # =========================
    # CUSTOMER: BUYURTMALARIM
    # =========================

    if text == "📜 Mening buyurtmalarim":
        send(chat_id, user_orders_text(chat_id), user_orders_keyboard(chat_id))
        return

    if text == "🔢 Buyurtmani tekshirish":
        states[chat_id] = {"action": "lookup_order"}
        send(chat_id, "🔢 Buyurtma raqamini yozing. Masalan: 0001\n❌ Bekor qilish uchun tugmani bosing.", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
        return

    # =========================
    # CUSTOMER: KITOBLAR
    # =========================

    if text == "📚 Kitoblar":
        send(
            chat_id,
            catalog_intro_text(),
            books_menu()
        )
        return

    # =========================
    # CUSTOMER: SAVATCHA
    # =========================

    if text == "🛒 Savatcha":
        send(
            chat_id,
            cart_text(chat_id),
            cart_keyboard(chat_id)
        )
        return

    # =========================
    # CUSTOMER: ZAKAZ BOSHLASH
    # =========================

    if text == "📦 Zakaz berish":
        cart = carts.get(chat_id, {})

        if not cart:
            send(
                chat_id,
                "🛒 Avval kitob tanlang.",
                main_menu(chat_id)
            )
            return

        saved = saved_customer_info(chat_id)
        states[chat_id] = {
            "action": "order_confirm" if saved else "order_name",
            "username": username,
            "chat_id": chat_id,
            "cart": dict(cart),
            "payment_declared": False
        }
        if saved:
            states[chat_id].update(saved)
            preview, total, grand_total = order_preview_text(states[chat_id])
            states[chat_id]["total"] = total
            states[chat_id]["delivery_fee"] = delivery_fee_for_cart(cart)
            states[chat_id]["grand_total"] = grand_total
            send(
                chat_id,
                "✅ Oldingi ma’lumotlaringiz ishlatildi.\n\n"
                + preview + "\n\n" + order_customer_info_text(states[chat_id]),
                order_edit_keyboard(states[chat_id])
            )
        else:
            send(
                chat_id,
                cart_text(chat_id) + "\n\n📝 Buyurtma uchun ismingizni yozing:",
                order_keyboard()
            )
        return

    # =========================
    # CUSTOMER: BEKOR QILISH
    # =========================

    if text == "❌ Bekor qilish":
        current_state = states.get(chat_id, {})
        if current_state.get("payment_declared", False):
            send(
                chat_id,
                "📸 To‘lov cheki yuborilgan. Endi ma’lumotlarni tekshirib, buyurtmani tasdiqlang.",
                order_edit_keyboard(current_state)
            )
            return

        states.pop(chat_id, None)

        send(
            chat_id,
            "Bekor qilindi.",
            main_menu(chat_id)
        )
        return

    # =========================
    # CUSTOMER: BOG'LANISH
    # =========================

    if text == "📞 Bog‘lanish":
        send(
            chat_id,
            "📞 Bog‘lanish:\n"
            "Admin bilan Telegram orqali bog‘lanishingiz mumkin.",
            main_menu(chat_id)
        )
        return

    # =========================
    # ORDER: ISM
    # =========================

    if state and state.get("action") == "order_name":
        state["name"] = text
        state["action"] = "order_phone"

        send(
            chat_id,
            "📞 Telefon raqamingizni yozing.\n\n"
            "Masalan: 01012345678"
        )
        return

    # =========================
    # ORDER: TELEFON
    # =========================

    if state and state.get("action") == "order_phone":
        if not valid_phone_number(text):
            send(
                chat_id,
                "❌ Telefon raqami noto‘g‘ri.\n\n"
                "8–15 ta raqamdan iborat telefon raqamingizni qayta yozing.\n"
                "Masalan: 01012345678"
            )
            return
        state["phone"] = text
        state["action"] = "order_address"

        send(
            chat_id,
            "📍 Manzil va xona raqamini to‘liq yozing.\n\n"
            "Masalan: 경상북도 경산시 계양로 37길 7-3, 808호"
        )
        return

    # =========================
    # ORDER: MANZIL
    # =========================

    if state and state.get("action") == "order_saved_address":
        state["address"] = text

        for book_id, qty in state["cart"].items():
            book = find_book(book_id)
            if not book or int(book["stock"]) < int(qty):
                states.pop(chat_id, None)
                send(
                    chat_id,
                    "❌ Kechirasiz, buyurtmadagi kitoblardan biri yetarli qolmagan.",
                    main_menu(chat_id)
                )
                return

        preview, total, grand_total = order_preview_text(state)
        state["total"] = total
        state["delivery_fee"] = delivery_fee_for_cart(state["cart"])
        state["grand_total"] = grand_total
        state["action"] = "order_confirm"
        send(
            chat_id,
            preview + "\n\n" + order_customer_info_text(state),
            order_edit_keyboard(state)
        )
        return

    if state and state.get("action") == "order_address":
        state["address"] = text

        # Omborni tekshirish
        for book_id, qty in state["cart"].items():
            book = find_book(book_id)

            if not book or int(book["stock"]) < int(qty):
                states.pop(chat_id, None)

                send(
                    chat_id,
                    "❌ Kechirasiz, buyurtmadagi "
                    "kitoblardan biri yetarli qolmagan.",
                    main_menu(chat_id)
                )
                return

        preview, total, grand_total = order_preview_text(state)

        state["total"] = total
        state["delivery_fee"] = delivery_fee_for_cart(state["cart"])
        state["grand_total"] = grand_total
        state["action"] = "order_confirm"

        send(
            chat_id,
            preview,
            order_edit_keyboard()
        )
        return

    if state and state.get("action") in ("edit_order_name", "edit_order_phone", "edit_order_address"):
        if not text:
            send(chat_id, "❌ Ma’lumot bo‘sh bo‘lmasin.")
            return

        action = state["action"]
        key = {
            "edit_order_name": "name",
            "edit_order_phone": "phone",
            "edit_order_address": "address"
        }[action]
        if key == "phone" and not valid_phone_number(text):
            send(
                chat_id,
                "❌ Telefon raqami noto‘g‘ri. 8–15 ta raqam bilan qayta yozing.\n"
                "Masalan: 01012345678"
            )
            return
        state[key] = text

        preview, total, grand = order_preview_text(
            state,
            show_payment_info=not state.get("payment_declared", False)
        )
        state["total"], state["grand_total"], state["action"] = total, grand, "order_confirm"

        # Tahrirdan keyin ham yangilangan ism/telefon/manzil ko‘rinsin.
        # To‘lov avval belgilangan bo‘lsa, shu holat ham saqlanadi.
        customer_info = order_customer_info_text(state)
        extra = ""
        if state.get("payment_declared", False):
            extra = "\n\nMa’lumotlaringizni tekshirib, buyurtmani tasdiqlang."

        send(
            chat_id,
            preview + "\n\n" + customer_info + extra,
            order_edit_keyboard(state)
        )
        return

    # =========================
    # ORDER: TASDIQLASH
    # =========================

    if state and state.get("action") == "order_confirm":
        if text == "✅ Buyurtmani tasdiqlash":
            finalize_order(chat_id)
            return
        send(chat_id, "Buyurtmani tugmalar orqali tahrirlang yoki tasdiqlang.", order_edit_keyboard(state))
        return

    if state and state.get("action") == "lookup_order":
        if not text.isdigit():
            send(chat_id, "❌ Buyurtma raqami faqat raqamlardan iborat bo‘lsin.")
            return
        order = find_order_by_display_number(text, chat_id)
        states.pop(chat_id, None)
        if not order:
            send(chat_id, "❌ Bunday buyurtma topilmadi.", main_menu(chat_id))
            return
        send(chat_id, f"🧾 BUYURTMA №{display_order_number(order)}\n\n{status_name(order.get('status'))}\n💵 Jami: ₩{int(order.get('grand_total',0)):,}", main_menu(chat_id))
        return

    # =========================
    # NOMALUM XABAR
    # =========================

    send(
        chat_id,
        "Menyudan kerakli bo‘limni tanlang.",
        main_menu(chat_id)
    )


# =========================
# CALLBACK HANDLER
# =========================

def handle_callback(callback):
    # Eskirgan tugmalar uchun Telegram 400 qaytarishi mumkin.
    # Callbackni tasdiqlashni disk/cloud amallaridan oldin qilamiz.
    callback_id = callback["id"]
    message = callback.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    data = callback.get("data", "")

    try:
        api(
            "answerCallbackQuery",
            {"callback_query_id": callback_id}
        )
    except urllib.error.HTTPError as e:
        print("Callback answer xatosi:", e)
        if e.code == 400:
            # Javob muddati o'tgan callbackni qayta ishlab,
            # eski amallarni takrorlamaymiz.
            return
    except Exception as e:
        print("Callback answer xatosi:", e)

    if chat_id is None:
        return

    # Oxirgi katalog va buyurtmalarni faqat yaroqli callback uchun yuklaymiz.
    load_books()
    load_orders()

    # Eski katalog/savatcha inline tugmalari mijozlar uchun endi yopiq.
    # Faqat admin callbacklari avvalgidek davom etadi.
    if not is_admin(chat_id):
        states.pop(chat_id, None)
        send_app_download_link(chat_id)
        return

    if data.startswith("finance_"):
        if not is_admin(chat_id):
            return
        period = data.split("_", 1)[1]
        if period not in FINANCE_PERIOD_LABELS:
            period = "month"
        send(chat_id, finance_report_text(period), finance_report_keyboard())
        return

    if chat_id is None:
        return

    # Callback ham botdan foydalanish hisoblanadi.
    register_user(chat_id, callback.get("from", {}))

    if data == "shipsmart_save":
        if not is_admin(chat_id):
            return
        state = states.get(chat_id, {})
        if state.get("action") != "shipping_smart_confirm":
            send(chat_id, "ℹ️ Saqlanadigan zakas topilmadi.", shipping_queue_menu())
            return
        try:
            instagram_cloud_id = str(state.get("instagram_cloud_order_id") or "").strip()
            if instagram_cloud_id:
                entry = cloud_bridge.enable_instagram_shipping(
                    instagram_cloud_id,
                    state.get("name"),
                    state.get("phone"),
                    state.get("address"),
                )
            else:
                entry = save_manual_shipping_order(state)
        except Exception as exc:
            send(chat_id, f"❌ Zakas saqlanmadi: {exc}", shipping_queue_menu())
            return
        states.pop(chat_id, None)
        _send_saved_shipping_entry(chat_id, entry)
        return

    if data == "shipsmart_cancel":
        if is_admin(chat_id):
            states.pop(chat_id, None)
            send(chat_id, "❎ Zakas kiritish bekor qilindi.", shipping_queue_menu())
        return

    if data.startswith("shipdel_"):
        if not is_admin(chat_id):
            return
        parts = data.split("_", 2)
        if len(parts) != 3 or parts[1] not in ("m", "o"):
            return
        kind, queue_id = parts[1], parts[2]
        send(
            chat_id,
            "⚠️ Rostdan ham bu zakasni POCHTA ZAKASLAR ro‘yxatidan o‘chirasizmi?\n\nAsl buyurtma, ombor va statistika o‘zgarmaydi.",
            {"inline_keyboard": [
                [{"text": "✅ Ha, o‘chirish", "callback_data": f"shipdelok_{kind}_{queue_id}"}],
                [{"text": "❌ Yo‘q", "callback_data": "shipdelno"}],
            ]},
        )
        return

    if data.startswith("shipdelok_"):
        if not is_admin(chat_id):
            return
        parts = data.split("_", 2)
        if len(parts) != 3 or parts[1] not in ("m", "o"):
            return
        delete_shipping_queue_entry(parts[1], parts[2])
        send(chat_id, "✅ Zakas pochta ro‘yxatidan o‘chirildi. Asl buyurtmaga tegilmadi.", shipping_queue_menu())
        return

    if data == "shipdelno":
        if is_admin(chat_id):
            send(chat_id, "❎ O‘chirish bekor qilindi.", shipping_queue_menu())
        return

    # =========================
    # HOME
    # =========================

    if data == "home":
        send(
            chat_id,
            "Asosiy menyu:",
            main_menu(chat_id)
        )
        return

    # =========================
    # YANGI KITOBLAR
    # =========================

    if data == "new_books":
        send(
            chat_id,
            "🆕 YANGI QO‘SHILGAN KITOBLAR",
            new_books_keyboard()
        )
        return

    # =========================
    # KITOBLAR
    # =========================

    if data == "books":
        send(
            chat_id,
            catalog_intro_text(),
            books_menu()
        )
        return

    if data.startswith("books_page_"):
        try:
            page = int(data[len("books_page_"):])
        except Exception:
            return

        send(
            chat_id,
            catalog_intro_text(page),
            books_menu(page)
        )
        return

    # =========================
    # SAVATCHADAN ZAKAZ BERISH
    # =========================

    if data == "cart_order":
        cart = carts.get(chat_id, {})

        if not cart:
            send(chat_id, "🛒 Avval kitob tanlang.", main_menu(chat_id))
            return

        state_user = users.get(str(chat_id), {})
        saved = saved_customer_info(chat_id)
        states[chat_id] = {
            "action": "confirm_saved_info" if saved else "order_name",
            "username": state_user.get("username", ""),
            "chat_id": chat_id,
            "cart": dict(cart),
            "payment_declared": False
        }
        if saved:
            states[chat_id].update(saved)
            send(
                chat_id,
                "📍 Oldingi ma’lumotlaringiz bizda saqlangan.\n\n"
                + order_customer_info_text(states[chat_id])
                + "\n\nShu manzilga yuborilsinmi?",
                {"inline_keyboard": [
                    [{"text": "✅ Shu manzilga yuborish", "callback_data": "saved_use_address"}],
                    [{"text": "📍 Boshqa manzil", "callback_data": "saved_new_address"}]
                ]}
            )
        else:
            send(chat_id, cart_text(chat_id) + "\n\n📝 Buyurtma uchun ismingizni yozing:")
        return

    if data == "saved_use_address":
        state = states.get(chat_id)
        if not state or state.get("action") != "confirm_saved_info":
            return
        preview, total, grand = order_preview_text(state)
        state["total"] = total
        state["delivery_fee"] = delivery_fee_for_cart(state["cart"])
        state["grand_total"] = grand
        state["action"] = "order_confirm"
        send(
            chat_id,
            preview + "\n\n" + order_customer_info_text(state),
            order_edit_keyboard(state)
        )
        return

    if data == "saved_new_address":
        state = states.get(chat_id)
        if not state or state.get("action") != "confirm_saved_info":
            return
        state.pop("name", None)
        state.pop("phone", None)
        state.pop("address", None)
        state["action"] = "order_name"
        send(chat_id, "📝 Yangi buyurtma uchun ismingizni yozing:")
        return

    # =========================
    # SAVATCHA - NOOP
    # =========================

    if data == "cart_noop":
        return

    # =========================
    # SAVATCHA - KAMAYTIRISH
    # =========================

    if data.startswith("cartminus_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except (ValueError, IndexError):
            return

        cart = carts.get(chat_id, {})

        if book_id in cart:
            cart[book_id] = int(cart[book_id]) - 1

            if cart[book_id] <= 0:
                del cart[book_id]

        if states.get(chat_id):
            if states[chat_id].get("action") == "order_confirm":
                states[chat_id]["cart"] = dict(cart)
                states[chat_id]["payment_declared"] = False
                states[chat_id].pop("receipt_file_id", None)
                states[chat_id].pop("payment_items", None)
                states[chat_id].pop("payment_total", None)
                states[chat_id].pop("payment_grand_total", None)

        try:
            edit_message(
                chat_id,
                message.get("message_id"),
                cart_text(chat_id),
                cart_keyboard(chat_id)
            )
        except Exception as e:
            print("Savatchani yangilash xatosi:", e)

        return

    # =========================
    # SAVATCHA - KO‘PAYTIRISH
    # =========================

    if data.startswith("cartplus_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except (ValueError, IndexError):
            return

        book = find_book(book_id)
        cart = carts.setdefault(chat_id, {})

        if not book:
            return

        current = int(cart.get(book_id, 0))
        stock = int(book.get("stock", 0))

        if current >= stock:
            try:
                api(
                    "answerCallbackQuery",
                    {
                        "callback_query_id": callback_id,
                        "text": f"Omborda faqat {stock} ta bor.",
                        "show_alert": True
                    }
                )
            except Exception:
                pass
            return

        cart[book_id] = current + 1

        if states.get(chat_id):
            if states[chat_id].get("action") == "order_confirm":
                states[chat_id]["cart"] = dict(cart)
                states[chat_id]["payment_declared"] = False
                states[chat_id].pop("receipt_file_id", None)
                states[chat_id].pop("payment_items", None)
                states[chat_id].pop("payment_total", None)
                states[chat_id].pop("payment_grand_total", None)

        try:
            edit_message(
                chat_id,
                message.get("message_id"),
                cart_text(chat_id),
                cart_keyboard(chat_id)
            )
        except Exception as e:
            print("Savatchani yangilash xatosi:", e)

        return

    # =========================
    # SAVATCHA - BITTA KITOBNI O‘CHIRISH
    # =========================

    if data.startswith("cartdelete_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except (ValueError, IndexError):
            return

        cart = carts.get(chat_id, {})

        if book_id in cart:
            del cart[book_id]

        if states.get(chat_id):
            if states[chat_id].get("action") == "order_confirm":
                states[chat_id]["cart"] = dict(cart)
                states[chat_id]["payment_declared"] = False
                states[chat_id].pop("receipt_file_id", None)
                states[chat_id].pop("payment_items", None)
                states[chat_id].pop("payment_total", None)
                states[chat_id].pop("payment_grand_total", None)

        try:
            edit_message(
                chat_id,
                message.get("message_id"),
                cart_text(chat_id),
                cart_keyboard(chat_id)
            )
        except Exception as e:
            print("Savatchani yangilash xatosi:", e)

        return

    # =========================
    # SAVATCHANI TO‘LIQ TOZALASH
    # =========================

    if data == "cartclear":
        carts[chat_id] = {}

        if states.get(chat_id):
            if states[chat_id].get("action") == "order_confirm":
                states[chat_id]["cart"] = {}
                states[chat_id]["payment_declared"] = False
                states[chat_id].pop("receipt_file_id", None)
                states[chat_id].pop("payment_items", None)
                states[chat_id].pop("payment_total", None)
                states[chat_id].pop("payment_grand_total", None)

        try:
            edit_message(
                chat_id,
                message.get("message_id"),
                "🛒 Savatcha bo‘sh.",
                cart_keyboard(chat_id)
            )
        except Exception as e:
            print("Savatchani tozalash xatosi:", e)

        return

    if data == "qstock_list":
        if not is_admin(chat_id): return
        refresh_books()
        states[chat_id]={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}
        send(chat_id,"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id)); return
    if data == "qstock_noop":
        return
    if data.startswith("qstock_batch_"):
        if not is_admin(chat_id): return
        try:
            parts=data.split("_"); book_id=int(parts[2]); delta=int(parts[3])
        except Exception: return
        state=states.get(chat_id,{})
        if state.get("action")!="quick_stock_batch":
            refresh_books(); state={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}; states[chat_id]=state
        draft=state.setdefault("stock_draft",{})
        current=int(draft.get(str(book_id),0)); draft[str(book_id)]=max(0,current+delta)
        try:
            edit_message(chat_id,message.get("message_id"),"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id))
        except Exception as e: print("Tezkor qoldiq yangilash xatosi:",e)
        return
    if data == "qstock_save":
        if not is_admin(chat_id): return
        state=states.get(chat_id,{})
        if state.get("action")!="quick_stock_batch": send(chat_id,"ℹ️ Saqlanadigan o‘zgarish yo‘q.",admin_menu()); return
        draft=state.get("stock_draft",{}); refresh_books(); restocked=[]; changed=0
        for b in books:
            key=str(int(b["id"])); old_stock=int(b.get("stock",0)); new_stock=int(draft.get(key,old_stock))
            if new_stock!=old_stock:
                b["stock"]=new_stock; changed+=1
                if old_stock<=0<new_stock: restocked.append(b)
        if changed: save_books()
        states.pop(chat_id,None)
        for b in restocked: notify_restock(b)
        send(chat_id,f"✅ Saqlandi. {changed} ta kitob qoldig‘i yangilandi.",admin_menu()); return
    if data == "qstock_cancel":
        if not is_admin(chat_id): return
        states.pop(chat_id,None); send(chat_id,"❌ O‘zgarishlar saqlanmadi.",admin_menu()); return
    if data.startswith("qstock_book_") or data.startswith("qstock_adj_") or data.startswith("qstock_set_"):
        if not is_admin(chat_id): return
        send(chat_id,"ℹ️ Bu eski tezkor qoldiq oynasi. ⚡ Tezkor qoldiqni qayta oching.",admin_menu()); return

    if data.startswith("report_"):
        if not is_admin(chat_id): return
        period = data.split("_",1)[1]
        send(chat_id, admin_report_text(period), admin_report_keyboard())
        return

    if data == "admin_orders":
        if is_admin(chat_id):
            send(chat_id, "📦 BUYURTMALAR\n\nKerakli papkani tanlang:", admin_orders_keyboard(None))
        return

    if data.startswith("adminorders_"):
        if not is_admin(chat_id):
            return
        status_filter = data.split("_", 1)[1]
        if status_filter not in set(ORDER_STATUS_NAMES) | {"all"}:
            return
        send(chat_id, admin_orders_text(status_filter), admin_orders_keyboard(status_filter))
        return

    # =========================
    # ADMIN
    # =========================

    if data == "admin":
        if is_admin(chat_id):
            states.pop(chat_id, None)

            send(
                chat_id,
                "⚙️ Admin panel",
                admin_menu()
            )
        return

    # =========================
    # EDIT LIST
    # =========================

    if data == "page_noop" or data == "qstock_noop":
        try:
            api("answerCallbackQuery", {"callback_query_id": callback_id})
        except Exception:
            pass
        return
    if data.startswith("editpage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        try:
            edit_message(chat_id, message_id, "✏️ Tahrirlash uchun kitob tanlang:", edit_book_menu(page))
        except Exception:
            send(chat_id, "✏️ Tahrirlash uchun kitob tanlang:", edit_book_menu(page))
        return
    if data.startswith("deletepage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        try:
            edit_message(chat_id, message_id, "🗑 O‘chirish uchun kitobni tanlang:", delete_book_menu(page))
        except Exception:
            send(chat_id, "🗑 O‘chirish uchun kitobni tanlang:", delete_book_menu(page))
        return
    if data.startswith("qstock_page_"):
        if not is_admin(chat_id): return
        state = states.get(chat_id, {})
        if state.get("action") != "quick_stock_batch": return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        state["stock_page"] = page
        try:
            edit_message(chat_id, message_id, "⚡ Tezkor qoldiq — kitoblar bo‘yicha o‘zgartiring:", quick_stock_list_keyboard(chat_id, page))
        except Exception:
            send(chat_id, "⚡ Tezkor qoldiq:", quick_stock_list_keyboard(chat_id, page))
        return
    if data == "editlist":
        if is_admin(chat_id):
            send(
                chat_id,
                "Tahrir qilinadigan kitobni tanlang:",
                edit_book_menu()
            )
        return

    # =========================
    # EDIT BOOK
    # =========================

    if data.startswith("edit_"):
        if not is_admin(chat_id):
            return

        book = find_book(data.split("_", 1)[1])

        if book:
            send(
                chat_id,
                f"✏️ {book['name']}\n\nNimani o‘zgartirmoqchisiz?",
                edit_fields_menu(book["id"])
            )
        return

    # =========================
    # FULL BOOK EDIT
    # =========================

    if data.startswith("eall_"):
        if not is_admin(chat_id):
            return
        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)
        if not book:
            send(chat_id, "❌ Kitob topilmadi.", admin_menu())
            return
        states[chat_id] = {"action": "full_edit_name", "book_id": book_id}
        send(chat_id, f"🛠 {book['name']} — umumiy tahrirlash\n\n✏️ Yangi nomini yozing:\nHozirgi: {book['name']}")
        return

    # =========================
    # RENAME
    # =========================

    if data.startswith("ename_"):
        if not is_admin(chat_id):
            return

        book_id = int(data.split("_", 1)[1])

        states[chat_id] = {
            "action": "rename",
            "book_id": book_id
        }

        send(
            chat_id,
            "✏️ Yangi kitob nomini yozing:"
        )
        return

    # =========================
    # PRICE
    # =========================

    if data.startswith("eprice_"):
        if not is_admin(chat_id):
            return

        book_id = int(data.split("_", 1)[1])

        states[chat_id] = {
            "action": "change_price",
            "book_id": book_id
        }

        send(
            chat_id,
            "💰 Yangi narxni yozing (₩).\nMasalan: 35000"
        )
        return

    if data.startswith("ecost_"):
        if not is_admin(chat_id): return
        book_id=int(data.split("_",1)[1]); states[chat_id]={"action":"change_cost_price","book_id":book_id}; book=find_book(book_id); current=int(book.get("cost_price",0) or 0) if book else 0; send(chat_id,f"💵 Yangi tannarxni yozing (₩).\nHozirgi: ₩{current:,}\nTannarx ma’lum bo‘lmasa: 0"); return

    # =========================
    # STOCK
    # =========================

    if data.startswith("estock_"):
        if not is_admin(chat_id):
            return

        book_id = int(data.split("_", 1)[1])

        states[chat_id] = {
            "action": "change_stock",
            "book_id": book_id
        }

        send(
            chat_id,
            "📦 Yangi qoldiqni yozing.\nMasalan: 12"
        )
        return

    # =========================
    # EDIT EXTRA FIELDS
    # =========================

    for prefix, action, prompt in [
        ("eoldprice_", "change_old_price", "🎁 Eski narxni yozing. Chegirma yo‘q bo‘lsa: 0"),
        ("ecat_", "change_category", "📂 Yangi kategoriyani yozing:"),
        ("ecover_", "change_cover", "📕 Muqova turini yozing: Qattiq / Yumshoq / Flexible\nO‘chirish uchun: —"),
        ("eauthor_", "change_author", "✍️ Yangi muallifni yozing:"),
        ("edesc_", "change_description", "📄 Yangi tavsifni yozing:"),
        ("ephoto_", "change_photo", "📸 Yangi rasmni yuboring. O‘chirish uchun: —"),
    ]:
        if data.startswith(prefix):
            if not is_admin(chat_id): return
            book_id = int(data.split("_", 1)[1])
            states[chat_id] = {"action": action, "book_id": book_id}
            send(chat_id, prompt)
            return

    if data.startswith("erec_"):
        if not is_admin(chat_id):
            return
        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)
        if not book:
            return
        book["recommended"] = not bool(book.get("recommended", False))
        save_books()
        state_text = "🔥 Tavsiya etilgan" if book["recommended"] else "Tavsiya olib tashlandi"
        send(chat_id, f"✅ {book['name']}: {state_text}.", edit_fields_menu(book_id))
        return

    # =========================
    # DELETE BOOK
    # =========================

    if data.startswith("delete_"):
        if not is_admin(chat_id):
            return

        try:
            book_id = int(data.split("_", 1)[1])
        except Exception:
            send(chat_id, "❌ Kitob ID noto‘g‘ri.", admin_menu())
            return

        refresh_books()
        book = find_book(book_id)
        if not book:
            # Eski Telegram inline xabari katalog emas. Kitob allaqachon o‘chirilgan
            # bo‘lsa, o‘sha eski xabarning tugmalarini ham olib tashlaymiz.
            try:
                edit_message(
                    chat_id,
                    message.get("message_id"),
                    "🗑 Bu kitob allaqachon o‘chirilgan.\n\n✅ Eski tugma ham tozalandi.",
                    {"inline_keyboard": []}
                )
            except Exception:
                send(
                    chat_id,
                    "ℹ️ Bu eski tugma. Kitob allaqachon o‘chirilgan yoki ro‘yxat yangilangan.",
                    admin_menu()
                )
            return

        try:
            cloud_bridge.delete_book(book)
        except Exception as e:
            send(chat_id, f"❌ Kitob o‘chirilmadi: {e}", admin_menu())
            return

        # Bir xil ID/cloud_id bilan qolgan stale lokal nusxalarni ham birdan tozalaymiz.
        target_cloud = str(book.get("cloud_id") or "")
        target_id = str(book.get("id") or "")
        books[:] = [
            b for b in books
            if str(b.get("id") or "") != target_id
            and (not target_cloud or str(b.get("cloud_id") or "") != target_cloud)
        ]
        save_books()
        refresh_books()

        send(
            chat_id,
            f"🗑 O‘chirildi: {book['name']}\n\n✅ Bot va ilova katalogidan olib tashlandi.",
            edit_book_menu() if books else admin_menu()
        )
        return

    # =========================
    # UNAVAILABLE BOOK
    # =========================

    if data.startswith("none_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except Exception:
            return
        book = find_book(book_id)
        if not book:
            return
        subscribed = str(chat_id) in [str(x) for x in restock_subscribers.get(str(book_id), [])]
        if subscribed:
            text = f"❌ {book['name']} hozircha mavjud emas.\n\n🔔 Siz qayta kelganda xabar olishga allaqachon yozilgansiz."
            kb = {"inline_keyboard":[[{"text":"📖 Batafsil", "callback_data":f"book_{book_id}"}],[{"text":"🏠 Bosh menyu","callback_data":"home"}]]}
        else:
            text = f"❌ {book['name']} hozircha mavjud emas.\n\n🔔 Xohlasangiz, qayta kelganda sizga xabar beramiz."
            kb = {"inline_keyboard":[[{"text":"🔔 Kelganda xabar bering", "callback_data":f"restock_{book_id}"}],[{"text":"🏠 Bosh menyu","callback_data":"home"}]]}
        send(chat_id, text, kb)
        return

    if data.startswith("restock_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except Exception:
            return
        book = find_book(book_id)
        if not book:
            return
        if int(book.get("stock", 0)) > 0:
            send(chat_id, "✅ Bu kitob hozir mavjud.", book_detail_keyboard(book, chat_id))
            return
        subscribe_restock(chat_id, book_id)
        send(chat_id, f"🔔 Tayyor! {book['name']} qayta kelganda sizga xabar beramiz.", main_menu(chat_id))
        return

    # =========================
    # KITOB TAVSIYACHISI
    # =========================
    if data == "recommend_again":
        states[chat_id] = {"action": "recommend_interest"}
        send(chat_id, "🎯 Avval ayting, qaysi mavzu sizni ko‘proq qiziqtiradi?", recommender_interest_keyboard())
        return

    if data.startswith("rec_i_"):
        interest = data[6:]
        if interest not in {"psixologiya", "biznes", "romantika", "detektiv", "diniy", "tarix", "rivojlanish", "any"}:
            return
        states[chat_id] = {"action": "recommend_style", "interest": interest}
        send(
            chat_id,
            "✨ Endi qanday kitob xohlaysiz?",
            recommender_style_keyboard()
        )
        return

    if data.startswith("rec_s_"):
        style = data[6:]
        if style not in {"easy", "think", "emotion", "exciting", "any"}:
            return
        state = states.get(chat_id, {})
        interest = state.get("interest", "any")
        states.pop(chat_id, None)
        recommender_result(chat_id, interest, style)
        return

    # =========================
    # KATEGORIYALAR
    # =========================
    if data == "categories":
        send(chat_id, "📂 Kategoriyani tanlang:", categories_keyboard())
        return

    if data.startswith("catidx_"):
        try:
            idx = int(data[len("catidx_"):])
            cats = category_list()
            if idx < 0 or idx >= len(cats):
                send(chat_id, "❌ Kategoriya topilmadi.", categories_keyboard())
                return
            category = cats[idx]
        except Exception:
            send(chat_id, "❌ Kategoriya topilmadi.", categories_keyboard())
            return
        send(chat_id, f"📂 {category}", category_books_keyboard(category, chat_id))
        return

    if data.startswith("catpage_"):
        try:
            parts = data.split("_", 2)
            page = int(parts[1])
            category = urllib.parse.unquote(parts[2])
        except Exception:
            return

        category = normalize_category(category)
        send(
            chat_id,
            f"📂 {category}",
            category_books_keyboard(category, chat_id, page)
        )
        return

    # Eski xabarlardagi cat_<kategoriya> tugmalarini ham ishlatamiz.
    if data.startswith("cat_"):
        try:
            category = urllib.parse.unquote(data[4:])
            if not category:
                return
            send(chat_id, f"📂 {normalize_category(category)}",
                 category_books_keyboard(normalize_category(category), chat_id))
        except Exception:
            send(chat_id, "❌ Kategoriya topilmadi.", categories_keyboard())
        return

    # =========================
    # SEVIMLILAR
    # =========================
    if data == "favorites":
        ids = favorite_ids(chat_id)
        if not ids:
            send(chat_id, "❤️ Sevimlilar hozircha bo‘sh.", main_menu(chat_id))
        else:
            send(chat_id, "❤️ SEVIMLI KITOBLAR", favorites_keyboard(chat_id))
        return

    if data.startswith("fav_"):
        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)
        if not book: return
        added = toggle_favorite(chat_id, book_id)
        send(chat_id, ("❤️ Sevimlilarga qo‘shildi." if added else "💔 Sevimlilardan olib tashlandi."), book_detail_keyboard(book, chat_id))
        return

    # =========================
    # ORDER EDIT CALLBACKS
    # =========================
    if data == "order_lookup":
        states[chat_id] = {"action": "lookup_order"}
        send(chat_id, "🔢 Buyurtma raqamini yozing.", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
        return

    if data == "order_cancel_cb":
        state = states.get(chat_id)
        if state and state.get("payment_declared", False):
            send(
                chat_id,
                "📸 To‘lov cheki yuborilgan. Endi buyurtmani bekor qilib bo‘lmaydi. Ma’lumotlarni tekshirib, tasdiqlang.",
                order_edit_keyboard(state)
            )
            return
        states.pop(chat_id, None)
        send(chat_id, "Buyurtma bekor qilindi.", main_menu(chat_id))
        return

    if data == "order_payment_done":
        state = states.get(chat_id)
        if not state or state.get("action") != "order_confirm":
            return
        if state.get("payment_declared", False):
            send(
                chat_id,
                "📸 To‘lov cheki allaqachon yuborilgan. Ma’lumotlarni tekshirib, buyurtmani tasdiqlang.",
                order_edit_keyboard(state)
            )
            return
        state["action"] = "awaiting_receipt"
        send(
            chat_id,
            "📸 TO‘LOV CHEKI\n\n"
            "Karta orqali qilgan to‘lovingiz chekining rasmini shu yerga yuboring.\n\n"
            "Rasm tiniq va summa ko‘rinadigan bo‘lsin.",
            order_keyboard()
        )
        return

    if data == "order_confirm_cb":
        state = states.get(chat_id)
        if not state or state.get("action") != "order_confirm":
            return
        if not state.get("payment_declared", False):
            send(chat_id, "💳 Avval «📸 To‘lov chekini yuborish» tugmasini bosing.",
                 order_edit_keyboard(state))
            return
        finalize_order(chat_id)
        return

    if data in ("orderedit_name", "orderedit_phone", "orderedit_address"):
        state = states.get(chat_id)
        if not state or "cart" not in state: return
        prompts = {"orderedit_name":"📝 Yangi ismingizni yozing:", "orderedit_phone":"📱 Yangi telefon raqamingizni yozing:", "orderedit_address":"📍 Yangi manzil va xona raqamini to‘liq yozing.\n\nMasalan: 경상북도 경산시 계양로 37길 7-3, 808호"}
        state["action"] = {"orderedit_name":"edit_order_name", "orderedit_phone":"edit_order_phone", "orderedit_address":"edit_order_address"}[data]
        send(chat_id, prompts[data])
        return

    if data == "orderedit_cart":
        state = states.get(chat_id)
        if state and state.get("cart"):
            carts[chat_id] = dict(state["cart"])
            send(chat_id, "🛒 Savatni o‘zgartiring:", order_cart_keyboard(chat_id))
        elif state:
            send(chat_id, "🛒 Buyurtmadagi savat bo‘sh.", order_edit_keyboard(state))
        return

    if data == "orderback_cart":
        state = states.get(chat_id)
        if state:
            state["cart"] = dict(carts.get(chat_id, state.get("cart", {})))
            preview, total, grand = order_preview_text(
                state,
                show_payment_info=not state.get("payment_declared", False)
            )
            state["total"], state["grand_total"], state["action"] = total, grand, "order_confirm"
            send(chat_id, preview, order_edit_keyboard(state))
        return


    # =========================
    # REYTING
    # =========================
    if data == "myorders":
        send(chat_id, user_orders_text(chat_id), user_orders_keyboard(chat_id))
        return

    if data.startswith("ratebook_"):
        parts = data.split("_")
        if len(parts) < 3:
            return
        order_id, book_id = parts[1], parts[2]
        order = orders.get(order_id)
        book = find_book(book_id)
        if not order or not book or int(order.get("chat_id", -1)) != int(chat_id) or order.get("status") != "shipped":
            send(chat_id, "❌ Bu kitobni baholash mumkin emas.")
            return
        if user_has_rated(chat_id, order_id, book_id):
            send(chat_id, "⭐ Bu kitobni allaqachon baholagansiz.")
            return
        send(chat_id, f"⭐ {book['name']}\n\nKitobga baho bering:", rating_keyboard(order_id, book_id))
        return

    if data.startswith("rate_"):
        parts = data.split("_")
        if len(parts) != 4:
            return
        order_id, book_id, stars = parts[1], parts[2], parts[3]
        if not stars.isdigit() or not 1 <= int(stars) <= 5:
            return
        order = orders.get(order_id)
        book = find_book(book_id)
        if not order or not book or int(order.get("chat_id", -1)) != int(chat_id) or order.get("status") != "shipped":
            send(chat_id, "❌ Bu baholash amal qilish muddati tugagan yoki buyurtma sizniki emas.")
            return
        if user_has_rated(chat_id, order_id, book_id):
            send(chat_id, "⭐ Bu kitobni allaqachon baholagansiz.")
            return
        item = ratings.setdefault(str(order_id), {"chat_id": chat_id, "ratings": {}})
        item["ratings"][str(book_id)] = int(stars)
        save_ratings()
        states[chat_id] = {
            "action": "review_text",
            "order_id": str(order_id),
            "book_id": str(book_id),
            "book_name": book["name"]
        }
        send(
            chat_id,
            f"✅ {book['name']} uchun {stars}⭐ baho qabul qilindi.\n\n"
            "💬 Kitob haqida qisqa fikringizni yozing.",
            {"inline_keyboard": [[
                {"text": "⏭ Fikr yozmaslik", "callback_data": "review_skip"}
            ]]}
        )
        return

    if data == "review_skip":
        state = states.get(chat_id)
        if state and state.get("action") == "review_text":
            states.pop(chat_id, None)
        send(chat_id, "Rahmat! ⭐ Bahoyingiz saqlandi.", main_menu(chat_id))
        return

    # =========================
    # BOOK DETAIL
    # =========================
    # BOOK -> DETAIL
    # =========================
    if data.startswith("book_"):
        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)
        if not book:
            send(chat_id, "❌ Kitob topilmadi.")
            return
        send_book_detail(chat_id, book)
        return

    # Eski xabarlardagi “Hozir sotib olish” tugmasi ham xavfsiz tarzda
    # savatga qo‘shish oqimiga o‘tadi.
    if data.startswith("fastbuy_") or data.startswith("addcart_"):
        try:
            book_id = int(data.split("_", 1)[1])
        except (ValueError, IndexError):
            return

        book = find_book(book_id)
        if not book or int(book.get("stock", 0)) <= 0 or int(book.get("price", 0)) <= 0:
            send(chat_id, "❌ Bu kitob hozircha mavjud emas.")
            return

        cart = carts.setdefault(chat_id, {})
        current = int(cart.get(book_id, 0))
        if current >= int(book["stock"]):
            send(chat_id, f"❌ Omborda faqat {book['stock']} ta bor.")
            return

        cart[book_id] = current + 1
        total_quantity = cart_quantity(cart)
        books_total = 0
        for cart_book_id, qty in cart.items():
            cart_book = find_book(cart_book_id)
            if cart_book:
                books_total += effective_price(cart_book) * int(qty)

        delivery_fee = delivery_fee_for_cart(cart)
        grand_total = books_total + delivery_fee
        if delivery_fee == 0:
            delivery_note = "🎁 4+ kitob aksiyasi qo‘llandi — yetkazib berish BEPUL!"
        else:
            delivery_note = "ℹ️ 4 ta yoki undan ko‘p kitob olsangiz, yetkazib berish bepul."

        send(
            chat_id,
            f"✅ {book['name']} xaridga qo‘shildi.\n\n"
            f"🛒 Savatda: {total_quantity} ta kitob\n"
            "━━━━━━━━━━━━━━\n"
            f"💰 Kitoblar narxi: ₩{books_total:,}\n"
            f"🚚 Yetkazib berish: {delivery_text(delivery_fee)}\n"
            "⏱ Yetkazish muddati: 1–3 ish kuni\n"
            f"💳 JAMI TO‘LOV: ₩{grand_total:,}\n"
            "━━━━━━━━━━━━━━\n"
            f"{delivery_note}\n\n"
            "Endi nima qilasiz? 👇",
            {
                "inline_keyboard": [
                    [{"text": "📚 Yana kitob tanlash", "callback_data": "books"}],
                    [{"text": "✅ Buyurtma berish", "callback_data": "cart_order"}],
                ]
            }
        )
        return

    if data.startswith("adminorder_"):
        if not is_admin(chat_id): return
        order = orders.get(data.split("_",1)[1])
        if not order:
            send(chat_id, "❌ Buyurtma topilmadi.")
            return
        kb = admin_order_status_keyboard(order["order_id"], order.get("status"))
        send(chat_id, admin_order_detail(order), kb or admin_menu())
        return

    # =========================
    # ADMIN: DELETE ORDER FROM BOT LIST
    # =========================

    if data.startswith("deleteorder_confirm_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("deleteorder_confirm_", 1)[1]
        order_key = order_id if order_id in orders else next(
            (k for k, o in orders.items() if str(o.get("order_id")) == str(order_id)),
            None
        )
        order = orders.get(order_key) if order_key is not None else None
        if not order:
            send(chat_id, "ℹ️ Buyurtma allaqachon o‘chirilgan.", admin_orders_keyboard("all"))
            return
        number = display_order_number(order)
        name = order.get("name", "Noma’lum")
        # Faqat botning orders ro‘yxatidan olib tashlaymiz.
        # Ombor, moliya va statistika bo‘yicha alohida qaytarish/amallar bajarilmaydi.
        orders.pop(order_key, None)
        save_orders()
        send(chat_id, f"🗑 №{number} | {name} — buyurtmalar ro‘yxatidan o‘chirildi.", admin_orders_keyboard("all"))
        return

    if data.startswith("deleteorder_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("deleteorder_", 1)[1]
        order = orders.get(order_id) or next(
            (o for o in orders.values() if str(o.get("order_id")) == str(order_id)),
            None
        )
        if not order:
            send(chat_id, "❌ Buyurtma topilmadi.", admin_orders_keyboard("all"))
            return
        send(
            chat_id,
            f"⚠️ №{display_order_number(order)} | {order.get('name','Noma’lum')} buyurtmasini ro‘yxatdan o‘chirasizmi?\n\n"
            "Bu faqat botdagi Buyurtmalar ro‘yxatidan olib tashlaydi. Ombor va statistika qayta o‘zgarmaydi.",
            {"inline_keyboard": [
                [{"text":"🗑 Ha, o‘chirish", "callback_data":f"deleteorder_confirm_{order_id}"}],
                [{"text":"⬅️ Ortga", "callback_data":f"adminorder_{order_id}"}],
            ]}
        )
        return

    # =========================
    # ADMIN: REQUEST CUSTOMER EDIT
    # =========================

    if data.startswith("editrequest_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order:
            send(chat_id, "❌ Zakaz topilmadi.")
            return
        if str(order.get("source") or "telegram") != "telegram":
            send(chat_id, "⚠️ Tahrirlash so‘rovi faqat Telegram bot mijoziga yuboriladi.", admin_order_status_keyboard(order_id, order.get("status")))
            return
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat <= 0:
            send(chat_id, "❌ Mijoz Telegram chat ID topilmadi.", admin_order_status_keyboard(order_id, order.get("status")))
            return
        states[chat_id] = {"action": "order_edit_request", "order_id": order_id}
        send(
            chat_id,
            f"✏️ Buyurtma №{display_order_number(order)} uchun mijozga yuboriladigan kamchilikni yozing.\n\n"
            "Masalan: Manzilni to‘liq yubormagansiz, iltimos xona raqami bilan qayta yuboring.",
            {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
        )
        return

    # =========================
    # ADMIN: ACCEPT ORDER
    # =========================

    if data.startswith("accept_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order:
            send(chat_id, "❌ Zakaz topilmadi.")
            return
        if order.get("status") != "pending":
            send(chat_id, "⚠️ Bu zakaz allaqachon qayta ishlangan.")
            return
        try:
            _cloud_set_order_status(order, "accepted")
        except Exception as first_error:
            # Buyurtma yaratish paytida cloudga yozish vaqtincha ishlamagan bo‘lsa,
            # "Qabul qilish" tugmasi Buyurtma topilmadi xatosida qolib ketmasin.
            # Avval cloud orderni yaratib, omborni aynan bir marta rezerv qilamiz,
            # so‘ng accepted holatiga o‘tkazamiz.
            if not str(order.get("cloud_order_id") or "").strip():
                try:
                    cloud_result = cloud_bridge.create_order(order, preserve_stock=False)
                    if isinstance(cloud_result, dict) and cloud_result.get("id"):
                        order["cloud_order_id"] = str(cloud_result["id"])
                        order["source"] = "telegram"
                        order["stock_reserved"] = True
                        _apply_cloud_stocks(cloud_result.get("stocks"))
                        orders[order_id] = order
                        save_orders()
                    _cloud_set_order_status(order, "accepted")
                except Exception as retry_error:
                    send(chat_id, f"❌ Buyurtma qabul qilinmadi: {retry_error}")
                    return
            else:
                send(chat_id, f"❌ Buyurtma qabul qilinmadi: {first_error}")
                return
        order["status"] = "accepted"
        save_orders()
        refresh_books()
        for book_id in order.get("cart", {}):
            book = find_book(book_id)
            if not book:
                continue
            remaining = int(book.get("stock", 0))
            if remaining == 0:
                send(chat_id, f"❌ OMBORDA TUGADI: {book['name']}")
            elif remaining <= LOW_STOCK_LIMIT:
                send(chat_id, f"⚠️ KAM QOLDI: {book['name']} — {remaining} ta")
        send(
            chat_id,
            f"✅ Buyurtma №{display_order_number(order)} qabul qilindi.\n\n📦 Ombor bot va programmada bir xil yangilandi.",
            admin_order_status_keyboard(order_id, "accepted")
        )
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0 and str(order.get("source") or "telegram") != "app":
            send(
                customer_chat,
                "✅ BUYURTMANGIZ QABUL QILINDI!\n\n" + order_receipt_text(order) +
                "\n\n📦 Kitoblaringiz pochtaga topshirilganda sizga alohida xabar yuboriladi.",
                main_menu(customer_chat)
            )
        return

    # =========================
    # ADMIN: SHIPPED
    # =========================

    if data.startswith("ship_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order or order.get("status") not in ("accepted", "paid"):
            send(chat_id, "⚠️ Avval buyurtmani qabul qiling.")
            return
        try:
            _cloud_set_order_status(order, "shipped")
        except Exception as e:
            send(chat_id, f"❌ Holat yangilanmadi: {e}")
            return
        order["status"] = "shipped"
        save_orders()
        send(chat_id, f"🚚 Buyurtma №{display_order_number(order)} jo‘natildi.", admin_order_status_keyboard(order_id, "shipped"))
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0 and str(order.get("source") or "telegram") != "app":
            send(
                customer_chat,
                "🚚 Kitobingiz jo‘natildi!\n\n"
                "📦 Buyurtmangiz 1–3 ish kunida yetib boradi.\n\n"
                "Xaridingiz uchun rahmat! ❤️",
                main_menu(customer_chat)
            )
        return

    # =========================
    # ADMIN: DELIVERED (legacy button)
    # =========================

    if data.startswith("deliver_"):
        if is_admin(chat_id):
            send(chat_id, "ℹ️ «Yetkazildi» bosqichi olib tashlangan. 🚚 Jo‘natildi — yakuniy holat.", admin_menu())
        return

    # =========================
    # ADMIN: PAYMENT CONFIRMED
    # =========================

    if data.startswith("paid_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order:
            send(chat_id, "❌ Zakaz topilmadi.")
            return
        if order.get("status") not in ("pending", "accepted"):
            send(chat_id, "⚠️ Bu zakaz allaqachon qayta ishlangan.")
            return
        try:
            _cloud_set_order_status(order, "paid")
        except Exception as e:
            send(chat_id, f"❌ Ombor yangilanmadi: {e}")
            return
        order["status"] = "paid"
        save_orders()
        refresh_books()
        for book_id in order.get("cart", {}):
            book = find_book(book_id)
            if not book:
                continue
            remaining = int(book.get("stock", 0))
            if remaining == 0:
                send(chat_id, f"❌ OMBORDA TUGADI: {book['name']}")
            elif remaining <= LOW_STOCK_LIMIT:
                send(chat_id, f"⚠️ KAM QOLDI: {book['name']} — {remaining} ta")
        send(
            chat_id,
            f"✅ Zakaz №{order_id} to‘lov qilindi deb belgilandi.\n\n📦 Ombor bot va programmada bir xil yangilandi.",
            admin_order_status_keyboard(order_id, "paid")
        )
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0:
            send(
                customer_chat,
                "✅ BUYURTMANGIZ QABUL QILINDI!\n\n" + order_receipt_text(order) +
                "\n\n📦 Kitoblaringiz pochtaga topshirilganda sizga alohida xabar yuboriladi.",
                main_menu(customer_chat)
            )
        return

    # =========================
    # ADMIN: ORDER CANCEL
    # =========================

    if data.startswith("cancelorder_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order:
            send(chat_id, "❌ Zakaz topilmadi.")
            return
        if order.get("status") not in ("pending", "accepted"):
            send(chat_id, "⚠️ Bu zakaz allaqachon qayta ishlangan.")
            return
        try:
            _cloud_set_order_status(order, "cancelled")
        except Exception as e:
            send(chat_id, f"❌ Bekor qilinmadi: {e}")
            return
        order["status"] = "cancelled"
        save_orders()
        send(chat_id, "❌ Zakaz bekor qilindi.", admin_menu())
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0:
            send(
                customer_chat,
                "❌ Zakaz bekor qilindi.\n\nAgar xatolik bo‘lsa, admin bilan bog‘laning.",
                main_menu(customer_chat)
            )
        return




# =========================
# TEZKOR APP BUYURTMA XABARI
# =========================

ORDER_NOTIFY_SECRET = os.environ.get("ORDER_NOTIFY_SECRET", "").strip()
ORDER_NOTIFY_PORT = int(os.environ.get("PORT", "8080") or 8080)

class _OrderNotifyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_HEAD(self):
        if not mini_app.serve(self, TOKEN):
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if mini_app.serve(self, TOKEN):
            return
        if self.path == "/health":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if mini_app.serve(self, TOKEN):
            return
        if self.path != "/notify-order":
            self.send_response(404)
            self.end_headers()
            return
        supplied = str(self.headers.get("X-Muhajeer-Order-Secret") or "").strip()
        if not ORDER_NOTIFY_SECRET or supplied != ORDER_NOTIFY_SECRET:
            self.send_response(401)
            self.end_headers()
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if str(payload.get("source") or "") != "app":
                self.send_response(204)
                self.end_headers()
                return
            order_no = int(payload.get("order_number") or 0)
            name = str(payload.get("customer_name") or "—").strip()
            phone = str(payload.get("phone") or "—").strip()
            address = str(payload.get("address") or "—").strip()
            total = int(payload.get("total") or 0)
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            lines = []
            for item in items[:30]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("name") or "Kitob").strip()
                qty = max(1, int(item.get("quantity") or item.get("qty") or 1))
                lines.append(f"• {title} × {qty}")
            label = f"#{order_no}" if order_no > 0 else "Yangi"
            text = (
                f"🚨 YANGI ILOVA BUYURTMASI {label}\n\n"
                f"👤 {name}\n📱 {phone}\n📍 {address}\n\n"
                f"📚 " + ("\n".join(lines) if lines else "Kitob ma’lumoti yo‘q") +
                f"\n\n💰 Jami: ₩{total:,}\n\n"
                "⚡ Ilovadan yangi zakas tushdi."
            )
            if ADMIN_ID:
                send(int(ADMIN_ID), text)
            self.send_response(200)
            body = b'{"ok":true}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            print("Tezkor zakas xabari xatosi:", exc)
            self.send_response(500)
            self.end_headers()

def _start_order_notify_server():
    if not ORDER_NOTIFY_SECRET:
        print("ORDER_NOTIFY_SECRET sozlanmagan; tezkor app zakas webhook o‘chiq.")
    server = ThreadingHTTPServer(("0.0.0.0", ORDER_NOTIFY_PORT), _OrderNotifyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Tezkor zakas webhook port {ORDER_NOTIFY_PORT} da tayyor.")


# =========================
# MAIN
# =========================

def main():
    if not TOKEN:
        raise Exception("BOT_TOKEN sozlanmagan!")

    load_books()
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()
    _start_order_notify_server()
    mini_app.start(api, {"name": BANK_NAME, "number": CARD_NUMBER, "owner": CARD_OWNER},
                   DATA_DIR, register_mini_app_user)

    offset = None

    while True:
        try:
            params = {"timeout": 50}

            if offset is not None:
                params["offset"] = offset

            result = api("getUpdates", params)

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    if "message" in update:
                        handle_message(update["message"])
                    elif "callback_query" in update:
                        handle_callback(update["callback_query"])
                except Exception as update_error:
                    # Bitta yaroqsiz xabar qolgan xabarlarni to‘xtatmasin.
                    print("Telegram update qayta ishlash xatosi:", update.get("update_id"), update_error)

            sync_app_order_status_notifications()
            # Eski mijoz menyusiga olib boradigan avtomatik reklama
            # xabarlari endi yuborilmaydi.

        except Exception as e:
            print("Xato:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
# Advanced admin statistics enabled
