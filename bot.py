import os
import time
import json
import shutil
import urllib.request
import urllib.parse
import urllib.error
import random
import io
import re
import subprocess
import cloud_bridge

from datetime import datetime, timedelta
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
# /data VOLUME MIGRATSIYASI
# =========================

MIGRATION_SOURCE_DIR = "."
MIGRATION_FILENAMES = [
    "books.json",
    "orders.json",
    "users.json",
    "favorites.json",
    "ratings.json",
    "restock.json",
]


def migrate_data_to_volume():
    """
    Railwayda /data volume ulanganda, ilgari /app (ephemeral) papkasida
    saqlangan JSON fayllarni bir martalik tarzda /data papkasiga ko'chiradi.

    Qoidalar:
    - Faqat /data haqiqatan mavjud va yozish mumkin bo'lgan katalog bo'lsa ishlaydi.
    - /data dagi mavjud fayllar HECH QACHON qayta yozilmaydi (ustidan yozish yo'q).
    - /app dagi manba fayllar o'chirilmaydi, ular ephemeral saqlash tomonidan
      redeploy vaqtida tabiiy ravishda tozalanadi.
    - Xatolik yuz bersa, funksiya jim tarzda davom etadi (bot ishga tushishiga
      xalaqit bermaydi).
    """
    try:
        if DATA_DIR != "/data" or not os.path.isdir("/data"):
            # Volume ulanmagan (hali ham ephemeral "." ishlatilmoqda) —
            # migratsiya kerak emas.
            return

        if not os.access("/data", os.W_OK):
            print("[Migratsiya] /data yozish uchun mavjud emas, o'tkazib yuborildi.")
            return

        copied = []
        skipped_existing = []
        skipped_missing = []
        errors = []

        for filename in MIGRATION_FILENAMES:
            source_path = os.path.join(MIGRATION_SOURCE_DIR, filename)
            dest_path = os.path.join(DATA_DIR, filename)

            try:
                if os.path.exists(dest_path):
                    # /data da fayl allaqachon bor — ustidan yozmaymiz.
                    skipped_existing.append(filename)
                    continue

                if not os.path.isfile(source_path):
                    # /app da manba fayl topilmadi — o'tkazib yuboriladi.
                    skipped_missing.append(filename)
                    continue

                shutil.copy2(source_path, dest_path)
                copied.append(filename)
            except Exception as file_error:
                errors.append(f"{filename} ({file_error})")

        print(
            "[Migratsiya] /data volume tekshiruvi yakunlandi: "
            f"manba='{os.path.abspath(MIGRATION_SOURCE_DIR)}', "
            f"maqsad='{os.path.abspath(DATA_DIR)}', "
            f"ko'chirildi={len(copied)} {copied}, "
            f"mavjud edi={len(skipped_existing)} {skipped_existing}, "
            f"manbada yo'q={len(skipped_missing)} {skipped_missing}, "
            f"xatoliklar={len(errors)} {errors}"
        )
    except Exception as e:
        # Migratsiya hech qachon botning ishga tushishini to'xtatmasligi kerak.
        print("[Migratsiya] Kutilmagan xato, o'tkazib yuborildi:", e)

# =========================
# FAOL BO'LMAGAN MIJOZLAR
# =========================

INACTIVE_DAYS = 30
INACTIVE_CHECK_INTERVAL = 6 * 60 * 60  # har 6 soatda tekshiriladi
last_inactive_check = 0

INACTIVE_MESSAGES = [
    "🤨 Yo‘qolib ketdingiz-ku?\n\n"
    "Sizni kitoblar orasida ko‘rmay qo‘ydik 😅📚\n\n"
    "🆕 Yangi kitoblar kelgan. Bir ko‘rib qo‘ymaysizmi?",

    "📚 Sizni anchadan beri ko‘rmayapmiz…\n\n"
    "Balki yana bir yaxshi kitob vaqti kelgandir? 👀\n\n"
    "Bir kirib, o‘zingizga bittasini tanlab qo‘ying 😅",

    "👀 Kitob o‘qishga vaqt topilmayaptimi?\n\n"
    "Hech bo‘lmasa bittasini boshlab qo‘yamiz 😅📖\n\n"
    "Balki aynan shu kitob sizga yoqib qolar.",

    "📢 Bizda yangiliklar bor!\n\n"
    "Siz yo‘qligingizda yangi kitoblar kelibdi 😅📚\n\n"
    "Bir kirib, nimalar qo‘shilganini ko‘rib chiqing 😉",

    "😏 Biz sizni unutmadik.\n\n"
    "Lekin kitoblar: «Qachon keladi ekan?» deb kutyapti 😂📚\n\n"
    "Bir ko‘rib qo‘ying, balki bittasi ko‘nglingizni olib qo‘yar.",

    "🫣 Bir savol…\n\n"
    "Oxirgi marta qachon kitob o‘qigansiz? 😂📖\n\n"
    "Balki bugun yana boshlash uchun yaxshi kun bo‘lar?",

    "📚 Kitoblar joyida.\nBot joyida.\n\n"
    "Faqat **siz yo‘qsiz** 😅\n\n"
    "Bir kirib chiqishingizga qarshi emasmiz 😂",

    "🚨 Diqqat!\n\n"
    "Siz o‘qimay yurganingizda kitoblar ko‘payib ketdi 😂📚\n\n"
    "Yangi kelganlarini ko‘rib qo‘ying, keyin «bilmagan ekanman» demang 😏",

    "😅 Bizda kichkina muammo bor…\n\n"
    "Siz uchun kitoblar yig‘ilib qolyapti.\n\n"
    "Endi ularni kim o‘qiydi? 😂📚",

    "👋 Hey, kitobxon!\n\n"
    "Ancha bo‘ldi-ku…\nBalki yana bir kitob bilan do‘stlashish vaqti kelgandir? 📖❤️\n\n"
    "Bizda yangilari ham bor 😉",

    "👀 Sizni qidirib qoldik…\n\n"
    "Kitoblar orasidan topolmadik 😅📚\n\n"
    "Balki o‘zingiz kelib, bir ko‘rib ketarsiz?",

    "😴 Kitoblar ham zerikib qoldi…\n\n"
    "«Bizni qachon o‘qishadi?» deb turishibdi 😂📖\n\n"
    "Keling, bittasini xursand qilamiz.",

    "🤔 Bugun kitob olish uchun bahona qidiryapsizmi?\n\n"
    "Mana bahona: **yangi kitoblar kelgan** 😅📚\n\n"
    "Qolganini o‘zingiz hal qilasiz 😉",

    "📖 Bir paytlar bu botdan kitob izlagan edingiz…\n\n"
    "Biz esa o‘sha paytdan beri yangi kitoblar qo‘shib kelmoqdamiz 😅\n\n"
    "Qani, yana bir qarab qo‘ying.",

    "🫵 Sizga bir kitob topib qo‘yishimiz kerak shekilli 😅\n\n"
    "Chunki shuncha kitob turibdi, siz esa yo‘q 😂📚\n\n"
    "Balki bugun omadli kitobingizni toparmiz?"
]



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

