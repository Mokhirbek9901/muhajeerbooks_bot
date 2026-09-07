from pathlib import Path
import re

path = Path('bot.py')
s = path.read_text(encoding='utf-8')

if 'import cloud_bridge\n' not in s:
    s = s.replace('import io\n', 'import io\nimport cloud_bridge\n', 1)

refresh_old = '''def refresh_books():
    """books.json ni har safar qayta o'qib, barcha foydalanuvchilarga eng yangi qoldiqni beradi."""
    load_books()
    return books
'''
refresh_new = refresh_old + '''\n\ndef _apply_cloud_stocks(stocks):
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
'''
if '_cloud_set_order_status' not in s:
    assert refresh_old in s, 'refresh_books block not found'
    s = s.replace(refresh_old, refresh_new, 1)

old_detail = '''def send_book_detail(chat_id, book):
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
'''
new_detail = '''def send_book_detail(chat_id, book):
    text = book_detail_text(book)
    markup = book_detail_keyboard(book, chat_id)
    # Telegramdagi file_id bo'lsa undan, programmadan yuklangan rasm bo'lsa public URLdan foydalanamiz.
    photo = str(book.get("photo_id", "") or book.get("image_url", "") or "").strip()
    if photo:
        try:
            api("sendPhoto", {"chat_id": chat_id, "photo": photo, "caption": text, "reply_markup": json.dumps(markup, ensure_ascii=False)})
            return
        except Exception as e:
            print("Rasm yuborish xatosi:", e)
    send(chat_id, text, markup)
'''
if old_detail in s:
    s = s.replace(old_detail, new_detail, 1)

old_inactive = '''    candidates = [
        b for b in books
        if int(b.get("stock", 0)) > 0
        and int(b.get("price", 0)) > 0
        and str(b.get("photo_id", "")).strip()
    ]
'''
new_inactive = '''    candidates = [
        b for b in books
        if int(b.get("stock", 0)) > 0
        and int(b.get("price", 0)) > 0
        and (str(b.get("photo_id", "")).strip() or str(b.get("image_url", "")).strip())
    ]
'''
if old_inactive in s:
    s = s.replace(old_inactive, new_inactive, 1)

old_inactive_photo = '''                    "photo": book["photo_id"],
'''
if old_inactive_photo in s:
    s = s.replace(old_inactive_photo, '''                    "photo": str(book.get("photo_id", "") or book.get("image_url", "")),
''', 1)

old_kb = '''def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "paid":
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}
'''
new_kb = '''def admin_order_status_keyboard(order_id, status):
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
'''
if old_kb in s:
    s = s.replace(old_kb, new_kb, 1)

finalize_old = '''    orders[order_id] = order
    save_orders()

    # Keyingi buyurtmada mijoz qayta yozmasligi uchun ma’lumotlarni eslab qolamiz.
'''
finalize_new = '''    orders[order_id] = order
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
'''
if finalize_old in s:
    s = s.replace(finalize_old, finalize_new, 1)

ship_block = '''    # =========================
    # ADMIN: SHIPPED
    # =========================

    if data.startswith("ship_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order or order.get("status") != "paid":
            send(chat_id, "⚠️ Avval to‘lovni tasdiqlang.")
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
        if customer_chat > 0:
            send(
                customer_chat,
                "🚚 Kitobingiz jo‘natildi!\\n\\n"
                "📦 Buyurtmangiz 1–3 ish kunida yetib boradi.\\n\\n"
                "Xaridingiz uchun rahmat! ❤️",
                main_menu(customer_chat)
            )
        return

'''

delivered_block = '''    # =========================
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
        try:
            _cloud_set_order_status(order, "delivered")
        except Exception as e:
            send(chat_id, f"❌ Holat yangilanmadi: {e}")
            return
        order["status"] = "delivered"
        save_orders()
        send(chat_id, f"✅ Zakaz №{order_id} yetkazildi deb belgilandi.", admin_menu())
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0:
            send(
                customer_chat,
                f"✅ Zakaz №{order_id} yetkazildi deb belgilandi.\\n\\n"
                "Rahmat! ❤️ «📜 Mening buyurtmalarim» bo‘limida kitobga baho va fikr qoldirishingiz mumkin.",
                main_menu(customer_chat)
            )
        return

'''

paid_block = '''    # =========================
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
        if order.get("status") != "pending":
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
            f"✅ Zakaz №{order_id} to‘lov qilindi deb belgilandi.\\n\\n📦 Ombor bot va programmada bir xil yangilandi.",
            admin_order_status_keyboard(order_id, "paid")
        )
        customer_chat = int(order.get("chat_id") or 0)
        if customer_chat > 0:
            send(
                customer_chat,
                "✅ BUYURTMANGIZ QABUL QILINDI!\\n\\n" + order_receipt_text(order) +
                "\\n\\n📦 Kitoblaringiz pochtaga topshirilganda sizga alohida xabar yuboriladi.",
                main_menu(customer_chat)
            )
        return

'''

cancel_block = '''    # =========================
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
        if order.get("status") != "pending":
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
                f"❌ Zakaz №{order_id} bekor qilindi.\\n\\nAgar xatolik bo‘lsa, admin bilan bog‘laning.",
                main_menu(customer_chat)
            )
        return

'''

# Markerlar orasini almashtirish status logikasini bir markazga (Supabase) o'tkazadi.
start = s.index('    # =========================\n    # ADMIN: SHIPPED\n')
end = s.index('\n\n# =========================\n# MAIN\n', start)
s = s[:start] + ship_block + delivered_block + paid_block + cancel_block + s[end:]

path.write_text(s, encoding='utf-8')
