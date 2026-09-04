import os
import time
import json
import urllib.request
import urllib.parse

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()

API = f"https://api.telegram.org/bot{TOKEN}"

# Railway Volume ishlatilsa /data papkasi doimiy saqlanadi
DATA_DIR = "/data" if os.path.isdir("/data") else "."

BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")

# =========================
# TO'LOV MA'LUMOTLARI
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


def save_books():
    with open(BOOKS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            books,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_books():
    global books

    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            books = json.load(f)

    except Exception:
        books = DEFAULT_BOOKS[:]
        save_books()


def save_orders():
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            orders,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_orders():
    global orders

    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)

    except Exception:
        orders = {}
        save_orders()


def is_admin(chat_id):
    return str(chat_id) == ADMIN_ID


def find_book(book_id):
    for book in books:
        if int(book["id"]) == int(book_id):
            return book

    return None


# =========================
# MENYULAR
# =========================

def main_menu(chat_id):
    buttons = [
        [{"text": "📚 Kitoblar"}, {"text": "🛒 Savatcha"}],
        [{"text": "📦 Zakaz berish"}, {"text": "📞 Bog‘lanish"}],
    ]

    if is_admin(chat_id):
        buttons.append([
            {"text": "⚙️ Admin panel"}
        ])

    return {
        "keyboard": buttons,
        "resize_keyboard": True
    }


def admin_menu():
    return {
        "keyboard": [
            [{"text": "📚 Kitoblar ro‘yxati"}],
            [{"text": "➕ Kitob qo‘shish"}, {"text": "✏️ Kitob tahrirlash"}],
            [{"text": "📦 Ombor"}, {"text": "🗑 Kitob o‘chirish"}],
            [{"text": "🏠 Asosiy menyu"}],
        ],
        "resize_keyboard": True
    }


def books_menu():
    buttons = []

    for book in books:
        stock = int(book.get("stock", 0))
        price = int(book.get("price", 0))

        if stock > 0 and price > 0:
            label = (
                f"📖 {book['name']} — "
                f"₩{price:,} ({stock} ta)"
            )

            buttons.append([
                {
                    "text": label,
                    "callback_data": f"book_{book['id']}"
                }
            ])

        else:
            label = (
                f"❌ {book['name']} — "
                f"hozircha mavjud emas"
            )

            buttons.append([
                {
                    "text": label,
                    "callback_data": f"none_{book['id']}"
                }
            ])

    buttons.append([
        {
            "text": "🏠 Bosh menyu",
            "callback_data": "home"
        }
    ])

    return {
        "inline_keyboard": buttons
    }


