from pathlib import Path
import re


# -------------------------
# bot.py
# -------------------------
bot = Path("bot.py")
s = bot.read_text(encoding="utf-8")

new_keyboard = '''def admin_order_status_keyboard(order_id, status):
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
'''
if 'callback_data":f"accept_{order_id}"' not in s:
    s, n = re.subn(
        r'def admin_order_status_keyboard\(order_id, status\):\n.*?^    return \{"inline_keyboard":buttons\}\n',
        new_keyboard,
        s,
        count=1,
        flags=re.S | re.M,
    )
    if n != 1:
        raise SystemExit("admin_order_status_keyboard patch failed")

marker = '''    # =========================
    # ADMIN: SHIPPED
    # =========================
'''
accept_block = '''    # =========================
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
'''
if 'if data.startswith("accept_"):' not in s:
    if marker not in s:
        raise SystemExit("shipped marker not found")
    s = s.replace(marker, accept_block, 1)

old_ship_guard = '''        if not order or order.get("status") != "paid":
            send(chat_id, "⚠️ Avval to‘lovni tasdiqlang.")
            return
'''
new_ship_guard = '''        if not order or order.get("status") not in ("accepted", "paid"):
            send(chat_id, "⚠️ Avval buyurtmani qabul qiling.")
            return
'''
if old_ship_guard in s:
    s = s.replace(old_ship_guard, new_ship_guard, 1)

# Appdan kelgan order hech qachon Telegram mijoz chatiga status xabari yubormasin.
ship_notify_old = '''        if customer_chat > 0:
            send(
                customer_chat,
                "🚚 Kitobingiz jo‘natildi!'''
ship_notify_new = '''        if customer_chat > 0 and str(order.get("source") or "telegram") != "app":
            send(
                customer_chat,
                "🚚 Kitobingiz jo‘natildi!'''
if ship_notify_old in s:
    s = s.replace(ship_notify_old, ship_notify_new, 1)

# Eski Yetkazildi callbacklari yangi holat yaratmasin.
delivered_pattern = re.compile(
    r'    # =========================\n    # ADMIN: DELIVERED\n    # =========================\n\n'
    r'    if data\.startswith\("deliver_"\):.*?^        return\n\n'
    r'    # =========================\n    # ADMIN: PAYMENT CONFIRMED\n    # =========================',
    re.S | re.M,
)
delivered_stub = '''    # =========================
    # ADMIN: DELIVERED (legacy button)
    # =========================

    if data.startswith("deliver_"):
        if is_admin(chat_id):
            send(chat_id, "ℹ️ «Yetkazildi» bosqichi olib tashlangan. 🚚 Jo‘natildi — yakuniy holat.", admin_menu())
        return

    # =========================
    # ADMIN: PAYMENT CONFIRMED
    # ========================='''
if delivered_pattern.search(s):
    s = delivered_pattern.sub(delivered_stub, s, count=1)

bot.write_text(s, encoding="utf-8")


# -------------------------
# sync_wrapper.py
# -------------------------
sync = Path("sync_wrapper.py")
w = sync.read_text(encoding="utf-8")
old_link = '    linked_chat = int(row.get("telegram_chat_id") or existing.get("chat_id") or 0)\n'
new_link = '''    # Ilovadan kelgan buyurtma Telegram mijoziga avtomatik bog‘lanmaydi.
    # Telegram akkauntining SIM raqamini bot ko‘rmaydi; telefon bo‘yicha taxminiy
    # bog‘lash boshqa akkauntga xabar yuborishiga sabab bo‘lishi mumkin.
    source = str(row.get("source") or "app")
    linked_chat = 0 if source == "app" else int(
        row.get("telegram_chat_id") or existing.get("chat_id") or 0
    )
'''
if old_link in w:
    w = w.replace(old_link, new_link, 1)
elif 'linked_chat = 0 if source == "app"' not in w:
    raise SystemExit("sync_wrapper linked_chat patch failed")

notify_start = w.find("def _notify_admin_app_order(order):")
if notify_start < 0:
    raise SystemExit("notify function not found")
kb_start = w.find("    kb = {", notify_start)
kb_end = w.find("    _telegram_send(ADMIN_ID, text, kb)", kb_start)
if kb_start < 0 or kb_end < 0:
    raise SystemExit("notify keyboard bounds not found")
current_kb = w[kb_start:kb_end]
if "✅ Buyurtmani qabul qilish" not in current_kb:
    kb_block = '''    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Buyurtmani qabul qilish",
                    "callback_data": f"accept_{order.get('order_id')}",
                }
            ],
            [
                {
                    "text": "📦 Buyurtmani ochish",
                    "callback_data": f"adminorder_{order.get('order_id')}",
                }
            ],
        ]
    }
'''
    w = w[:kb_start] + kb_block + w[kb_end:]

sync.write_text(w, encoding="utf-8")


# -------------------------
# cloud_bridge.py
# -------------------------
bridge = Path("cloud_bridge.py")
c = bridge.read_text(encoding="utf-8")
if "Kitob server katalogidan o‘chirilmadi" not in c:
    start = c.find("def delete_book(book):")
    if start < 0:
        raise SystemExit("delete_book function not found")
    new_delete = '''def delete_book(book):
    cloud_id = str(book.get("cloud_id") or "").strip() or None
    try:
        telegram_id = int(book.get("id") or 0)
    except Exception:
        telegram_id = None
    payload = {
        "p_secret": SYNC_SECRET,
        "p_telegram_id": telegram_id if telegram_id and telegram_id > 0 else None,
        "p_cloud_id": cloud_id,
    }
    result = rpc("bot_sync_delete", payload)
    try:
        deleted = int(result or 0)
    except Exception:
        deleted = 0
    if deleted <= 0:
        raise RuntimeError("Kitob server katalogidan o‘chirilmadi. Qayta urinib ko‘ring.")
    return deleted
'''
    c = c[:start] + new_delete
bridge.write_text(c, encoding="utf-8")