def send(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    return api("sendMessage", data)


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
    return result


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
                "Kitobni ko‘rish uchun botga kiring.",
                book_detail_keyboard(book, int(uid))
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
    lines = ["🧾 BUYURTMA CHEKI", "", f"🔢 Buyurtma №{order.get('order_id')}",
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
    image_url = str(book.get("image_url", "") or "").strip()
    photo_id = str(book.get("photo_id", "") or "").strip()
    # Cloudga ulangan kitobda image_url rasmning yagona haqiqiy manbasi.
    photo = image_url if str(book.get("cloud_id", "") or "").strip() else (image_url or photo_id)
    if photo:
        try:
            api("sendPhoto", {"chat_id": chat_id, "photo": photo, "caption": text, "reply_markup": json.dumps(markup, ensure_ascii=False)})
            return
        except Exception as e:
            print("Rasm yuborish xatosi:", e)
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
    buttons = [
        [{"text": "📚 Kitoblar"}, {"text": "📂 Kategoriyalar"}],
        [{"text": "🔎 Qidirish"}, {"text": "❤️ Sevimlilar"}],
        [{"text": "🔥 Tavsiya etilgan"}, {"text": "🆕 Yangi kitoblar"}],
        [{"text": "🏆 Eng ko‘p sotilgan"}],
        [{"text": "🎯 Menga kitob tanla"}],
        [{"text": "🛒 Savatcha"}, {"text": "📦 Zakaz berish"}],
        [{"text": "📜 Mening buyurtmalarim"}, {"text": "📞 Bog‘lanish"}],
        [{"text": "🔢 Buyurtmani tekshirish"}],
    ]

    if is_admin(chat_id):
        buttons.append([{"text": "⚙️ Admin panel"}])

    return {
        "keyboard": buttons,
        "resize_keyboard": True
    }


def global_discount_active():
    return any("global_discount_base_price" in book for book in books)


def admin_menu():
    discount_button = (
        {"text": "🛑 Chegirmani to‘xtatish"}
        if global_discount_active()
        else {"text": "💸 Chegirma berish"}
    )

    return {
        "keyboard": [
            [{"text": "📚 Kitoblar ro‘yxati"}, {"text": "🔎 Kitob qidirish"}],
            [{"text": "➕ Kitob qo‘shish"}, {"text": "✏️ Kitob tahrirlash"}],
            [{"text": "📦 Ombor"}, {"text": "🗑 Kitob o‘chirish"}],
            [{"text": "⚡ Tezkor qoldiq"}],
            [{"text": "📚 Sotilgan kitoblar"}],
            [{"text": "📷 Instagram savdo"}],
            [{"text": "📦 Zakaslar"}],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],
            [{"text": "📅 Bugungi hisobot"}],
            [{"text": "💰 Moliya"}, {"text": "➕ Xarajat"}],
            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],
            [{"text": "🧪 Random xabarni sinash"}],
            [{"text": "💾 Backup"}, {"text": "📥 Backup tiklash"}],
            [discount_button],
            [{"text": "🏠 Asosiy menyu"}],
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

def inactive_new_books_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🆕 Yangi kitoblarni ko‘rish", "callback_data": "new_books"}]
        ]
    }


def send_inactive_message(chat_id):
    refresh_books()
    candidates = [
        b for b in books
        if int(b.get("stock", 0)) > 0
        and int(b.get("price", 0)) > 0
        and (str(b.get("image_url", "")).strip() if str(b.get("cloud_id", "")).strip() else (str(b.get("image_url", "")).strip() or str(b.get("photo_id", "")).strip()))
    ]

    text = random.choice(INACTIVE_MESSAGES)
    markup = inactive_new_books_keyboard()

    if candidates:
        book = random.choice(candidates)
        try:
            api(
                "sendPhoto",
                {
                    "chat_id": chat_id,
                    "photo": (str(book.get("image_url", "") or "").strip() if str(book.get("cloud_id", "") or "").strip() else str(book.get("image_url", "") or book.get("photo_id", "") or "").strip()),
                    "caption": text,
                    "reply_markup": json.dumps(markup, ensure_ascii=False)
                }
            )
            return True
        except Exception as e:
            print("Faol bo‘lmagan mijozga rasm yuborish xatosi:", chat_id, e)

    try:
        send(chat_id, text, markup)
        return True
    except Exception as e:
        print("Faol bo‘lmagan mijozga xabar yuborish xatosi:", chat_id, e)
        return False


def check_inactive_users(force=False):
    global last_inactive_check

    now = time.time()
    if not force and now - last_inactive_check < INACTIVE_CHECK_INTERVAL:
        return
    last_inactive_check = now

    load_users()
    changed = False
    period = INACTIVE_DAYS * 24 * 60 * 60

    for uid, user in list(users.items()):
        if str(uid) == str(ADMIN_ID):
            continue
        if not isinstance(user, dict):
            continue

        try:
            last_active = float(user.get("last_active", 0) or 0)
        except Exception:
            last_active = 0

        # Agar xabar allaqachon yuborilgan bo‘lsa, keyingi 30 kunni
        # aynan o‘sha xabar yuborilgan vaqtdan hisoblaymiz.
        last_reminder = user.get("inactive_message_sent", 0)
        try:
            last_reminder = float(last_reminder or 0)
        except Exception:
            last_reminder = 0

        reference_time = max(last_active, last_reminder)
        if reference_time <= 0 or now - reference_time < period:
            continue

        # 30 kun o‘tgach yana random xabar yuboriladi.
        # Foydalanuvchi botga kirsa register_user inactive_message_sent=False qiladi.
        if send_inactive_message(int(uid)):
            user["inactive_message_sent"] = int(now)
            changed = True

    if changed:
        save_users()


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
        "inactive_message_sent": False
    })
    users[key] = profile
    save_users()


def admin_users_texts():
    # Telegram bitta xabarda 4096 belgidan oshirmaydi, shuning uchun ro‘yxat
    # katta bo‘lsa uni bir nechta xabarga bo‘lib yuboramiz.
    load_users()
    people = sorted(
        users.items(),
        key=lambda item: (
            str(item[1].get("first_name", "")).lower(),
            str(item[1].get("last_name", "")).lower(),
            str(item[0])
        )
    )

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
        entry = (
            f"\n{number}. 👤 {full_name}\n"
            f"   🔗 {username_text}\n"
            f"   🆔 {telegram_id}\n"
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
        lines.append(
            f"🔢 №{o.get('order_id')} — {status}\n"
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
    return {status: sum(1 for o in orders.values() if o.get("status") == status) for status in ORDER_STATUS_NAMES}

def admin_orders_text(status_filter="all"):
    if not orders:
        return "📦 Hozircha buyurtmalar yo‘q."
    selected = [o for o in orders.values() if status_filter == "all" or o.get("status") == status_filter]
    selected.sort(key=lambda x: int(x.get("order_id", 0)), reverse=True)
    title = "📦 BARCHA BUYURTMALAR" if status_filter == "all" else f"📦 {ORDER_STATUS_NAMES.get(status_filter, status_filter).upper()}"
    lines = [f"{title} — {len(selected)} ta", ""]
    for o in selected[:30]:
        lines.append(f"№{o.get('order_id')} | {o.get('name', 'Noma’lum')} | ₩{int(o.get('grand_total', 0)):,} | {ORDER_STATUS_NAMES.get(o.get('status'), o.get('status'))}")
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
    paid_statuses = ("shipped",)
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
        f"👥 Bot foydalanuvchilari: {len(users)} ta",
        f"📦 Jami buyurtmalar: {len(selected)} ta",
        f"🟡 To‘lov kutilmoqda: {pending} ta",
        f"💳 To‘langan: {paid} ta",
        f"🚚 Jo‘natilgan: {shipped} ta",
        f"❌ Bekor qilingan: {cancelled} ta", "",
        f"💰 Jami tushum: ₩{revenue:,}",
        f"📚 Kitoblar savdosi: ₩{books_revenue:,}",
        f"🚚 Yetkazib berish: ₩{delivery_revenue:,}",
        f"💵 Sotilgan kitoblar tannarxi: ₩{cost_of_goods:,}",
        f"📖 Kitobdan qolgan foyda: ₩{book_profit:,}",
        f"📦 Yangi partiya kitoblar: ₩{inventory_purchases:,}",
        f"📮 Do‘kon hisobidan pochta: ₩{store_postage_expense:,}",
        f"🧾 Boshqa chiqimlar: ₩{other_expenses:,}",
        f"➖ Hisobga kiradigan jami chiqim: ₩{cash_outflow_total:,}",
        f"{'✅ Sof foyda' if net_profit >= 0 else '🔻 Sof zarar'}: {'-' if net_profit < 0 else ''}₩{abs(net_profit):,}",
        f"📈 O‘rtacha buyurtma: ₩{avg_order:,.0f}",
        f"📚 Sotilgan kitoblar: {sum(sold.values())} dona",
        f"👤 Yangi mijozlar: {new_customers} ta",
        f"🔁 Qayta xarid qilganlar: {repeat_customers} ta ({repeat_pct:.1f}%)",
        (f"🏷 Eng ko‘p sotilgan kategoriya: {top_category_name} — {top_category_qty} dona"
         if category_sales else "🏷 Eng ko‘p sotilgan kategoriya: hali sotuv yo‘q"),
        f"🎁 Bepul yetkazishga ketgan: ₩{free_delivery_cost:,} ({len(free_delivery_orders)} ta buyurtma)", "",
        "🏆 TOP 10 KITOB:"
    ]

    if missing_cost_qty:
        lines.insert(lines.index("🏆 TOP 10 KITOB:"), f"⚠️ Tannarxi kiritilmagan sotuv: {missing_cost_qty} dona")

    if top:
        for i, (bid, qty) in enumerate(top, 1):
            b = find_book(bid)
            if b:
                avg, count = book_rating(bid)
                rating = f" | ⭐{avg:.1f}" if count else ""
                lines.append(f"{i}. {b['name']} — {qty} dona{rating}")
    else:
        lines.append("Hali sotuv yo‘q.")

    lines.append("\n👑 ENG KO‘P XARID QILGANLAR:")
    if top_customers:
        for i, (cid, amount) in enumerate(top_customers, 1):
            u = users.get(str(cid), {})
            name = u.get("first_name") or u.get("username") or str(cid)
            lines.append(f"{i}. {name} — ₩{amount:,}")
    else:
        lines.append("Hali xaridorlar yo‘q.")

    low = [b for b in books if 0 < int(b.get("stock", 0)) <= LOW_STOCK_LIMIT]
    empty = [b for b in books if int(b.get("stock", 0)) <= 0]
    lines.append("\n⚠️ KAM QOLGAN:")
    lines.extend([f"• {b['name']} — {int(b['stock'])} ta" for b in low] or ["Kam qolgan kitob yo‘q."])
    lines.append("\n❌ TUGAGAN:")
    lines.extend([f"• {b['name']}" for b in empty] or ["Tugagan kitob yo‘q."])

    return "\n".join(lines)

def admin_orders_keyboard(status_filter="all"):
    counts = admin_order_counts()
    buttons = [
        [{"text": f"🟡 Kutilmoqda ({counts['pending']})", "callback_data": "adminorders_pending"}],
        [{"text": f"📦 Qabul qilingan ({counts['accepted']})", "callback_data": "adminorders_accepted"}],
        [{"text": f"🚚 Jo‘natilgan ({counts['shipped']})", "callback_data": "adminorders_shipped"}],
        [{"text": f"📦 Hammasi ({len(orders)})", "callback_data": "adminorders_all"}],
    ]
    selected = [o for o in orders.values() if status_filter == "all" or o.get("status") == status_filter]
    selected.sort(key=lambda x: int(x.get("order_id", 0)), reverse=True)
    for o in selected[:30]:
        buttons.append([{"text": f"№{o.get('order_id')} — {status_name(o.get('status'))}", "callback_data": f"adminorder_{o.get('order_id')}"}])
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}


