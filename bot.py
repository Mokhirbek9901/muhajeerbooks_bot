import os
import time
import json
import urllib.request
import urllib.parse
import random
import io

from datetime import datetime, timedelta

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
LOW_STOCK_LIMIT = 2

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


# =========================
# TELEGRAM API
# =========================

def api(method, data=None):
    if data is None:
        data = {}

    encoded = urllib.parse.urlencode(data).encode()

    request = urllib.request.Request(
        f"{API}/{method}",
        data=encoded
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


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


def create_backup():
    """Botning barcha doimiy ma'lumotlarini bitta JSON faylga yig'adi."""
    refresh_books()
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()
    return json.dumps({
        "backup_version": 1,
        "created_at": datetime.now().isoformat(),
        "books": books,
        "orders": orders,
        "users": users,
        "favorites": favorites,
        "ratings": ratings,
        "restock_subscribers": restock_subscribers
    }, ensure_ascii=False, indent=2)


def restore_backup_file(path):
    """Backup JSONni tekshiradi va barcha doimiy ma'lumotlarni qayta tiklaydi."""
    global books, orders, users, favorites, ratings, restock_subscribers

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        raise ValueError("Backup fayli noto'g'ri yoki eski formatda.")

    restored = {
        "orders": data.get("orders", {}),
        "users": data.get("users", {}),
        "favorites": data.get("favorites", {}),
        "ratings": data.get("ratings", {}),
        "restock_subscribers": data.get("restock_subscribers", {})
    }

    # Avval vaqtinchalik fayllarga yozamiz. Hammasi muvaffaqiyatli bo'lsa almashtiramiz.
    payloads = {
        BOOKS_FILE: data["books"],
        ORDERS_FILE: restored["orders"],
        USERS_FILE: restored["users"],
        FAVORITES_FILE: restored["favorites"],
        RATINGS_FILE: restored["ratings"],
        RESTOCK_FILE: restored["restock_subscribers"]
    }

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

    load_books()
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()

    # Backup tiklangandan keyin eski foydalanuvchi sessiyalari va savatchalari
    # yangi ma'lumotlar bilan aralashib ketmasligi uchun tozalanadi.
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

    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            books = json.load(f)
    except Exception:
        books = DEFAULT_BOOKS[:]

    changed = False

    # GitHub orqali qo‘shilgan kitob: mavjud bo‘lmasa bir marta omborga qo‘shiladi.
    if not any(str(b.get("name", "")).strip().casefold() == "assasin" for b in books):
        next_id = max(
            [int(b.get("id", 0)) for b in books if str(b.get("id", "")).isdigit()],
            default=0
        ) + 1
        books.append({
            "id": next_id,
            "name": "Assasin",
            "price": 17000,
            "stock": 3,
            "category": "Boshqalar",
            "author": "Ko‘rsatilmagan",
            "description": "Ma’lumot kiritilmagan.",
            "old_price": 0,
            "photo_id": "",
            "cover": "Yumshoq",
            "recommended": False,
            "created_at": datetime.now().isoformat()
        })
        changed = True

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
        if o.get("status") in ("paid", "shipped", "delivered"):
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
    lines += ["", f"💰 Kitoblar: ₩{total:,}", f"🚚 Yetkazib berish: ₩{delivery:,}"]
    if discount:
        lines.append(f"🎁 Chegirma: ₩{discount:,}")
    lines += [f"💵 JAMI: ₩{grand:,}", "", f"Holati: {status_name(order.get('status'))}"]
    return "\n".join(lines)


def status_name(status):
    return {
        "pending": "🟡 To‘lov kutilmoqda",
        "paid": "🟢 To‘lov tasdiqlangan",
        "shipped": "🚚 Jo‘natildi",
        "delivered": "✅ Yetkazildi",
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
    photo_id = book.get("photo_id", "")
    if photo_id:
        try:
            api("sendPhoto", {"chat_id": chat_id, "photo": photo_id, "caption": text, "reply_markup": json.dumps(markup, ensure_ascii=False)})
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
            [{"text": "📍 Manzil", "callback_data": "orderedit_address"},
             {"text": "🛒 Savat", "callback_data": "orderedit_cart"}],
            [{"text": "✅ Buyurtmani tasdiqlash", "callback_data": "order_confirm_cb"}],
            [{"text": "❌ Bekor qilish", "callback_data": "order_cancel_cb"}],
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
            [discount_button],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],
            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],
            [{"text": "🧪 Random xabarni sinash"}],
            [{"text": "💾 Backup"}, {"text": "📥 Backup tiklash"}],
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
            return datetime.fromisoformat(raw)
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
    if name and phone and address:
        return {"name": name, "phone": phone, "address": address}
    return None


