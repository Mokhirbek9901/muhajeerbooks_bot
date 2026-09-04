import os
import time
import json
import urllib.request
import urllib.parse

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

API = f"https://api.telegram.org/bot{TOKEN}"

# Hozircha namunaviy kitoblar
BOOKS = [
    {"id": 1, "name": "Istiqlol jallodlari", "price": 30000},
    {"id": 2, "name": "Yovuz daho 2-qism", "price": 35000},
    {"id": 3, "name": "Sunniy intelekt asoslari", "price": 40000},
    {"id": 4, "name": "Yuqumlilik", "price": 30000},
    {"id": 5, "name": "Binafsha 1-qism", "price": 35000},
    {"id": 6, "name": "Jinni binafsha 2-qism", "price": 40000},
]

carts = {}


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


def send(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)

    return api("sendMessage", data)


def main_menu():
    return {
        "keyboard": [
            [{"text": "📚 Kitoblar"}, {"text": "🛒 Savatcha"}],
            [{"text": "📦 Zakaz berish"}, {"text": "📞 Bog‘lanish"}]
        ],
        "resize_keyboard": True
    }


def books_menu():
    buttons = []

    for book in BOOKS:
        buttons.append([
            {
                "text": f"📖 {book['name']} — {book['price']:,} so‘m",
                "callback_data": f"book_{book['id']}"
            }
        ])

    buttons.append([
        {"text": "⬅️ Bosh menyu", "callback_data": "home"}
    ])

    return {"inline_keyboard": buttons}


def cart_text(chat_id):
    cart = carts.get(chat_id, {})

    if not cart:
        return "🛒 Savatchangiz hozircha bo‘sh."

    text = "🛒 SAVATCHA\n\n"
    total = 0

    for book_id, quantity in cart.items():
        book = next((b for b in BOOKS if b["id"] == book_id), None)

        if book:
            summa = book["price"] * quantity
            total += summa

            text += (
                f"📖 {book['name']}\n"
                f"   {quantity} dona × {book['price']:,} = "
                f"{summa:,} so‘m\n\n"
            )

    text += f"💰 Jami: {total:,} so‘m"
    return text


def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":
        carts.setdefault(chat_id, {})
        send(
            chat_id,
            "Assalomu alaykum! 📚\n\n"
            "Muhajeer Books kitob do‘koniga xush kelibsiz!",
            main_menu()
        )

    elif text == "/id":
        send(
            chat_id,
            f"Sizning Telegram ID raqamingiz:\n\n{chat_id}"
        )

    elif text == "📚 Kitoblar":
        send(
            chat_id,
            "📚 KITOBLAR\n\n"
            "Kerakli kitobni tanlang:",
            books_menu()
        )

    elif text == "🛒 Savatcha":
        send(chat_id, cart_text(chat_id))

    elif text == "📦 Zakaz berish":
        cart = carts.get(chat_id, {})

        if not cart:
            send(
                chat_id,
                "🛒 Avval savatchaga kitob qo‘shing."
            )
            return

        send(
            chat_id,
            cart_text(chat_id)
            + "\n\n👤 Zakazni rasmiylashtirish uchun "
              "ismingizni yozing."
        )

        # Keyingi bosqichda ism/telefon/manzil yig‘ishni qo‘shamiz.

    elif text == "📞 Bog‘lanish":
        send(
            chat_id,
            "📞 Bog‘lanish\n\n"
            "Muhajeer Books\n"
            "Telegram: @muhajeerbooks_bot"
        )

    else:
        send(
            chat_id,
            "Menyudan kerakli bo‘limni tanlang 👇",
            main_menu()
        )


def handle_callback(query):
    query_id = query["id"]
    data = query["data"]
    chat_id = query["message"]["chat"]["id"]

    api("answerCallbackQuery", {
        "callback_query_id": query_id
    })

    if data == "home":
        send(
            chat_id,
            "🏠 Bosh menyu",
            main_menu()
        )
        return

    if data.startswith("book_"):
        book_id = int(data.split("_")[1])
        book = next(
            (b for b in BOOKS if b["id"] == book_id),
            None
        )

        if not book:
            return

        carts.setdefault(chat_id, {})
        carts[chat_id][book_id] = (
            carts[chat_id].get(book_id, 0) + 1
        )

        send(
            chat_id,
            f"✅ {book['name']} savatchaga qo‘shildi!\n\n"
            + cart_text(chat_id),
            main_menu()
        )


def main():
    if not TOKEN:
        raise Exception("BOT_TOKEN sozlanmagan!")

    offset = 0

    print("Muhajeer Books bot ishga tushdi...")

    while True:
        try:
            result = api("getUpdates", {
                "offset": offset,
                "timeout": 50
            })

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])

                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

        except Exception as e:
            print("Xatolik:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