def admin_order_detail(order):
    text = order_receipt_text(order)
    if str(order.get("source") or "telegram") == "app":
        return "📱 ILOVADAN ZAKAS — boshqarish faqat ilovada\n\n" + text
    return text


def admin_order_status_keyboard(order_id, status):
    order = orders.get(str(order_id)) or {}
    if str(order.get("source") or "telegram") == "app":
        return []
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"✅ Buyurtmani qabul qilish", "callback_data":f"accept_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status in ("accepted", "paid"):
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
        if status == "accepted":
            buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    # Jo‘natildi — yakuniy bosqich. Yetkazildi tugmasi endi yo‘q.
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}


def _search_key(value):
    """Search text: lowercase, emoji/punctuation ignored, Uzbek apostrophes ignored."""
    value = str(value or "").casefold()
    apostrophes = {"'", "’", "‘", "ʻ", "ʼ", "`", "´"}
    out = []
    for ch in value:
        if ch.isalnum():
            out.append(ch)
        elif ch in apostrophes:
            # o‘g‘irlangan -> ogirlangan, kambag‘al -> kambagal
            continue
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _fuzzy_threshold(value):
    n = len(str(value or "").replace(" ", ""))
    if n <= 3:
        return 0.86
    if n <= 5:
        return 0.74
    return 0.68