def cart_text(chat_id):
    cart = carts.get(chat_id, {})
    if not cart:
        return "🛒 Savatcha bo‘sh."
    lines = []
    total = 0
    for book_id, qty in cart.items():
        book = find_book(book_id)
        if not book:
            continue
        subtotal = effective_price(book) * int(qty)
        total += subtotal
        lines.append(f"📖 {book['name']} × {qty} = ₩{subtotal:,}")
    fee = delivery_fee_for_cart(cart)
    grand_total = total + fee
    bonus = (
        "\n🎁 Aksiya qo‘llandi: 4 ta yoki undan ko‘p kitob — yetkazib berish bepul!"
        if fee == 0
        else "\nℹ️ 4 ta yoki undan ko‘p kitob xarid qilsangiz, yetkazib berish bepul."
    )
    return (
        "🛒 Savatchangiz:\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Kitoblar jami: ₩{total:,}"
        + f"\n🚚 Yetkazib berish: {delivery_text(fee)}"
        + bonus
        + f"\n💵 JAMI TO‘LOV: ₩{grand_total:,}"
    )


def cart_keyboard(chat_id):
    cart = carts.get(chat_id, {})

    if not cart:
        return {
            "inline_keyboard": [
                [{"text": "📚 Kitoblar", "callback_data": "books"}],
                [{"text": "🏠 Bosh menyu", "callback_data": "home"}]
            ]
        }

    buttons = []

    for book_id, qty in list(cart.items()):
        book = find_book(book_id)

        if not book:
            continue

        stock = int(book.get("stock", 0))

        buttons.append([
            {"text": "➖", "callback_data": f"cartminus_{book_id}"},
            {"text": f"{qty} ta", "callback_data": "cart_noop"},
            {"text": "➕", "callback_data": f"cartplus_{book_id}"},
        ])

        buttons.append([
            {"text": f"🗑 {book['name']}ni o‘chirish",
             "callback_data": f"cartdelete_{book_id}"}
        ])

    buttons.append([
        {"text": "🗑 Barchasini tozalash", "callback_data": "cartclear"}
    ])

    # Savatchaning o‘zidan turib buyurtmani boshlash.
    buttons.append([
        {"text": "📦 Zakaz berish", "callback_data": "cart_order"}
    ])

    buttons.append([
        {"text": "📚 Kitoblar", "callback_data": "books"},
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


def edit_book_menu():
    refresh_books()
    buttons = []

    for b in books:
        buttons.append([
            {
                "text": f"✏️ {b['name']}",
                "callback_data": f"edit_{b['id']}"
            }
        ])

    buttons.append([
        {"text": "⬅️ Admin panel", "callback_data": "admin"}
    ])

    return {"inline_keyboard": buttons}


def delete_book_menu():
    refresh_books()
    buttons = []

    for b in books:
        buttons.append([
            {
                "text": f"🗑 {b['name']}",
                "callback_data": f"delete_{b['id']}"
            }
        ])

    buttons.append([
        {"text": "⬅️ Admin panel", "callback_data": "admin"}
    ])

    return {"inline_keyboard": buttons}


def edit_fields_menu(book_id):
    return {
        "inline_keyboard": [
            [{"text": "✏️ Nomini o‘zgartirish", "callback_data": f"ename_{book_id}"}],
            [{"text": "💰 Narxini o‘zgartirish", "callback_data": f"eprice_{book_id}"}],
            [{"text": "🎁 Eski narx/chegirma", "callback_data": f"eoldprice_{book_id}"}],
            [{"text": "📦 Qoldig‘ini o‘zgartirish", "callback_data": f"estock_{book_id}"}],
            [{"text": "📂 Kategoriyani o‘zgartirish", "callback_data": f"ecat_{book_id}"}],
            [{"text": "📕 Muqovani o‘zgartirish", "callback_data": f"ecover_{book_id}"}],
            [{"text": "✍️ Muallifni o‘zgartirish", "callback_data": f"eauthor_{book_id}"}],
            [{"text": "📄 Tavsifni o‘zgartirish", "callback_data": f"edesc_{book_id}"}],
            [{"text": "📸 Rasmni o‘zgartirish", "callback_data": f"ephoto_{book_id}"}],
            [{"text": "🔥 Tavsiya etilgan ON/OFF", "callback_data": f"erec_{book_id}"}],
            [{"text": "⬅️ Orqaga", "callback_data": "editlist"}],
        ]
    }


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
    free_note = (
        "\n🎁 Aksiya qo‘llandi: 4 ta yoki undan ko‘p kitob — yetkazib berish bepul!"
        if fee == 0
        else "\nℹ️ 4 ta yoki undan ko‘p kitob xarid qilsangiz, yetkazib berish bepul."
    )
    text = (
        "🧾 BUYURTMANGIZ\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Kitoblar: ₩{total:,}"
        + f"\n🚚 Yetkazib berish: {delivery_text(fee)}"
        + free_note
        + f"\n💵 JAMI TO‘LOV: ₩{grand_total:,}"
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
        and str(b.get("photo_id", "")).strip()
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
                    "photo": book["photo_id"],
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


def register_user(chat_id, user):
    key = str(chat_id)
    now = int(time.time())
    old = users.get(key, {})

    users[key] = {
        "chat_id": chat_id,
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "last_active": now,
        "inactive_message_sent": False
    }

    # Mijoz yana foydalansa, avvalgi 30 kunlik eslatma holatini tiklaymiz.
    # Birinchi marta ko‘rinayotgan eski userlarda esa hozirgi vaqtni boshlang‘ich nuqta qilamiz.
    if not old.get("last_active"):
        users[key]["last_active"] = now
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
    q = query.lower().strip()
    result = []
    if not q:
        return result
    for b in books:
        fields = [
            str(b.get("name", "")),
            str(b.get("author", "")),
            str(b.get("category", "")),
            str(b.get("description", ""))
        ]
        if any(q in field.lower() for field in fields):
            result.append(b)
    return result


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
        "paid": "🟢 To‘lov tasdiqlangan",
        "shipped": "🚚 Jo‘natildi",
        "delivered": "✅ Yetkazildi",
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
        if o.get("status") == "delivered":
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
    "pending": "🟡 Kutilmoqda", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "✅ Yetkazilgan",
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
            dt = datetime.fromisoformat(raw)
        except Exception:
            return False
        if period == "today":
            return dt.date() == now.date()
        if period == "week":
            return dt >= now - timedelta(days=7)
        if period == "month":
            return dt.year == now.year and dt.month == now.month
        return True

    selected = [o for o in orders.values() if included(o)]
    paid_statuses = ("paid", "shipped", "delivered")
    successful = [o for o in selected if o.get("status") in paid_statuses]

    pending = sum(1 for o in selected if o.get("status") == "pending")
    paid = sum(1 for o in selected if o.get("status") == "paid")
    shipped = sum(1 for o in selected if o.get("status") == "shipped")
    delivered = sum(1 for o in selected if o.get("status") == "delivered")
    cancelled = sum(1 for o in selected if o.get("status") == "cancelled")
    revenue = sum(int(o.get("grand_total", 0)) for o in successful)
    books_revenue = sum(int(o.get("total", 0)) for o in successful)
    delivery_revenue = sum(int(o.get("delivery_fee", DELIVERY_FEE)) for o in successful)
    avg_order = revenue / len(successful) if successful else 0

    sold = {}
    customer_totals = {}
    for o in successful:
        cid = str(o.get("chat_id"))
        customer_totals[cid] = customer_totals.get(cid, 0) + int(o.get("grand_total", 0))
        for bid, qty in o.get("cart", {}).items():
            sold[int(bid)] = sold.get(int(bid), 0) + int(qty)

    top = sorted(sold.items(), key=lambda x: x[1], reverse=True)[:10]
    top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    label = {"all":"Barcha vaqt", "today":"Bugun", "week":"Oxirgi 7 kun", "month":"Shu oy"}.get(period, "Barcha vaqt")
    lines = [
        f"📊 KUCHLI SAVDO STATISTIKASI — {label}", "",
        f"👥 Bot foydalanuvchilari: {len(users)} ta",
        f"📦 Jami buyurtmalar: {len(selected)} ta",
        f"🟡 To‘lov kutilmoqda: {pending} ta",
        f"💳 To‘langan: {paid} ta",
        f"🚚 Jo‘natilgan: {shipped} ta",
        f"✅ Yetkazilgan: {delivered} ta",
        f"❌ Bekor qilingan: {cancelled} ta", "",
        f"💰 Jami tushum: ₩{revenue:,}",
        f"📚 Kitoblar savdosi: ₩{books_revenue:,}",
        f"🚚 Yetkazib berish: ₩{delivery_revenue:,}",
        f"📈 O‘rtacha buyurtma: ₩{avg_order:,.0f}",
        f"📚 Sotilgan kitoblar: {sum(sold.values())} dona", "",
        "🏆 TOP 10 KITOB:"
    ]

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
        [{"text": f"🟢 To‘langan ({counts['paid']})", "callback_data": "adminorders_paid"}],
        [{"text": f"🚚 Jo‘natilgan ({counts['shipped']})", "callback_data": "adminorders_shipped"}],
        [{"text": f"✅ Yetkazilgan ({counts['delivered']})", "callback_data": "adminorders_delivered"}],
        [{"text": f"❌ Bekor qilingan ({counts['cancelled']})", "callback_data": "adminorders_cancelled"}],
        [{"text": f"⚠️ Ombor muammosi ({counts['stock_problem']})", "callback_data": "adminorders_stock_problem"}],
        [{"text": f"📦 Hammasi ({len(orders)})", "callback_data": "adminorders_all"}],
    ]
    selected = [o for o in orders.values() if status_filter == "all" or o.get("status") == status_filter]
    selected.sort(key=lambda x: int(x.get("order_id", 0)), reverse=True)
    for o in selected[:30]:
        buttons.append([{"text": f"№{o.get('order_id')} — {status_name(o.get('status'))}", "callback_data": f"adminorder_{o.get('order_id')}"}])
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}


def admin_order_detail(order):
    return order_receipt_text(order)


def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "paid":
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    elif status == "shipped":
        buttons.append([{ "text":"✅ Yetkazildi", "callback_data":f"deliver_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}


# =========================
# BUYURTMANI YAKUNLASH
# =========================

def finalize_order(chat_id):
    state = states.get(chat_id)

    if not state or state.get("action") != "order_confirm":
        send(chat_id, "⚠️ Buyurtma tasdiqlash holatida emas.", main_menu(chat_id))
        return

    if not state.get("payment_declared", False):
        send(chat_id, "💳 Avval to‘lovni amalga oshiring va «💳 To‘lov qildim» tugmasini bosing.",
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
                    "unit_price": int(effective_price(book))
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
                + "💳 Mijoz «To‘lov qildim» deb tasdiqladi."
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


def handle_message(message):
    # Har bir yangi xabarda books.json dan eng yangi ombor holatini yuklaymiz.
    # Shu sabab admin qoldiqni o'zgartirgach, boshqa foydalanuvchilar ham yangi sonni ko'radi.
    load_books()
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
                    "unit_price": int(effective_price(book))
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
            "✅ To‘lov cheki qabul qilindi.\n\n"
            + preview + "\n\n" + order_customer_info_text(state)
            + "\n\nMa’lumotlarni tekshirib, buyurtmani tasdiqlang.",
            order_edit_keyboard(state)
        )
        return

    # =========================
    # START
    # =========================

    if text == "/start":
        carts.setdefault(chat_id, {})
        states.pop(chat_id, None)

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

        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return

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
                backup = create_backup()
                send_document(
                    chat_id,
                    "muhajeer_books_backup.json",
                    backup,
                    "💾 Backup tayyor. Shu faylni saqlab qo‘ying. Yangi kod/deploydan keyin ma'lumotlarni tiklash uchun kerak bo‘ladi."
                )
                send(chat_id, "✅ Backup yuborildi. Uni telefoningizga yoki Telegramdagi Saved Messages'ga saqlab qo‘ying.", admin_menu())
            except Exception as e:
                send(chat_id, f"❌ Backup yaratilmadi: {e}", admin_menu())
            return

        if text == "📥 Backup tiklash":
            states[chat_id] = {"action": "restore_backup"}
            send(
                chat_id,
                "📥 Backup tiklash\n\n"
                "Oldin bot bergan `muhajeer_books_backup.json` faylini shu yerga yuboring.\n\n"
                "⚠️ Backup tiklanganda hozirgi kitoblar, buyurtmalar va foydalanuvchilar ma'lumotlari backupdagi holat bilan almashtiriladi.\n\n"
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
                    buttons.append([{ "text":"⬅️ Admin panel", "callback_data":"admin" }])
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
                state["action"] = "add_stock"

                send(
                    chat_id,
                    "📦 Endi qoldiq sonini yozing.\nMasalan: 10"
                )
                return

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
                new_id = max([int(b["id"]) for b in books], default=0) + 1
                new_book = {"id": new_id, "name": state["name"], "price": state["price"], "stock": state["stock"],
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

            if action in ("change_old_price", "change_category", "change_cover", "change_author", "change_description", "change_photo"):
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
            "📞 Bog‘lanish"
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
            "🔎 Kitob nomini yozing.\nMasalan: Yovuz daho"
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
            "📞 Telefon raqamingizni yozing:"
        )
        return

    # =========================
    # ORDER: TELEFON
    # =========================

    if state and state.get("action") == "order_phone":
        state["phone"] = text
        state["action"] = "order_address"

        send(
            chat_id,
            "📍 Yetkazib berish manzilingizni yozing:"
        )
        return

    # =========================
    # ORDER: MANZIL
    # =========================

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
            extra = (
                "\n\n💳 To‘lovingiz belgilandi.\n"
                "⚠️ Ma’lumotlarni tekshirib, «✅ Tasdiqlash» tugmasini bosing."
            )

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
        if text == "❌ Bekor qilish":
            states.pop(chat_id, None)
            send(chat_id, "Buyurtma bekor qilindi.", main_menu(chat_id))
            return
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
    # Callback kelganda ham omborning eng yangi holatini yuklaymiz.
    load_books()
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

    if chat_id is None:
        return

    # Callback ham botdan foydalanish hisoblanadi.
    register_user(chat_id, callback.get("from", {}))

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
            "action": "order_confirm" if saved else "order_name",
            "username": state_user.get("username", ""),
            "chat_id": chat_id,
            "cart": dict(cart),
            "payment_declared": False
        }
        if saved:
            states[chat_id].update(saved)
            preview, total, grand = order_preview_text(states[chat_id])
            states[chat_id]["total"] = total
            states[chat_id]["delivery_fee"] = delivery_fee_for_cart(cart)
            states[chat_id]["grand_total"] = grand
            send(chat_id, "✅ Oldingi ma’lumotlaringiz ishlatildi.\n\n" + preview + "\n\n" + order_customer_info_text(states[chat_id]), order_edit_keyboard(states[chat_id]))
        else:
            send(chat_id, cart_text(chat_id) + "\n\n📝 Buyurtma uchun ismingizni yozing:")
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

        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)

        if book:
            books.remove(book)
            save_books()

            send(
                chat_id,
                f"🗑 O‘chirildi: {book['name']}",
                admin_menu()
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
        states.pop(chat_id, None)
        send(chat_id, "Buyurtma bekor qilindi.", main_menu(chat_id))
        return

    if data == "order_payment_done":
        state = states.get(chat_id)
        if not state or state.get("action") != "order_confirm":
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
            send(chat_id, "💳 Avval «💳 To‘lov qildim» tugmasini bosing.",
                 order_edit_keyboard(state))
            return
        finalize_order(chat_id)
        return

    if data in ("orderedit_name", "orderedit_phone", "orderedit_address"):
        state = states.get(chat_id)
        if not state or "cart" not in state: return
        prompts = {"orderedit_name":"📝 Yangi ismingizni yozing:", "orderedit_phone":"📱 Yangi telefon raqamingizni yozing:", "orderedit_address":"📍 Yangi manzilingizni yozing:"}
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
        if not order or not book or int(order.get("chat_id", -1)) != int(chat_id) or order.get("status") != "delivered":
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
        if not order or not book or int(order.get("chat_id", -1)) != int(chat_id) or order.get("status") != "delivered":
            send(chat_id, "❌ Bu baholash amal qilish muddati tugagan yoki buyurtma sizniki emas.")
            return
        if user_has_rated(chat_id, order_id, book_id):
            send(chat_id, "⭐ Bu kitobni allaqachon baholagansiz.")
            return
        item = ratings.setdefault(str(order_id), {"chat_id": chat_id, "ratings": {}})
        item["ratings"][str(book_id)] = int(stars)
        save_ratings()
        avg, count = book_rating(book_id)
        send(chat_id, f"✅ {book['name']} uchun {stars}⭐ baho qabul qilindi.\n\n⭐ Hozirgi reyting: {avg:.1f}/5 ({count} ta baho)",
             user_orders_keyboard(chat_id))
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

        send(
            chat_id,
            f"✅ {book['name']} xaridga qo‘shildi.\n\n"
            f"🛒 Savatda: {total_quantity} ta kitob\n"
            f"💰 Kitoblar jami: ₩{books_total:,}\n\n"
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
    # ADMIN: SHIPPED
    # =========================

    if data.startswith("ship_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order or order.get("status") != "paid":
            send(chat_id, "⚠️ Buyurtma holati mos emas.")
            return
        order["status"] = "shipped"
        save_orders()
        send(chat_id, f"🚚 Zakaz №{order_id} jo‘natildi.", admin_menu())
        send(order["chat_id"], f"🚚 Zakaz №{order_id} jo‘natildi!\n\nBuyurtmangiz yo‘lda. ❤️", main_menu(order["chat_id"]))
        return

    # =========================
    # ADMIN: DELIVERED
    # =========================

    if data.startswith("deliver_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order or order.get("status") != "shipped":
            send(chat_id, "⚠️ Buyurtma holati mos emas.")
            return
        order["status"] = "delivered"
        save_orders()
        send(chat_id, f"✅ Zakaz №{order_id} yetkazildi deb belgilandi.", admin_menu())
        send(order["chat_id"], f"✅ Zakaz №{order_id} yetkazildi deb belgilandi.\n\nRahmat! ❤️", main_menu(order["chat_id"]))
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

        if order["status"] != "pending":
            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon qayta ishlangan."
            )
            return

        # Eng so‘nggi books.json ni bir marta yuklaymiz.
        # Keyingi tekshiruv va kamaytirish bir xil xotiradagi obyektlar bilan ishlaydi.
        # Shu sabab bir buyurtmada bir nechta kitob bo‘lsa ham oldingi kamaytirish yo‘qolmaydi.
        refresh_books()

        order_books = {}
        for book_id, qty in order["cart"].items():
            book = next(
                (b for b in books if int(b.get("id", -1)) == int(book_id)),
                None
            )

            if not book or int(book.get("stock", 0)) < int(qty):
                order["status"] = "stock_problem"
                save_orders()

                send(
                    chat_id,
                    "❌ Omborda bu zakazni bajarish uchun "
                    "yetarli kitob qolmagan."
                )

                send(
                    order["chat_id"],
                    "❌ Afsuski, zakazingizdagi kitoblardan "
                    "biri qolmagan. Admin siz bilan bog‘lanadi.",
                    main_menu(order["chat_id"])
                )
                return

            order_books[str(book_id)] = book

        # Omborni kamaytirish — barcha kitoblar bitta yuklangan
        # books ro‘yxatida kamaytiriladi.
        for book_id, qty in order["cart"].items():
            book = order_books[str(book_id)]
            book["stock"] = int(book.get("stock", 0)) - int(qty)

        save_books()

        # Kam qoldiq haqida adminni ogohlantirish.
        for book_id, qty in order["cart"].items():
            book = order_books.get(str(book_id))
            if book:
                remaining = int(book.get("stock", 0))
                if remaining == 0:
                    try:
                        send(chat_id, f"❌ OMBORDA TUGADI: {book['name']}")
                    except Exception:
                        pass
                elif remaining <= LOW_STOCK_LIMIT:
                    try:
                        send(chat_id, f"⚠️ KAM QOLDI: {book['name']} — {remaining} ta")
                    except Exception:
                        pass

        order["status"] = "paid"
        save_orders()

        send(
            chat_id,
            f"✅ Zakaz №{order_id} to‘lov qilindi deb belgilandi.\n\n"
            "📦 Ombor yangilandi.",
            admin_order_status_keyboard(order_id, "paid")
        )

        send(
            order["chat_id"],
            f"✅ To‘lovingiz tasdiqlandi!\n\n"
            f"🔢 Zakaz №{order_id}\n"
            f"💵 Jami: ₩{order['grand_total']:,}\n\n"
            "📦 Buyurtmangiz tez orada yuboriladi.\n"
            "Rahmat! ❤️",
            main_menu(order["chat_id"])
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

        if order["status"] != "pending":
            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon qayta ishlangan."
            )
            return

        order["status"] = "cancelled"
        save_orders()

        send(
            chat_id,
            f"❌ Zakaz №{order_id} bekor qilindi.",
            admin_menu()
        )

        send(
            order["chat_id"],
            f"❌ Zakaz №{order_id} bekor qilindi.\n\n"
            "Agar xatolik bo‘lsa, admin bilan bog‘laning.",
            main_menu(order["chat_id"])
        )
        return


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