def order_keyboard():
    return {
        "keyboard": [
            [{"text": "✅ Buyurtmani tasdiqlash"}],
            [{"text": "❌ Bekor qilish"}],
        ],
        "resize_keyboard": True
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


# =========================
# SAVATCHA
# =========================

def cart_text(chat_id):
    cart = carts.get(chat_id, {})

    if not cart:
        return "🛒 Savatcha bo‘sh."

    lines = ["🛒 Savatchangiz:\n"]

    total = 0

    for book_id, qty in cart.items():
        book = find_book(book_id)

        if not book:
            continue

        subtotal = int(book["price"]) * int(qty)

        total += subtotal

        lines.append(
            f"📖 {book['name']} × {qty} = "
            f"₩{subtotal:,}"
        )

    lines.append(
        f"\n💰 Kitoblar jami: ₩{total:,}"
    )

    return "\n".join(lines)
    return "\n".join(lines)


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

    for book_id, qty in cart.items():
        book = find_book(book_id)

        if not book:
            continue

        buttons.append([
            {"text": "➖", "callback_data": f"cartminus_{book_id}"},
            {"text": f"{qty} ta", "callback_data": "cart_noop"},
            {"text": "➕", "callback_data": f"cartplus_{book_id}"},
            {"text": "🗑 O‘chirish", "callback_data": f"cartdelete_{book_id}"}
        ])

    buttons.append([
        {"text": "🗑 Barchasini tozalash", "callback_data": "cartclear"}
    ])

    buttons.append([
        {"text": "⬅️ Orqaga", "callback_data": "home"}
    ])

    return {"inline_keyboard": buttons}


# =========================
# ADMIN KITOBLAR
# =========================

# =========================
# ADMIN KITOBLAR
# =========================

def admin_books_text():
    if not books:
        return "📚 Hozircha kitob yo‘q."

    lines = ["📚 Kitoblar:"]

    for b in books:
        lines.append(
            f"\n#{b['id']} {b['name']}\n"
            f"💰 ₩{int(b['price']):,}\n"
            f"📦 Qoldiq: {int(b['stock'])} ta"
        )

    return "\n".join(lines)


def edit_book_menu():
    buttons = []

    for b in books:
        buttons.append([
            {
                "text": f"✏️ {b['name']}",
                "callback_data": f"edit_{b['id']}"
            }
        ])

    buttons.append([
        {
            "text": "⬅️ Admin panel",
            "callback_data": "admin"
        }
    ])

    return {
        "inline_keyboard": buttons
    }


def delete_book_menu():
    buttons = []

    for b in books:
        buttons.append([
            {
                "text": f"🗑 {b['name']}",
                "callback_data": f"delete_{b['id']}"
            }
        ])

    buttons.append([
        {
            "text": "⬅️ Admin panel",
            "callback_data": "admin"
        }
    ])

    return {
        "inline_keyboard": buttons
    }


def edit_fields_menu(book_id):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Nomini o‘zgartirish",
                    "callback_data": f"ename_{book_id}"
                }
            ],
            [
                {
                    "text": "💰 Narxini o‘zgartirish",
                    "callback_data": f"eprice_{book_id}"
                }
            ],
            [
                {
                    "text": "📦 Qoldig‘ini o‘zgartirish",
                    "callback_data": f"estock_{book_id}"
                }
            ],
            [
                {
                    "text": "⬅️ Orqaga",
                    "callback_data": "editlist"
                }
            ]
        ]
    }


# =========================
# MIJOZ ZAKAZI
# =========================

def create_order_preview(state):
    lines = []
    total = 0

    for book_id, qty in state["cart"].items():
        book = find_book(book_id)

        if not book:
            continue

        subtotal = int(book["price"]) * int(qty)

        total += subtotal

        lines.append(
            f"📖 {book['name']} × {qty} = "
            f"₩{subtotal:,}"
        )

    grand_total = total + DELIVERY_FEE

    text = (
        "🧾 BUYURTMANGIZ\n\n"
        + "\n".join(lines)
        + "\n\n"
        f"💰 Kitoblar: ₩{total:,}\n"
        f"🚚 택배 +₩{DELIVERY_FEE:,}\n"
        f"💵 JAMI TO‘LOV: ₩{grand_total:,}\n\n"
        "💳 TO‘LOV MA’LUMOTLARI\n"
        f"💳 Karta raqami: {CARD_NUMBER}\n"
        f"🏦 {BANK_NAME}\n"
        f"👤 {CARD_OWNER}\n\n"
        "⚠️ Iltimos, yuqoridagi karta raqamiga "
        "jami summani o‘tkazing.\n\n"
        "To‘lovni amalga oshirgach, "
        "«✅ Buyurtmani tasdiqlash» tugmasini bosing."
    )

    return text, total, grand_total


# =========================
# MESSAGE HANDLER
# =========================