def _fuzzy_ratio(a, b):
    a = _search_key(a)
    b = _search_key(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 3 and a in b:
        return 0.98
    if len(b) >= 4 and b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def _instagram_name_key(value):
    return _search_key(value)


def _instagram_fuzzy_matches(query):
    """Instagram savdoda qisqa yoki biroz xato nomdan eng yaqin bitta kitobni tanlaydi."""
    q = _search_key(query)
    if not q:
        return []

    scored = []
    for b in books:
        name_key = _search_key(b.get("name", ""))
        if not name_key:
            continue

        # Qisqa nomlar uchun boshidan mos kelish eng kuchli signal.
        # Masalan: "Yusuf" -> "Yusufning qizi".
        if name_key == q:
            score = 2.0
        elif name_key.startswith(q):
            score = 1.40 - min(0.20, max(0, len(name_key) - len(q)) * 0.004)
        elif q in name_key.split():
            score = 1.25 - min(0.15, max(0, len(name_key) - len(q)) * 0.003)
        elif q in name_key:
            score = 1.15 - min(0.20, max(0, len(name_key) - len(q)) * 0.003)
        elif len(name_key) >= 4 and name_key in q:
            score = 1.05
        else:
            score = _fuzzy_ratio(q, name_key)

        # Bir xil/yaqin nomli dublikatlarda omborda borini afzal ko‘ramiz.
        stock = int(b.get("stock", 0) or 0)
        stock_bonus = min(stock, 20) * 0.0005
        scored.append((score + stock_bonus, b))

    if not scored:
        return []

    scored.sort(key=lambda x: (x[0], int(x[1].get("stock", 0) or 0), -int(x[1].get("id", 0) or 0)), reverse=True)
    best_score, best_book = scored[0]

    # Juda qisqa yoki umuman aloqasiz matnni tasodifiy kitobga bog‘lamaymiz.
    if best_score < _fuzzy_threshold(q):
        return []

    return [best_book]



def _instagram_qty_token(token):
    value = str(token or "").casefold().strip()
    if value.endswith("ta"):
        value = value[:-2].strip()
    if value.startswith("x"):
        value = value[1:].strip()
    if value.endswith("x"):
        value = value[:-1].strip()
    try:
        qty = int(value)
        return qty if qty > 0 else None
    except Exception:
        return None


def _instagram_money_token(token):
    value = str(token or "").strip().replace("₩", "").replace(",", "").replace(".", "").replace(" ", "")
    try:
        amount = int(value)
        return amount if amount > 0 else None
    except Exception:
        return None


def parse_instagram_sale_items(text):
    refresh_books()
    exact = {}
    for b in books:
        exact.setdefault(_instagram_name_key(b.get("name", "")), []).append(b)

    selected = {}
    errors = []

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            errors.append(f"• {line} — soni yozilmagan")
            continue

        qty = _instagram_qty_token(parts[-1])
        query_parts = parts[:-1]
        if qty is None or not query_parts:
            errors.append(f"• {line} — format noto‘g‘ri. Masalan: Dafina 1")
            continue

        query = " ".join(query_parts).strip()
        qkey = _instagram_name_key(query)
        matches = exact.get(qkey, [])
        if len(matches) > 1:
            # Bir xil nomli dublikat bo‘lsa, omborda ko‘proq qolgani olinadi.
            matches = [max(matches, key=lambda b: (int(b.get("stock", 0) or 0), -int(b.get("id", 0) or 0)))]
        if not matches:
            matches = _instagram_fuzzy_matches(query)

        if not matches:
            errors.append(f"• {query} — topilmadi")
            continue

        book = matches[0]
        bid = str(book.get("id"))
        selected[bid] = selected.get(bid, 0) + int(qty)

    if not selected and not errors:
        errors.append("Kitoblar yozilmadi.")

    return selected, errors



def instagram_sale_items_text(cart):
    lines = []
    for bid, qty in cart.items():
        b = find_book(bid)
        name = b.get("name", "Kitob") if b else "Kitob"
        stock = int(b.get("stock", 0)) if b else 0
        lines.append(f"• {name} × {int(qty)}  (omborda {stock} ta)")
    return "\n".join(lines)



def instagram_postage_keyboard():
    return {
        "keyboard": [
            [{"text": "👤 Pochtani mijoz to‘ladi"}, {"text": "🎁 Pochtani men to‘ladim"}],
            [{"text": "❌ Bekor qilish"}]
        ],
        "resize_keyboard": True
    }


def instagram_confirm_keyboard():
    return {
        "keyboard": [
            [{"text": "✅ Savdoni saqlash"}],
            [{"text": "❌ Bekor qilish"}]
        ],
        "resize_keyboard": True
    }


def save_instagram_sale(state):
    refresh_books()
    cart = {str(k): int(v) for k, v in state.get("cart", {}).items()}
    if not cart:
        raise ValueError("Kitoblar tanlanmagan.")

    received_total = int(state.get("received_total", 0) or 0)
    if received_total <= 0:
        raise ValueError("Mijozdan olingan jami summa kiritilmagan.")

    customer_pays_postage = bool(state.get("customer_pays_postage", False))
    delivery_fee = int(DELIVERY_FEE) if customer_pays_postage else 0
    if customer_pays_postage and received_total < delivery_fee:
        raise ValueError("Jami summa pochta pulidan kam bo‘lishi mumkin emas.")

    # Admin pochta to'lasa, mijozdan olingan summa to'liq kitob savdosi.
    # Mijoz pochta to'lasa, faqat o'sha 4,000 won ajratiladi.
    books_total = max(0, received_total - delivery_fee)
    grand_total = received_total

    by_id = {str(b.get("id")): b for b in books}
    for bid, qty in cart.items():
        if qty <= 0:
            raise ValueError("Kitob soni noto‘g‘ri.")
        book = by_id.get(str(bid))
        if not book:
            raise ValueError(f"Kitob topilmadi: ID {bid}")
        if int(book.get("stock", 0)) < int(qty):
            raise ValueError(
                f"{book.get('name')} omborda yetarli emas. "
                f"Hozir {int(book.get('stock', 0))} ta."
            )

    # Instagram savdoda admin kiritgan haqiqiy kitob tushumi asosiy narx.
    # Katalog narxi faqat tushumni kitoblar orasida proporsional taqsimlash uchun
    # ishlatiladi. Agar biror kitob narxi 0 bo‘lsa, teng taqsimlaymiz.
    units = []
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        for _ in range(int(qty)):
            units.append(book)

    catalog_weights = [max(0, int(effective_price(book))) for book in units]
    if not units:
        raise ValueError("Kitoblar tanlanmagan.")
    if any(weight <= 0 for weight in catalog_weights):
        catalog_weights = [1 for _ in units]

    weight_total = max(1, sum(catalog_weights))
    allocated = []
    remainders = []
    used = 0
    for index, weight in enumerate(catalog_weights):
        numerator = int(books_total) * int(weight)
        amount = numerator // weight_total
        allocated.append(amount)
        remainders.append((numerator % weight_total, index))
        used += amount
    for _, index in sorted(remainders, reverse=True)[:max(0, int(books_total) - used)]:
        allocated[index] += 1

    items = []
    for book, unit_price in zip(units, allocated):
        items.append({
            "book_id": str(book.get("id")),
            "name": str(book.get("name", "Kitob")),
            "qty": 1,
            "unit_price": int(unit_price),
            "unit_cost": int(book.get("cost_price", 0) or 0),
        })

    order_id = str(int(time.time() * 1000))
    while order_id in orders or int(order_id) < STATS_RESET_ORDER_ID:
        time.sleep(0.001)
        order_id = str(int(time.time() * 1000))

    order = {
        "order_id": order_id,
        "chat_id": 0,
        "username": "",
        "name": "Instagram savdo",
        "phone": "",
        "address": "Instagram",
        "cart": cart,
        "items": items,
        "total": int(books_total),
        "delivery_fee": int(delivery_fee),
        "grand_total": int(grand_total),
        "discount": 0,
        "status": "shipped",
        "payment_declared": True,
        "receipt_file_id": "",
        "source": "instagram",
        "instagram_received_total": int(received_total),
        "postage_paid_by": "customer" if customer_pays_postage else "admin",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    # Faqat HAMMA tekshiruvdan o'tgandan keyin qoldiq bir marta kamayadi.
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        book["stock"] = int(book.get("stock", 0)) - int(qty)
    save_books()

    orders[order_id] = order
    save_orders()

    # Markaziy bazaga yozish muvaffaqiyatsiz bo'lsa local savdo saqlanib qoladi;
    # sync_wrapper keyingi siklda aynan shu order_id bilan qayta urinadi.
    try:
        cloud_result = cloud_bridge.create_order(order, preserve_stock=True)
        if isinstance(cloud_result, dict) and cloud_result.get("id"):
            cloud_id = str(cloud_result["id"])
            order["cloud_order_id"] = cloud_id
            orders[order_id] = order
            save_orders()
            try:
                cloud_bridge.mark_instagram_order(cloud_id)
            except Exception as mark_error:
                print("Instagram source belgilash xatosi:", mark_error)
    except Exception as e:
        print("Instagram savdoni Supabase'ga yozish xatosi:", e)

    return order

def _sold_book_date(raw):
    try:
        return _local_datetime(raw).strftime("%d.%m.%Y")
    except Exception:
        return "—"


def _local_sold_rows():
    rows = []
    for order in orders.values():
        if not isinstance(order, dict):
            continue
        if str(order.get("status") or "") != "shipped":
            continue
        sold_at = order.get("created_at", "")
        source = str(order.get("source") or "telegram")
        items = order.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("name") or item.get("title") or "Kitob")
                try:
                    qty = max(1, int(item.get("qty") or item.get("quantity") or 1))
                except Exception:
                    qty = 1
                for _ in range(qty):
                    rows.append({"title": title, "source": source, "sold_at": sold_at})
            continue
        for bid, qty_raw in (order.get("cart") or {}).items():
            book = find_book(bid)
            title = str((book or {}).get("name") or "Kitob")
            try:
                qty = max(1, int(qty_raw))
            except Exception:
                qty = 1
            for _ in range(qty):
                rows.append({"title": title, "source": source, "sold_at": sold_at})
    rows.sort(key=lambda row: str(row.get("sold_at") or ""))
    return rows


def admin_sold_books_texts():
    try:
        rows = cloud_bridge.sales_list(5000)
    except Exception as e:
        print("Sotilgan kitoblar cloud tarixi xatosi:", e)
        rows = _local_sold_rows()

    if not rows:
        return ["📚 SOTILGAN KITOBLAR\n\nHozircha sotuv yo‘q."]

    lines = []
    for index, row in enumerate(rows, 1):
        title = str(row.get("title") or "Kitob").strip() or "Kitob"
        date = _sold_book_date(row.get("sold_at"))
        lines.append(f"{index}. {title} ({date})")

    chunks = []
    current = "📚 SOTILGAN KITOBLAR\n\n"
    for line in lines:
        candidate = current + line + "\n"
        if len(candidate) > 3500 and current.strip() != "📚 SOTILGAN KITOBLAR":
            chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


# =========================
# BUYURTMANI YAKUNLASH
# =========================

def finalize_order(chat_id):
    state = states.get(chat_id)

    if not state or state.get("action") != "order_confirm":
        send(chat_id, "⚠️ Buyurtma tasdiqlash holatida emas.", main_menu(chat_id))
        return

    if not state.get("payment_declared", False):
        send(chat_id, "💳 Avval to‘lovni amalga oshiring va «📸 To‘lov chekini yuborish» tugmasini bosing.",
             order_edit_keyboard(state))
        return

    cart = state.get("cart", {})
    if not cart:
        states.pop(chat_id, None)
        carts[chat_id] = {}
        send(chat_id, "🛒 Savat bo‘sh. Buyurtma yaratilmadi.", main_menu(chat_id))
        return

    for book_id, qty in cart.items():
        book = find_book(book_id)
        if not book or int(book.get("stock", 0)) < int(qty):
            states.pop(chat_id, None)
            send(chat_id, "❌ Buyurtmadagi kitoblardan biri hozir yetarli qolmagan.", main_menu(chat_id))
            return

    # To‘lov e’lon qilingan paytdagi summa va narxlarni muzlatib qo‘yamiz.
    # Admin keyin narxni o‘zgartirsa ham shu buyurtma summasi o‘zgarmaydi.
    payment_items = state.get("payment_items", [])
    if not payment_items:
        for book_id, qty in cart.items():
            book = find_book(book_id)
            if book:
                payment_items.append({
                    "book_id": str(book_id),
                    "name": str(book.get("name", "Kitob")),
                    "qty": int(qty),
                    "unit_price": int(effective_price(book)),
                    "unit_cost": int(book.get("cost_price", 0) or 0)
                })

    total = sum(int(item["unit_price"]) * int(item["qty"]) for item in payment_items)
    delivery_fee = delivery_fee_for_cart(cart)
    grand_total = total + delivery_fee

    order_id = str(int(time.time() * 1000))
    while order_id in orders:
        time.sleep(0.001)
        order_id = str(int(time.time() * 1000))

    saved_items = [dict(item) for item in payment_items]

    order = {
        "order_id": order_id,
        "chat_id": chat_id,
        "username": state.get("username", ""),
        "name": state.get("name", ""),
        "phone": state.get("phone", ""),
        "address": state.get("address", ""),
        "cart": {str(k): int(v) for k, v in cart.items()},
        "items": saved_items,
        "total": int(total),
        "delivery_fee": int(delivery_fee),
        "grand_total": int(grand_total),
        "discount": 0,
        "status": "pending",
        "payment_declared": True,
        "receipt_file_id": state.get("receipt_file_id", ""),
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    orders[order_id] = order
    save_orders()

    # Buyurtma bir vaqtning o'zida programma admin paneliga ham tushadi.
    try:
        cloud_result = cloud_bridge.create_order(order, preserve_stock=False)
        if isinstance(cloud_result, dict) and cloud_result.get("id"):
            order["cloud_order_id"] = str(cloud_result["id"])
            order["source"] = "telegram"
            orders[order_id] = order
            save_orders()
    except Exception as e:
        # Local nusxa yo'qolmaydi; sync_wrapper keyingi siklda qayta urinadi.
        print("Telegram buyurtmasini Supabase'ga yozish xatosi:", e)

    # Keyingi buyurtmada mijoz qayta yozmasligi uchun ma’lumotlarni eslab qolamiz.
    profile = users.setdefault(str(chat_id), {})
    profile["saved_name"] = order["name"]
    profile["saved_phone"] = order["phone"]
    profile["saved_address"] = order["address"]
    save_users()

    carts[chat_id] = {}
    states.pop(chat_id, None)

    send(chat_id,
         "✅ BUYURTMANGIZ QABUL QILINDI!\n\n" + order_receipt_text(order) +
         "\n\n💳 To‘lov admin tomonidan tekshiriladi.\n"
         "Tasdiqlangach buyurtma jo‘natish bosqichiga o‘tadi.",
         main_menu(chat_id))

    if ADMIN_ID:
        try:
            # Admin uchun buyurtmani to‘liq ko‘rsatamiz:
            # mijoz ma’lumotlari + Telegram username/ID + qaysi kitoblar
            # va nechta olgani + har bir kitob summasi + yetkazib berish + jami.
            items = []
            for item in order.get("items", []):
                item_name = str(item.get("name", "Kitob"))
                qty = int(item.get("qty", 0))
                unit_price = int(item.get("unit_price", 0))
                subtotal = unit_price * qty
                items.append(
                    f"• {item_name} × {qty} = ₩{subtotal:,}"
                )

            # Eski buyurtmalarda items bo‘lmasligi mumkin.
            # Shunda cart orqali kitob nomlarini tiklaymiz.
            if not items:
                for bid, qty in order.get("cart", {}).items():
                    b = find_book(int(bid))
                    item_name = b["name"] if b else "Kitob"
                    price = effective_price(b) if b else 0
                    subtotal = price * int(qty)
                    items.append(
                        f"• {item_name} × {int(qty)} = ₩{subtotal:,}"
                    )

            username_value = str(order.get("username", "") or "").strip().lstrip("@")
            telegram_line = (
                f"🔗 Telegram: @{username_value}\n"
                if username_value
                else "🔗 Telegram: username yo‘q\n"
            )

            delivery_fee = int(order.get("delivery_fee", DELIVERY_FEE))
            book_total = int(order.get("total", total))
            order_grand_total = int(order.get("grand_total", grand_total))

            admin_text = (
                f"🛒 YANGI BUYURTMA №{order_id}\n\n"
                f"👤 Ism: {order.get('name', '—')}\n"
                f"📱 Telefon: {order.get('phone', '—')}\n"
                f"📍 Manzil: {order.get('address', '—')}\n"
                f"{telegram_line}"
                f"🆔 ID: {order.get('chat_id', '—')}\n\n"
                f"📚 BUYURTMA QILINGAN KITOBLAR:\n"
                + ("\n".join(items) if items else "• Kitob ma’lumoti topilmadi")
                + "\n\n"
                + f"💰 Kitoblar jami: ₩{book_total:,}\n"
                + f"🚚 Yetkazib berish: ₩{delivery_fee:,}\n"
                + f"💵 JAMI TO‘LOV: ₩{order_grand_total:,}\n"
                + "💳 Mijoz to‘lov chekini yubordi."
            )

            send(
                int(ADMIN_ID),
                admin_text,
                admin_order_status_keyboard(order_id, "pending")
            )
            receipt_file_id = str(order.get("receipt_file_id", "") or "")
            if receipt_file_id:
                api("sendPhoto", {
                    "chat_id": int(ADMIN_ID),
                    "photo": receipt_file_id,
                    "caption": f"📸 To‘lov cheki · Buyurtma №{order_id}"
                })
        except Exception as e:
            print("Adminga buyurtma yuborish xatosi:", e)


# =========================
# MESSAGE HANDLER
# =========================

def recommender_interest_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🧠 Psixologiya", "callback_data": "rec_i_psixologiya"}],
            [{"text": "💼 Biznes", "callback_data": "rec_i_biznes"}],
            [{"text": "❤️ Romantika", "callback_data": "rec_i_romantika"}],
            [{"text": "🕵️ Detektiv", "callback_data": "rec_i_detektiv"}],
            [{"text": "🕌 Diniy", "callback_data": "rec_i_diniy"}],
            [{"text": "🏺 Tarix", "callback_data": "rec_i_tarix"}],
            [{"text": "🌱 Rivojlanish", "callback_data": "rec_i_rivojlanish"}],
            [{"text": "🎲 Farqi yo‘q", "callback_data": "rec_i_any"}],
            [{"text": "🏠 Bosh menyu", "callback_data": "home"}]
        ]
    }


