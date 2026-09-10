from pathlib import Path
import re


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Missing patch target: {label}")
    return text.replace(old, new, 1)


def replace_def(text, name, replacement):
    pattern = rf"(?ms)^def {re.escape(name)}\([^\n]*\):\n.*?(?=^def |\Z)"
    updated, count = re.subn(pattern, replacement.rstrip() + "\n\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not replace function: {name}")
    return updated


bot_path = Path("bot.py")
bot = bot_path.read_text(encoding="utf-8")

if "import urllib.error" not in bot:
    bot = replace_once(bot, "import urllib.parse\n", "import urllib.parse\nimport urllib.error\n", "urllib.error import")

api_fn = r'''def api(method, data=None):
    if data is None:
        data = {}

    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{API}/{method}", data=encoded)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
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
'''
bot = replace_def(bot, "api", api_fn)

# Add small reusable pager before the edit menu.
if "ADMIN_PAGE_SIZE = 12" not in bot:
    pager = r'''ADMIN_PAGE_SIZE = 12


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

'''
    marker = "def edit_book_menu("
    idx = bot.find(marker)
    if idx < 0:
        raise RuntimeError("Missing edit_book_menu marker")
    bot = bot[:idx] + pager + bot[idx:]

edit_fn = r'''def edit_book_menu(page=0, chat_id=ADMIN_ID, message_id=None):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"✏️ {b['name']}",
        "callback_data": f"edit_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("editpage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    markup = {"inline_keyboard": buttons}
    text = f"✏️ Tahrirlash uchun kitob tanlang: ({page + 1}/{total})"
    if message_id is not None:
        try:
            edit_message(chat_id, message_id, text, markup)
            return
        except Exception:
            pass
    send(chat_id, text, markup)
'''
bot = replace_def(bot, "edit_book_menu", edit_fn)

delete_fn = r'''def delete_book_menu(page=0, chat_id=ADMIN_ID, message_id=None):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"🗑 {b['name']}",
        "callback_data": f"delete_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("deletepage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    markup = {"inline_keyboard": buttons}
    text = f"🗑 O‘chirish uchun kitobni tanlang: ({page + 1}/{total})"
    if message_id is not None:
        try:
            edit_message(chat_id, message_id, text, markup)
            return
        except Exception:
            pass
    send(chat_id, text, markup)
'''
bot = replace_def(bot, "delete_book_menu", delete_fn)

quick_fn = r'''def quick_stock_list_keyboard(chat_id=None, page=None):
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
'''
bot = replace_def(bot, "quick_stock_list_keyboard", quick_fn)

# Pagination callback handlers.
if 'data.startswith("editpage_")' not in bot:
    anchor = '    if data == "editlist":\n'
    insert = '''    if data == "page_noop" or data == "qstock_noop":
        try:
            api("answerCallbackQuery", {"callback_query_id": callback_id})
        except Exception:
            pass
        return
    if data.startswith("editpage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        edit_book_menu(page, chat_id, message_id); return
    if data.startswith("deletepage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        delete_book_menu(page, chat_id, message_id); return
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
'''
    bot = replace_once(bot, anchor, insert + anchor, "pagination callback handlers")

# Make the legacy list actions open page zero in the current message.
bot = bot.replace('        edit_book_menu()\n        return', '        edit_book_menu(0, chat_id, message_id)\n        return', 1)
bot = bot.replace('        delete_book_menu()\n        return', '        delete_book_menu(0, chat_id, message_id)\n        return', 1)

# Preserve quick-stock current page while editing quantities.
bot = bot.replace(
    'states[chat_id] = {"action":"quick_stock_batch","stock_draft":{str(b["id"]):int(b.get("stock",0)) for b in books}}',
    'states[chat_id] = {"action":"quick_stock_batch","stock_draft":{str(b["id"]):int(b.get("stock",0)) for b in books},"stock_page":0}',
    1,
)
# Handle variant formatting if the original line uses spaces.
if '"action": "quick_stock_batch"' in bot and '"stock_page"' not in bot[bot.find('"action": "quick_stock_batch"'):bot.find('"action": "quick_stock_batch"')+300]:
    bot = bot.replace(
        '"action": "quick_stock_batch",\n            "stock_draft": {',
        '"action": "quick_stock_batch",\n            "stock_page": 0,\n            "stock_draft": {',
        1,
    )