def handle_message(message):
    chat_id = message["chat"]["id"]

    text = message.get("text", "").strip()

    user = message.get("from", {})

    name = " ".join(
        x for x in [
            user.get("first_name", ""),
            user.get("last_name", "")
        ]
        if x
    ).strip() or "Noma’lum"

    username = user.get("username", "")

    state = states.get(chat_id)

    # -------------------------
    # START
    # -------------------------

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

    # -------------------------
    # ID
    # -------------------------

    if text == "/id":
        send(
            chat_id,
            f"Sizning Telegram ID raqamingiz: {chat_id}"
        )

        return

    # -------------------------
    # ADMIN PANEL
    # -------------------------

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
    # ADMIN
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

        if text == "📚 Kitoblar ro‘yxati":

            send(
                chat_id,
                admin_books_text(),
                admin_menu()
            )

            return

        if text == "📦 Ombor":

            lines = ["📦 Ombor qoldig‘i:"]

            for b in books:
                lines.append(
                    f"• {b['name']} — "
                    f"{int(b['stock'])} ta"
                )

            send(
                chat_id,
                "\n".join(lines),
                admin_menu()
            )

            return

        if text == "➕ Kitob qo‘shish":

            states[chat_id] = {
                "action": "add_name"
            }

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

        # -------------------------
        # ADMIN STATES
        # -------------------------

        if state:

            action = state.get("action")

            if action == "add_name":

                state["name"] = text

                state["action"] = "add_price"

                send(
                    chat_id,
                    "💰 Endi narxini yozing.\n"
                    "Masalan: 25000"
                )

                return

            if action == "add_price":

                try:
                    price = int(
                        text.replace(",", "")
                        .replace(" ", "")
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
                    "📦 Endi qoldiq sonini yozing.\n"
                    "Masalan: 10"
                )

                return

            if action == "add_stock":

                try:
                    stock = int(
                        text.replace(",", "")
                        .replace(" ", "")
                    )

                    if stock < 0:
                        raise ValueError

                except ValueError:

                    send(
                        chat_id,
                        "❌ Qoldiq 0 yoki undan katta "
                        "son bo‘lsin."
                    )

                    return

                new_id = max(
                    [int(b["id"]) for b in books],
                    default=0
                ) + 1

                books.append({
                    "id": new_id,
                    "name": state["name"],
                    "price": state["price"],
                    "stock": stock
                })

                save_books()

                states.pop(chat_id, None)

                send(
                    chat_id,
                    f"✅ Kitob qo‘shildi!\n\n"
                    f"📖 {state['name']}\n"
                    f"💰 ₩{state['price']:,}\n"
                    f"📦 {stock} ta",
                    admin_menu()
                )

                return

            if action in (
                "rename",
                "change_price",
                "change_stock"
            ):

                book = find_book(
                    state["book_id"]
                )

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

                    msg = (
                        f"✅ Kitob nomi o‘zgartirildi: "
                        f"{text}"
                    )

                elif action == "change_price":

                    try:
                        value = int(
                            text.replace(",", "")
                            .replace(" ", "")
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

                    msg = (
                        f"✅ Yangi narx: ₩{value:,}"
                    )

                else:

                    try:
                        value = int(
                            text.replace(",", "")
                            .replace(" ", "")
                        )

                        if value < 0:
                            raise ValueError

                    except ValueError:

                        send(
                            chat_id,
                            "❌ Qoldiq 0 yoki undan katta "
                            "son bo‘lsin."
                        )

                        return

                    book["stock"] = value

                    msg = (
                        f"✅ Yangi qoldiq: {value} ta"
                    )

                save_books()

                states.pop(chat_id, None)

                send(
                    chat_id,
                    msg,
                    admin_menu()
                )

                return

        # Admin panelga tegishli bo‘lmagan
        # xabarlar pastdagi customer menyusiga o'tadi

    # =========================
    # CUSTOMER MENU
    # =========================

    if text == "📚 Kitoblar":

        send(
            chat_id,
            "📚 Mavjud kitoblar:",
            books_menu()
        )

        return

    if text == "🛒 Savatcha":

        send(
            chat_id,
            cart_text(chat_id),
            main_menu(chat_id)
        )

        return

    # -------------------------
    # ZAKAZ BOSHLASH
    # -------------------------

    if text == "📦 Zakaz berish":

        cart = carts.get(chat_id, {})

        if not cart:

            send(
                chat_id,
                "🛒 Avval kitob tanlang.",
                main_menu(chat_id)
            )

            return

        states[chat_id] = {
            "action": "order_name",
            "username": username,
            "cart": dict(cart)
        }

        send(
            chat_id,
            cart_text(chat_id)
            + "\n\n📝 Buyurtma uchun "
            "ismingizni yozing:",
            order_keyboard()
        )

        return

    # -------------------------
    # BEKOR QILISH
    # -------------------------

    if text == "❌ Bekor qilish":

        states.pop(chat_id, None)

        send(
            chat_id,
            "Bekor qilindi.",
            main_menu(chat_id)
        )

        return

    # -------------------------
    # BOG'LANISH
    # -------------------------

    if text == "📞 Bog‘lanish":

        send(
            chat_id,
            "📞 Bog‘lanish:\n"
            "Admin bilan Telegram orqali "
            "bog‘lanishingiz mumkin.",
            main_menu(chat_id)
        )

        return

    # =========================
    # ORDER STATES
    # =========================

    if state:

        action = state.get("action")

        # -------------------------
        # ISM
        # -------------------------

        if action == "order_name":

            state["name"] = text

            state["action"] = "order_phone"

            send(
                chat_id,
                "📞 Telefon raqamingizni yozing:"
            )

            return

        # -------------------------
        # TELEFON
        # -------------------------

        if action == "order_phone":

            state["phone"] = text

            state["action"] = "order_address"

            send(
                chat_id,
                "📍 Yetkazib berish "
                "manzilingizni yozing:"
            )

            return

        # -------------------------
        # MANZIL
        # -------------------------

        if action == "order_address":

            state["address"] = text

            # Omborni tekshirish
            for book_id, qty in state["cart"].items():

                book = find_book(book_id)

                if (
                    not book
                    or int(book["stock"]) < int(qty)
                ):

                    states.pop(chat_id, None)

                    send(
                        chat_id,
                        "❌ Kechirasiz, buyurtmadagi "
                        "kitoblardan biri yetarli "
                        "qolmagan.",
                        main_menu(chat_id)
                    )

                    return

            preview, total, grand_total = (
                create_order_preview(state)
            )

            state["total"] = total
            state["delivery_fee"] = DELIVERY_FEE
            state["grand_total"] = grand_total

            state["action"] = "order_confirm"

            send(
                chat_id,
                preview,
                order_keyboard()
            )

            return

        # -------------------------
        # BUYURTMANI TASDIQLASH
        # -------------------------

        if action == "order_confirm":

            if text != "✅ Buyurtmani tasdiqlash":

                send(
                    chat_id,
                    "Iltimos, buyurtmani "
                    "tasdiqlang yoki bekor qiling.",
                    order_keyboard()
                )

                return

            # Tasdiqlashdan oldin yana
            # omborni tekshiramiz
            for book_id, qty in state["cart"].items():

                book = find_book(book_id)

                if (
                    not book
                    or int(book["stock"]) < int(qty)
                ):

                    states.pop(chat_id, None)

                    send(
                        chat_id,
                        "❌ Kechirasiz, buyurtmadagi "
                        "kitoblardan biri hozir "
                        "qolmagan.",
                        main_menu(chat_id)
                    )

                    return

            # Yangi order ID
            order_id = str(
                int(time.time())
            )

            # Kitoblar
            lines = []

            for book_id, qty in state["cart"].items():

                book = find_book(book_id)

                if not book:
                    continue

                subtotal = (
                    int(book["price"])
                    * int(qty)
                )

                lines.append(
                    f"• {book['name']} × {qty} "
                    f"= ₩{subtotal:,}"
                )

            order = {
                "order_id": order_id,
                "chat_id": chat_id,
                "name": state["name"],
                "phone": state["phone"],
                "address": state["address"],
                "username": state.get(
                    "username",
                    ""
                ),
                "cart": state["cart"],
                "total": state["total"],
                "delivery_fee": DELIVERY_FEE,
                "grand_total": state["grand_total"],
                "status": "pending"
            }

            orders[order_id] = order

            save_orders()

            # Admin uchun zakaz
            order_text = (
                "🛒 YANGI BUYURTMA!\n\n"
                f"🔢 Zakaz №{order_id}\n\n"
                f"👤 Ism: {state['name']}\n"
                f"📞 Telefon: {state['phone']}\n"
                f"📍 Manzil: {state['address']}\n"
                f"🔗 Telegram: "
                f"@{state['username'] if state['username'] else 'username yo‘q'}\n"
                f"🆔 ID: {chat_id}\n\n"
                + "\n".join(lines)
                + "\n\n"
                f"💰 Kitoblar: ₩{state['total']:,}\n"
                f"🚚 택배: +₩{DELIVERY_FEE:,}\n"
                f"💵 JAMI: ₩{state['grand_total']:,}\n\n"
                "💳 TO‘LOV MA’LUMOTLARI\n"
                f"💳 Karta: {CARD_NUMBER}\n"
                f"🏦 {BANK_NAME}\n"
                f"👤 {CARD_OWNER}"
            )

            if ADMIN_ID:

                send(
                    ADMIN_ID,
                    order_text,
                    admin_order_keyboard(order_id)
                )

            # Savatchani bo'shatamiz
            carts[chat_id] = {}

            states.pop(chat_id, None)

            # Mijozga
            send(
                chat_id,
                "✅ Buyurtmangiz qabul qilindi!\n\n"
                f"🔢 Zakaz №{order_id}\n"
                f"💵 Jami: ₩{state['grand_total']:,}\n\n"
                "💳 To‘lov ma’lumotlari:\n"
                f"💳 Karta raqami: {CARD_NUMBER}\n"
                f"🏦 {BANK_NAME}\n"
                f"👤 {CARD_OWNER}\n\n"
                "To‘lovingiz tekshirilgach, "
                "admin siz bilan bog‘lanadi.",
                main_menu(chat_id)
            )

            return

    # -------------------------
    # NOMALUM XABAR
    # -------------------------

    send(
        chat_id,
        "Menyudan kerakli bo‘limni tanlang.",
        main_menu(chat_id)
    )


# =========================
# CALLBACK HANDLER
# =========================

def handle_callback(callback):

    callback_id = callback["id"]

    chat_id = callback["message"]["chat"]["id"]

    data = callback.get("data", "")

    api(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id
        }
    )

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
                "Tahrir qilinadigan "
                "kitobni tanlang:",
                edit_book_menu()
            )

        return

    # =========================
    # EDIT BOOK
    # =========================

    if data.startswith("edit_"):

        if not is_admin(chat_id):
            return

        book = find_book(
            data.split("_", 1)[1]
        )

        if book:

            send(
                chat_id,
                f"✏️ {book['name']}\n\n"
                "Nimani o‘zgartirmoqchisiz?",
                edit_fields_menu(
                    book["id"]
                )
            )

        return

    # =========================
    # RENAME
    # =========================

    if data.startswith("ename_"):

        if not is_admin(chat_id):
            return

        book_id = int(
            data.split("_", 1)[1]
        )

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

        book_id = int(
            data.split("_", 1)[1]
        )

        states[chat_id] = {
            "action": "change_price",
            "book_id": book_id
        }

        send(
            chat_id,
            "💰 Yangi narxni yozing (₩).\n"
            "Masalan: 35000"
        )

        return

    # =========================
    # STOCK
    # =========================

    if data.startswith("estock_"):

        if not is_admin(chat_id):
            return

        book_id = int(
            data.split("_", 1)[1]
        )

        states[chat_id] = {
            "action": "change_stock",
            "book_id": book_id
        }

        send(
            chat_id,
            "📦 Yangi qoldiqni yozing.\n"
            "Masalan: 12"
        )

        return

    # =========================
    # DELETE BOOK
    # =========================

    if data.startswith("delete_"):

        if not is_admin(chat_id):
            return

        book_id = int(
            data.split("_", 1)[1]
        )

        book = find_book(book_id)

        if book:

            books.remove(book)

            save_books()

            send(
                chat_id,
                f"🗑 O‘chirildi: "
                f"{book['name']}",
                admin_menu()
            )

        return

    # =========================
    # UNAVAILABLE BOOK
    # =========================

    if data.startswith("none_"):

        send(
            chat_id,
            "❌ Bu kitob hozircha "
            "mavjud emas."
        )

        return

    # =========================
    # ADD BOOK TO CART
    # =========================

    if data.startswith("book_"):

        book_id = int(
            data.split("_", 1)[1]
        )

        book = find_book(book_id)

        if (
            not book
            or int(book["stock"]) <= 0
            or int(book["price"]) <= 0
        ):

            send(
                chat_id,
                "❌ Bu kitob hozircha "
                "mavjud emas."
            )

            return

        cart = carts.setdefault(
            chat_id,
            {}
        )

        current = int(
            cart.get(book_id, 0)
        )

        if current >= int(
            book["stock"]
        ):

            send(
                chat_id,
                f"❌ Omborda faqat "
                f"{book['stock']} ta bor."
            )

            return

        cart[book_id] = current + 1

        send(
            chat_id,
            f"✅ {book['name']} "
            "savatchaga qo‘shildi.\n\n"
            + cart_text(chat_id),
            main_menu(chat_id)
        )

        return

    # =========================
    # ADMIN: PAYMENT CONFIRMED
    # =========================

    if data.startswith("paid_"):

        if not is_admin(chat_id):
            return

        order_id = data.split(
            "_",
            1
        )[1]

        order = orders.get(order_id)

        if not order:

            send(
                chat_id,
                "❌ Zakaz topilmadi."
            )

            return

        if order["status"] != "pending":

            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon "
                "qayta ishlangan."
            )

            return

        # To'lov tasdiqlanishidan oldin
        # omborni yana tekshirish
        for book_id, qty in order["cart"].items():

            book = find_book(book_id)

            if (
                not book
                or int(book["stock"]) < int(qty)
            ):

                order["status"] = "stock_problem"

                save_orders()

                send(
                    chat_id,
                    "❌ Omborda bu zakazni "
                    "bajarish uchun yetarli "
                    "kitob qolmagan."
                )

                send(
                    order["chat_id"],
                    "❌ Afsuski, zakazingizdagi "
                    "kitoblardan biri qolmagan. "
                    "Admin siz bilan bog‘lanadi.",
                    main_menu(
                        order["chat_id"]
                    )
                )

                return

        # Omborni kamaytirish
        for book_id, qty in order["cart"].items():

            book = find_book(book_id)

            book["stock"] = (
                int(book["stock"])
                - int(qty)
            )

        save_books()

        order["status"] = "paid"

        save_orders()

        # Admin
        send(
            chat_id,
            f"✅ Zakaz №{order_id} "
            "to‘lov qilindi deb belgilandi.\n\n"
            "📦 Ombor yangilandi.",
            admin_menu()
        )

        # Mijoz
        send(
            order["chat_id"],
            f"✅ To‘lovingiz tasdiqlandi!\n\n"
            f"🔢 Zakaz №{order_id}\n"
            f"💵 Jami: ₩{order['grand_total']:,}\n\n"
            "📦 Buyurtmangiz tez orada "
            "yuboriladi.\n"
            "Rahmat! ❤️",
            main_menu(
                order["chat_id"]
            )
        )

        return

    # =========================
    # ADMIN: CANCEL ORDER
    # =========================

    if data.startswith("cancelorder_"):

        if not is_admin(chat_id):
            return

        order_id = data.split(
            "_",
            1
        )[1]

        order = orders.get(order_id)

        if not order:

            send(
                chat_id,
                "❌ Zakaz topilmadi."
            )

            return

        if order["status"] != "pending":

            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon "
                "qayta ishlangan."
            )

            return

        order["status"] = "cancelled"

        save_orders()

        send(
            chat_id,
            f"❌ Zakaz №{order_id} "
            "bekor qilindi.",
            admin_menu()
        )

        send(
            order["chat_id"],
            f"❌ Zakaz №{order_id} "
            "bekor qilindi.\n\n"
            "Agar xatolik bo‘lsa, admin "
            "bilan bog‘laning.",
            main_menu(
                order["chat_id"]
            )
        )

        return


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:
        raise Exception(
            "BOT_TOKEN sozlanmagan!"
        )

    load_books()
    load_orders()

    offset = None

    while True:

        try:

            params = {
                "timeout": 50
            }

            if offset is not None:
                params["offset"] = offset

            result = api(
                "getUpdates",
                params
            )

            for update in result.get(
                "result",
                []
            ):

                offset = (
                    update["update_id"]
                    + 1
                )

                if "message" in update:

                    handle_message(
                        update["message"]
                    )

                elif "callback_query" in update:

                    handle_callback(
                        update[
                            "callback_query"
                        ]
                    )

        except Exception as e:

            print(
                "Xato:",
                e
            )

            time.sleep(5)


if __name__ == "__main__":
    main()