def recommender_style_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "😊 Yengil va oson", "callback_data": "rec_s_easy"}],
            [{"text": "🤔 O‘ylantiradigan", "callback_data": "rec_s_think"}],
            [{"text": "🥹 Ta’sirli / hissiy", "callback_data": "rec_s_emotion"}],
            [{"text": "🔥 Hayajonli", "callback_data": "rec_s_exciting"}],
            [{"text": "🎲 Farqi yo‘q", "callback_data": "rec_s_any"}],
            [{"text": "🏠 Bosh menyu", "callback_data": "home"}]
        ]
    }


def recommender_result(chat_id, interest, style):
    interest_map = {
        "psixologiya": ["psixolog", "psixologiya", "ruh", "ong", "shaxsiyat"],
        "biznes": ["biznes", "marketing", "moliya", "iqtisod", "tadbirkor", "startup", "startap"],
        "romantika": ["romant", "sevgi", "muhabbat", "love"],
        "detektiv": ["detektiv", "jinoyat", "sir", "triller", "tergov"],
        "diniy": ["diniy", "islom", "islomiy", "sunniy", "aqida", "fiqh", "hadis", "qur'on", "quron"],
        "tarix": ["tarix", "tarixiy", "urush", "saltanat", "imperiya"],
        "rivojlanish": ["rivojlanish", "motivatsiya", "odat", "o‘zini", "ozini", "self", "success"]
    }
    style_map = {
        "easy": ["oson", "yengil", "hikoya", "qissa", "roman"],
        "think": ["falsafa", "fikr", "tafakkur", "psixolog", "tahlil", "intellekt", "aqida"],
        "emotion": ["sevgi", "muhabbat", "romant", "hayot", "hiss", "ta'sir", "ta’sir"],
        "exciting": ["detektiv", "jinoyat", "sir", "triller", "sarguzasht", "urush"]
    }
    def searchable(book):
        return " ".join([str(book.get("name", "")), str(book.get("author", "")), str(book.get("category", "")), str(book.get("description", ""))]).lower()
    available = [b for b in books if int(b.get("stock", 0)) > 0 and int(effective_price(b)) > 0]
    if not available:
        send(chat_id, "😔 Hozircha omborda mavjud kitoblar yo‘q.", main_menu(chat_id)); return
    iw = interest_map.get(interest, []); sw = style_map.get(style, [])
    scored=[]
    for b in available:
        t=searchable(b); score=0
        if interest != "any": score += sum(5 for w in iw if w in t)
        if style != "any": score += sum(2 for w in sw if w in t)
        if b.get("recommended"): score += 1
        avg,count=book_rating(b.get("id"))
        if count: score += min(float(avg),5.0)*0.2
        scored.append((score,b))
    scored.sort(key=lambda x:(x[0],int(x[1].get("stock",0))), reverse=True)
    matched=[b for score,b in scored if score>0]
    result=(matched[:5] if matched else [b for _,b in scored[:5]])
    buttons=[[{"text":f"📖 {b['name']} — ₩{effective_price(b):,}","callback_data":f"book_{b['id']}"}] for b in result]
    buttons += [[{"text":"🎯 Qayta tanlash","callback_data":"recommend_again"}], [{"text":"🏠 Bosh menyu","callback_data":"home"}]]
    send(chat_id, "🎯 SIZ UCHUN TAVSIYALAR\n\nSiz tanlagan qiziqish va uslubga eng yaqin kitoblar:", {"inline_keyboard":buttons})