# Telegram deep-link: /start restock_<book_id> enrolls user in real Telegram notifications.
if 'start_payload.startswith("restock_")' not in bot:
    bot = replace_once(bot, '    if text == "/start":\n', '    if text == "/start" or text.startswith("/start "):\n', "deep-link start condition")
    start_anchor = '''        carts.setdefault(chat_id, {})
        states.pop(chat_id, None)

'''
    deep_link = '''        carts.setdefault(chat_id, {})
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
                send(chat_id, f"✅ {book['name']} hozir sotuvda mavjud.", book_keyboard(book, chat_id))
                return
            subscribe_restock(chat_id, book_id)
            send(
                chat_id,
                f"🔔 {book['name']} qayta kelishi bilan Telegram orqali sizga xabar beraman.",
                main_menu(chat_id),
            )
            return

'''
    bot = replace_once(bot, start_anchor, deep_link, "deep-link handler")

bot_path.write_text(bot, encoding="utf-8")


# -------------------------
# sync_wrapper.py: web/app stock changes should also wake Telegram subscribers.
# -------------------------
sync_path = Path("sync_wrapper.py")
sync = sync_path.read_text(encoding="utf-8")
if "RESTOCK_FILE =" not in sync:
    sync = replace_once(
        sync,
        'RATINGS_FILE = os.path.join(DATA_DIR, "ratings.json")\n',
        'RATINGS_FILE = os.path.join(DATA_DIR, "ratings.json")\nRESTOCK_FILE = os.path.join(DATA_DIR, "restock.json")\n',
        "sync restock file",
    )

if "def _notify_restock_transitions(" not in sync:
    helper = r'''
def _telegram_send_text(chat_id, text):
    if not BOT_TOKEN:
        return False
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=urllib.parse.urlencode({"chat_id": str(chat_id), "text": text}).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return bool(payload.get("ok"))
    except Exception as exc:
        print("Restock Telegram xatosi:", chat_id, exc)
        return False


def _notify_restock_transitions(before, after):
    subscriptions = _read_json(RESTOCK_FILE, {})
    if not isinstance(subscriptions, dict) or not subscriptions:
        return
    before_by_id = {
        str(b.get("id")): b for b in (before or []) if isinstance(b, dict)
    }
    changed = False
    for book in after or []:
        if not isinstance(book, dict):
            continue
        bid = str(book.get("id") or "")
        if not bid:
            continue
        old = before_by_id.get(bid) or {}
        try:
            old_stock = int(old.get("stock") or 0)
            new_stock = int(book.get("stock") or 0)
        except Exception:
            continue
        if old_stock > 0 or new_stock <= 0:
            continue
        targets = [str(x) for x in subscriptions.get(bid, [])]
        if not targets:
            continue
        title = str(book.get("name") or "Kitob")
        price = int(book.get("price") or 0)
        message = f"📚 {title} yana sotuvda!\n📦 Qoldiq: {new_stock} ta"
        if price > 0:
            message += f"\n💰 Narx: ₩{price:,}"
        message += "\n\nMuhajeer Books orqali buyurtma berishingiz mumkin."
        failed = []
        for chat_id in targets:
            if not _telegram_send_text(chat_id, message):
                failed.append(chat_id)
        if failed:
            subscriptions[bid] = sorted(set(failed))
        else:
            subscriptions.pop(bid, None)
        changed = True
    if changed:
        _write_json(RESTOCK_FILE, subscriptions)

'''
    anchor = "def _hash(data):\n"
    idx = sync.find(anchor)
    if idx < 0:
        raise RuntimeError("Missing sync hash marker")
    sync = sync[:idx] + helper + sync[idx:]

old_write = '''                if _hash(merged) != _hash(latest_local):
                    _write_json(BOOKS_FILE, merged)
'''
new_write = '''                if _hash(merged) != _hash(latest_local):
                    _notify_restock_transitions(latest_local, merged)
                    _write_json(BOOKS_FILE, merged)
'''
if old_write in sync:
    sync = sync.replace(old_write, new_write, 1)
elif "_notify_restock_transitions(latest_local, merged)" not in sync:
    raise RuntimeError("Missing sync merged write target")

sync_path.write_text(sync, encoding="utf-8")

print("Bot launch hardening patches applied")