FINANCE_PERIOD_LABELS = {
    "today": "Bugun",
    "week": "Shu hafta",
    "month": "Shu oy",
    "all": "Hammasi",
}

FINANCE_EXPENSE_CATEGORIES = {
    "🚚 Pochta": "postage",
    "📚 Yangi partiya kitoblar": "inventory_purchase",
    "📦 Qadoqlash": "packaging",
    "📣 Reklama": "ads",
    "🚕 Transport": "transport",
    "🧾 Boshqa": "other",
}


def finance_report_keyboard():
    return {"inline_keyboard": [
        [{"text": "📅 Bugun", "callback_data": "finance_today"}, {"text": "📆 Shu hafta", "callback_data": "finance_week"}],
        [{"text": "🗓 Shu oy", "callback_data": "finance_month"}, {"text": "📊 Hammasi", "callback_data": "finance_all"}],
        [{"text": "⬅️ Admin panel", "callback_data": "admin"}],
    ]}


def finance_report_text(period="month"):
    period = period if period in FINANCE_PERIOD_LABELS else "month"
    try:
        r = cloud_bridge.finance_report(period)
    except Exception as exc:
        return f"❌ Moliya hisoboti serverdan olinmadi: {exc}"

    def n(key):
        try:
            return int(float(r.get(key, 0) or 0))
        except Exception:
            return 0

    try:
        margin = float(r.get("margin_percent", 0) or 0)
    except Exception:
        margin = 0.0
    postage_note = " (taxmin)" if r.get("postage_is_estimated") else ""
    return "\n".join([
        f"💰 MOLIYA — {FINANCE_PERIOD_LABELS[period].upper()}",
        "━━━━━━━━━━━━━━",
        f"💵 Jami tushum: ₩{n('total_revenue'):,}",
        f"📚 Kitob savdosi: ₩{n('books_revenue'):,}",
        f"🚚 Yetkazish tushumi: ₩{n('delivery_revenue'):,}",
        "",
        f"📦 Kitob tannarxi: ₩{n('cost_of_goods'):,}",
        f"📖 Kitobdan qolgan foyda: ₩{n('book_profit'):,}",
        f"📚 Yangi partiya kitoblar: ₩{n('inventory_purchases'):,}",
        f"📮 Do‘kon hisobidan pochta: ₩{n('store_postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        f"➖ Hisobga kiradigan jami chiqim: ₩{n('cash_outflow_total'):,}",
        "━━━━━━━━━━━━━━",
        f"{'✅ SOF FOYDA' if n('net_profit') >= 0 else '🔻 SOF ZARAR'}: {'-' if n('net_profit') < 0 else ''}₩{abs(n('net_profit')):,}",
        f"📈 Sof marja: {margin:.1f}%",
        "",
        f"📚 Sotilgan kitob: {n('sold_books')} dona",
        f"📦 Jo‘natilgan buyurtma: {n('shipped_orders')} ta",
        "",
        "ℹ️ Sof natija = kitob savdosi − yangi partiya kitoblar − do‘kon hisobidan pochta − boshqa chiqimlar.",
        "Mijoz to‘lagan pochta puli foyda emas; u pochta xarajatini qoplaydi.",
    ])


def finance_expense_category_keyboard():
    return {"keyboard": [
        [{"text": "📚 Yangi partiya kitoblar"}],
        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],
        [{"text": "📣 Reklama"}, {"text": "🚕 Transport"}],
        [{"text": "🧾 Boshqa"}],
        [{"text": "❌ Bekor qilish"}],
    ], "resize_keyboard": True}

def handle_message(message):
    # Har bir yangi xabarda kitoblar va buyurtmalarning eng yangi cloud nusxasini o'qiymiz.
    load_books()
    load_orders()
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    user = message.get("from", {})

    user_full_name = " ".join(
        x for x in [
            user.get("first_name", ""),
            user.get("last_name", "")
        ]
        if x
    ).strip() or "Noma’lum"

    username = user.get("username", "")
    register_user(chat_id, user)

    # =========================
    # ADMIN BACKUP RESTORE
    # =========================
    if message.get("document") and str(chat_id) == str(ADMIN_ID):
        document = message["document"]
        file_name = document.get("file_name", "")
        state_now = states.get(chat_id, {})
        if state_now.get("action") == "restore_backup":
            if not file_name.lower().endswith(".json"):
                send(chat_id, "❌ Faqat .json backup faylini yuboring.", admin_menu())
                return

            restore_path = os.path.join(DATA_DIR, "restore_backup.json")
            try:
                download_telegram_file(document["file_id"], restore_path)
                book_count, order_count, user_count = restore_backup_file(restore_path)
                states.pop(chat_id, None)
                try:
                    os.remove(restore_path)
                except Exception:
                    pass
                send(
                    chat_id,
                    "✅ BACKUP TIKLANDI\n\n"
                    f"📚 Kitoblar: {book_count} ta\n"
                    f"📦 Buyurtmalar: {order_count} ta\n"
                    f"👥 Foydalanuvchilar: {user_count} ta\n\n"
                    "Endi bot ma'lumotlari tiklangan holatda ishlaydi.",
                    admin_menu()
                )
            except Exception as e:
                states.pop(chat_id, None)
                try:
                    if os.path.exists(restore_path):
                        os.remove(restore_path)
                except Exception:
                    pass
                send(chat_id, f"❌ Backup tiklanmadi: {e}", admin_menu())
            return

    state = states.get(chat_id)

    # =========================
    # ADMIN: MOLIYA XARAJATI
    # =========================
    if state and is_admin(chat_id) and state.get("action") in ("finance_expense_category", "finance_expense_amount"):
        if text == "❌ Bekor qilish":
            states.pop(chat_id, None)
            send(chat_id, "Xarajat kiritish bekor qilindi.", admin_menu())
            return

        if state.get("action") == "finance_expense_category":
            category = FINANCE_EXPENSE_CATEGORIES.get(text)
            if not category:
                send(chat_id, "Xarajat turini tugmalardan tanlang.", finance_expense_category_keyboard())
                return
            states[chat_id] = {"action": "finance_expense_amount", "category": category, "category_label": text}
            send(chat_id, f"{text} xarajat summasini yozing (₩).\nMasalan: 12000", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
            return

        if state.get("action") == "finance_expense_amount":
            try:
                amount = int(text.replace(",", "").replace(" ", ""))
                if amount <= 0:
                    raise ValueError
            except Exception:
                send(chat_id, "❌ Summani faqat musbat raqamda yozing. Masalan: 12000")
                return
            try:
                cloud_bridge.add_finance_expense(amount, state.get("category", "other"), state.get("category_label", ""))
            except Exception as exc:
                send(chat_id, f"❌ Xarajat serverga saqlanmadi: {exc}", admin_menu())
                return
            states.pop(chat_id, None)
            send(chat_id, f"✅ Xarajat saqlandi: ₩{amount:,}", admin_menu())
            send(chat_id, finance_report_text("month"), finance_report_keyboard())
            return

    # =========================
    # TO‘LOV CHEKI RASMI
    # =========================
    if state and state.get("action") == "awaiting_receipt":
        if text == "❌ Bekor qilish":
            states.pop(chat_id, None)
            send(chat_id, "Buyurtma bekor qilindi.", main_menu(chat_id))
            return
        photos = message.get("photo", [])
        if not photos:
            send(chat_id, "📸 Iltimos, to‘lov chekining rasmini yuboring.")
            return

        state["receipt_file_id"] = photos[-1]["file_id"]
        payment_items = []
        for book_id, qty in state.get("cart", {}).items():
            book = find_book(book_id)
            if book:
                payment_items.append({
                    "book_id": str(book_id),
                    "name": str(book.get("name", "Kitob")),
                    "qty": int(qty),
                    "unit_price": int(effective_price(book)),
                    "unit_cost": int(book.get("cost_price", 0) or 0)
                })

        if not payment_items:
            states.pop(chat_id, None)
            send(chat_id, "❌ Buyurtmadagi kitob topilmadi. Qaytadan urinib ko‘ring.", main_menu(chat_id))
            return

        total = sum(int(item["unit_price"]) * int(item["qty"]) for item in payment_items)
        fee = delivery_fee_for_cart(state.get("cart", {}))
        state["payment_declared"] = True
        state["payment_items"] = payment_items
        state["payment_total"] = total
        state["payment_grand_total"] = total + fee
        state["total"] = total
        state["delivery_fee"] = fee
        state["grand_total"] = total + fee
        state["action"] = "order_confirm"

        preview, _, _ = order_preview_text(state, show_payment_info=False)
        send(
            chat_id,
            "📸 To‘lov cheki yuborildi.\n\n"
            "⚠️ DIQQAT!\n"
            "Buyurtmani tugatish uchun «✅ Buyurtmani tasdiqlash» tugmasini bosing.\n\n"
            + preview + "\n\n" + order_customer_info_text(state)
            + "\n\nMa’lumotlaringizni tekshirib, buyurtmani tasdiqlang.",
            order_edit_keyboard(state)
        )
        return

    # =========================
    # MIJOZ FIKRI
    # =========================
    if state and state.get("action") == "review_text" and text != "/start":
        review_text = text.strip()
        if len(review_text) < 2:
            send(chat_id, "💬 Iltimos, fikringizni yozing yoki «Fikr yozmaslik»ni bosing.")
            return
        if len(review_text) > 150:
            send(chat_id, "❌ Fikr 150 belgidan oshmasin. Qisqaroq yozing.")
            return

        order_id = str(state.get("order_id"))
        book_id = str(state.get("book_id"))
        profile = users.get(str(chat_id), {})
        customer_name = str(profile.get("first_name", "") or "Mijoz")
        item = ratings.setdefault(order_id, {"chat_id": chat_id, "ratings": {}})
        item.setdefault("reviews", {})[book_id] = {
            "name": customer_name,
            "text": review_text
        }
        save_ratings()
        states.pop(chat_id, None)
        send(chat_id, "✅ Fikringiz uchun rahmat! U kitob sahifasida ko‘rinadi.", main_menu(chat_id))
        return

    # =========================
    # START
    # =========================

    if text == "/start" or text.startswith("/start "):
        carts.setdefault(chat_id, {})
        states.pop(chat_id, None)

        start_payload = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if start_payload.startswith("restock_"):
            try:
                book_id = int(start_payload.split("_", 1)[1])
            except Exception:
                book_id = 0
            book = find_book(book_id) if book_id else None
            if not book:
                send(chat_id, "❌ Kitob topilmadi.", main_menu(chat_id))
                return
            if int(book.get("stock", 0)) > 0 and int(effective_price(book)) > 0:
                send(chat_id, f"✅ {book['name']} hozir sotuvda mavjud.", book_detail_keyboard(book, chat_id))
                return
            subscribe_restock(chat_id, book_id)
            send(
                chat_id,
                f"🔔 {book['name']} qayta kelishi bilan Telegram orqali sizga xabar beraman.",
                main_menu(chat_id),
            )
            return

        send(
            chat_id,
            "Assalomu alaykum! 📚\n\n"
            "Muhaјeer Books botiga xush kelibsiz.",
            main_menu(chat_id)
        )
        return

    # =========================
    # ID
    # =========================

    if text == "/id":
        send(
            chat_id,
            f"Sizning Telegram ID raqamingiz: {chat_id}"
        )
        return

    # =========================
    # ADMIN PANEL
    # =========================

    if text == "/admin" or text == "⚙️ Admin panel":
        if not is_admin(chat_id):
            send(
                chat_id,
                "⛔ Sizda admin huquqi yo‘q.",
                main_menu(chat_id)
            )
            return

        states.pop(chat_id, None)

        send(
            chat_id,
            "⚙️ Admin panel",
            admin_menu()
        )
        return

    # =========================
    # ADMIN AMALLARI
    # =========================

    if is_admin(chat_id):

        if text == "🏠 Asosiy menyu":
            states.pop(chat_id, None)
            send(
                chat_id,
                "Asosiy menyu:",
                main_menu(chat_id)
            )
            return

        if text == "📚 Sotilgan kitoblar":
            states.pop(chat_id, None)
            try:
                messages = admin_sold_books_texts()
                for index, value in enumerate(messages):
                    send(
                        chat_id,
                        value,
                        admin_menu() if index == len(messages) - 1 else None,
                    )
            except Exception as e:
                send(chat_id, f"❌ Sotuv tarixini ochib bo‘lmadi: {e}", admin_menu())
            return

        if text == "📦 Zakaslar":
            states.pop(chat_id, None)
            send(chat_id, "📦 ZAKASLAR\n\nPochta ilovasiga ko‘chirish uchun zakaslarni shu yerda boshqarasiz.", shipping_queue_menu())
            return

        if text == "📋 Barcha zakaslar":
            states.pop(chat_id, None); send_shipping_queue(chat_id, "all"); return
        if text == "🤖 Bot zakaslari":
            states.pop(chat_id, None); send_shipping_queue(chat_id, "telegram"); return
        if text == "📱 Ilova zakaslari":
            states.pop(chat_id, None); send_shipping_queue(chat_id, "app"); return
        if text == "✍️ Qo‘lda kiritilgan":
            states.pop(chat_id, None); send_shipping_queue(chat_id, "manual"); return
        if text == "⬅️ Admin panel":
            states.pop(chat_id, None); send(chat_id, "⚙️ Admin panel", admin_menu()); return
        if text in ("➕ SMS / rasm", "➕ Qo‘lda zakas"):
            states[chat_id] = {"action": "shipping_smart_input"}
            send(
                chat_id,
                "📩 ZAKASNI TEZ KIRITISH\n\n"
                "Instagram yoki boshqa joydan kelgan xabarni BUTUNLIGICHA yuboring.\n"
                "Yoki manzil/zakas screenshotini rasm qilib yuboring.\n\n"
                "Men ism, telefon, manzil va kitoblarni o‘zim ajrataman. "
                "Agar kitob nomi xabarda bo‘lmasa, faqat kitobni alohida so‘rayman.",
                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
            return

        if text == "📷 Instagram savdo":
            states[chat_id] = {"action": "instagram_items"}
            send(
                chat_id,
                "📷 INSTAGRAM SAVDO\n\n"
                "Har qatorga KITOB NOMI + SONINI yozing.\n\n"
                "Masalan:\n"
                "Dafina 1\n"
                "Boy ota kambag‘al ota 2\n\n"
                "Nomda ozgina xato bo‘lsa ham bot topishga harakat qiladi.",
                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
            return

        if text == "💰 Moliya":
            states.pop(chat_id, None)
            send(chat_id, finance_report_text("month"), finance_report_keyboard())
            return

        if text == "➕ Xarajat":
            states[chat_id] = {"action": "finance_expense_category"}
            send(chat_id, "🧾 Xarajat turini tanlang:", finance_expense_category_keyboard())
            return

        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return

        if text == "📅 Bugungi hisobot":
            states.pop(chat_id, None); send(chat_id, daily_admin_report_text(), admin_menu()); return

        if text == "🚚 Pochta xarajati":
            states[chat_id] = {"action":"postage_expense"}; send(chat_id,"📮 Bugun pochtaga sarflagan summani yozing (₩).\nMasalan: 12000\n\nBir kunda bir necha marta kiritsangiz, hammasi qo‘shib hisoblanadi."); return

        if text == "📦 Buyurtmalar":
            states.pop(chat_id, None)
            send(chat_id, admin_orders_text("all"), admin_orders_keyboard("all"))
            return

        if text == "👥 Foydalanuvchilar":
            states.pop(chat_id, None)
            user_messages = admin_users_texts()
            for index, user_message in enumerate(user_messages):
                keyboard = admin_menu() if index == len(user_messages) - 1 else None
                send(chat_id, user_message, keyboard)
            return

        if text == "🧪 Random xabarni sinash":
            states.pop(chat_id, None)
            try:
                if send_inactive_message(chat_id):
                    send(
                        chat_id,
                        "✅ Test xabari yuborildi. 15 ta variantdan bittasi random tanlandi.",
                        admin_menu()
                    )
                else:
                    send(chat_id, "❌ Test xabarini yuborib bo‘lmadi.", admin_menu())
            except Exception as e:
                print("Random test xabari xatosi:", e)
                send(chat_id, f"❌ Test xabarini yuborib bo‘lmadi: {e}", admin_menu())
            return

        if text == "📢 Xabar yuborish":
            states[chat_id] = {"action": "broadcast"}
            send(
                chat_id,
                "📢 Barcha bot foydalanuvchilariga yuboriladigan xabarni yozing.\n\n"
                "❌ Bekor qilish uchun tugmani bosing.",
                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
            return

        if text == "💾 Backup":
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                books_backup = create_books_backup()
                data_backup = create_data_backup()
                send_document(
                    chat_id,
                    f"muhajeer_books_kitoblar_{stamp}.json",
                    books_backup,
                    "📚 KITOBLAR BACKUP — faqat kitoblar, narxlar, qoldiq va kitob ma'lumotlari."
                )
                send_document(
                    chat_id,
                    f"muhajeer_books_malumotlar_{stamp}.json",
                    data_backup,
                    "🗂 MA'LUMOTLAR BACKUP — buyurtmalar, foydalanuvchilar, sevimlilar, reytinglar va xarajatlar."
                )
                send(
                    chat_id,
                    "✅ 2 ta alohida backup fayl yuborildi:\n\n"
                    "1️⃣ 📚 Kitoblar\n"
                    "2️⃣ 🗂 Buyurtmalar va boshqa ma'lumotlar\n\n"
                    "Ikkalasini ham saqlab qo'ying.",
                    admin_menu()
                )
            except Exception as e:
                send(chat_id, f"❌ Backup yaratilmadi: {e}", admin_menu())
            return

        if text == "📥 Backup tiklash":
            states[chat_id] = {"action": "restore_backup"}
            send(
                chat_id,
                "📥 Backup tiklash\n\n"
                "Bot bergan 📚 Kitoblar yoki 🗂 Ma'lumotlar backup JSON fayllaridan birini shu yerga yuboring.\n\n"
                "⚠️ Qaysi backup turi yuborilsa, faqat o'sha bo'lim backupdagi holat bilan almashtiriladi.\n\n"
                "❌ Bekor qilish uchun tugmani bosing.",
                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
            return

        if text == "📚 Kitoblar ro‘yxati":
            send(
                chat_id,
                admin_books_text(),
                admin_menu()
            )
            return

        if text == "🔎 Kitob qidirish":
            states[chat_id] = {"action": "admin_search"}
            send(chat_id, "🔎 Qidiriladigan kitob nomini, muallifini yoki kategoriyasini yozing:\n\n❌ Bekor qilish", {"keyboard":[[{"text":"❌ Bekor qilish"}]],"resize_keyboard":True})
            return

        if text == "⚠️ Kam qolgan":
            states.pop(chat_id,None); send(chat_id,low_stock_admin_text(),low_stock_admin_keyboard()); return

        if text == "⚡ Tezkor qoldiq":
            refresh_books()
            states[chat_id]={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}
            send(chat_id,"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id)); return

        if text == "📦 Ombor":
            lines = ["📦 Ombor qoldig‘i:"]
            total_stock = 0
            total_value = 0

            for b in books:
                stock = int(b.get("stock", 0))
                price = effective_price(b)
                total_stock += stock
                if stock > 0 and price > 0:
                    total_value += stock * price
                lines.append(f"• {b['name']} — {stock} ta")

            lines.append(f"\n📚 JAMI QOLGAN KITOBLAR: {total_stock} ta")
            lines.append(f"💰 OMBORDAGI KITOBLAR QIYMATI: ₩{total_value:,}")

            send(chat_id, "\n".join(lines), admin_menu())
            return
        if text == "💸 Chegirma berish":
            states[chat_id] = {"action": "global_discount"}
            send(
                chat_id,
                "💸 Barcha kitoblarga necha foiz chegirma beramiz?\n\n"
                "Masalan: 10, 20 yoki 25\n\n"
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

            if action == "instagram_items":
                cart, errors = parse_instagram_sale_items(text)
                if errors:
                    send(
                        chat_id,
                        "❌ Ayrim kitoblarni aniqlay olmadim:\n\n" + "\n".join(errors) +
                        "\n\nQaytadan yozing. Masalan:\nDafina 1"
                    )
                    return

                shortages = []
                for bid, qty in cart.items():
                    b = find_book(bid)
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
                books_total = max(0, received - int(DELIVERY_FEE))
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
                    states.pop(chat_id, None)
                    fee = int(order.get("delivery_fee", 0))
                    send(
                        chat_id,
                        f"✅ Instagram savdo saqlandi.\n\n"
                        f"🔢 №{order['order_id']}\n"
                        f"📚 {sum(int(q) for q in order.get('cart',{}).values())} ta kitob\n"
                        f"💵 Mijozdan jami: ₩{int(order.get('grand_total',0)):,}\n"
                        f"🚚 Pochta: {'mijoz to‘ladi' if fee else 'siz to‘ladingiz'}\n"
                        f"📖 Kitob savdosi: ₩{int(order.get('total',0)):,}\n\n"
                        "📦 Ombor yangilandi va savdo statistikaga qo‘shildi.",
                        admin_menu()
                    )
                except Exception as e:
                    send(chat_id, f"❌ Savdo saqlanmadi: {e}\n\nOmbor qayta tekshirildi.", admin_menu())
                    states.pop(chat_id, None)
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

    # =========================
    # CUSTOMER: KITOB TAVSIYACHISI
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
        send(chat_id, "🔢 Buyurtma raqamini yozing. Masalan: 1750000000000\n❌ Bekor qilish uchun tugmani bosing.", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
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
        order = orders.get(text)
        states.pop(chat_id, None)
        if not order or int(order.get("chat_id", -1)) != int(chat_id):
            send(chat_id, "❌ Bunday buyurtma topilmadi.", main_menu(chat_id))
            return
        send(chat_id, f"🧾 BUYURTMA №{text}\n\n{status_name(order.get('status'))}\n💵 Jami: ₩{int(order.get('grand_total',0)):,}", main_menu(chat_id))
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
    # Callback kelganda ham kitoblar va buyurtmalarning eng yangi holatini yuklaymiz.
    load_books()
    load_orders()
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
    except Exception as e:
        print("Callback answer xatosi:", e)


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
            send(chat_id, admin_orders_text("all"), admin_orders_keyboard("all"))
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
        except Exception as e:
            send(chat_id, f"❌ Buyurtma qabul qilinmadi: {e}")
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
            f"✅ Buyurtma №{order_id} qabul qilindi.\n\n📦 Ombor bot va programmada bir xil yangilandi.",
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
        send(chat_id, f"🚚 Buyurtma №{order_id} jo‘natildi.", admin_order_status_keyboard(order_id, "shipped"))
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
        send(chat_id, f"❌ Zakaz №{order_id} bekor qilindi.", admin_menu())
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0:
            send(
                customer_chat,
                f"❌ Zakaz №{order_id} bekor qilindi.\n\nAgar xatolik bo‘lsa, admin bilan bog‘laning.",
                main_menu(customer_chat)
            )
        return



# =========================
# MAIN
# =========================

def main():
    if not TOKEN:
        raise Exception("BOT_TOKEN sozlanmagan!")

    migrate_data_to_volume()

    load_books()
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()

    offset = None

    while True:
        try:
            params = {"timeout": 50}

            if offset is not None:
                params["offset"] = offset

            result = api("getUpdates", params)

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])

                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

            check_inactive_users()

        except Exception as e:
            print("Xato:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
# Advanced admin statistics enabled
