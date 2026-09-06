from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

old = '''def admin_orders_keyboard(status_filter="all"):
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
'''
new = '''def admin_orders_keyboard(status_filter="all"):
    counts = admin_order_counts()
    buttons = [
        [{"text": f"🟡 Kutilmoqda ({counts['pending']})", "callback_data": "adminorders_pending"}],
        [{"text": f"🚚 Jo‘natilgan ({counts['shipped']})", "callback_data": "adminorders_shipped"}],
        [{"text": f"📦 Hammasi ({len(orders)})", "callback_data": "adminorders_all"}],
    ]
'''
assert text.count(old) == 1, f"admin_orders_keyboard count={text.count(old)}"
text = text.replace(old, new, 1)

old = '''def admin_order_status_keyboard(order_id, status):
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
new = '''def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status in ("pending", "paid"):
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}
'''
assert text.count(old) == 1, f"admin_order_status_keyboard count={text.count(old)}"
text = text.replace(old, new, 1)

old = '''    if data.startswith("ship_"):
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
        send(order["chat_id"], f"🚚 Zakaz №{order_id} jo‘natildi!\\n\\nBuyurtmangiz yo‘lda. ❤️", main_menu(order["chat_id"]))
        return
'''
new = '''    if data.startswith("ship_"):
        if not is_admin(chat_id):
            return
        order_id = data.split("_", 1)[1]
        order = orders.get(order_id)
        if not order or order.get("status") not in ("pending", "paid"):
            send(chat_id, "⚠️ Buyurtma holati mos emas.")
            return

        # Admin "Jo‘natildi"ni bosganda pending buyurtma savdo sifatida
        # hisoblanadi va ombor shu payt kamayadi.
        if order.get("status") == "pending":
            refresh_books()
            order_books = {}
            for book_id, qty in order.get("cart", {}).items():
                book = next(
                    (b for b in books if int(b.get("id", -1)) == int(book_id)),
                    None
                )
                if not book or int(book.get("stock", 0)) < int(qty):
                    order["status"] = "stock_problem"
                    save_orders()
                    send(chat_id, "❌ Omborda bu buyurtmani jo‘natish uchun yetarli kitob qolmagan.")
                    send(
                        order["chat_id"],
                        "❌ Afsuski, buyurtmangizdagi kitoblardan biri qolmagan. Admin siz bilan bog‘lanadi.",
                        main_menu(order["chat_id"])
                    )
                    return
                order_books[str(book_id)] = book

            for book_id, qty in order.get("cart", {}).items():
                book = order_books[str(book_id)]
                book["stock"] = int(book.get("stock", 0)) - int(qty)
            save_books()

            for book_id, qty in order.get("cart", {}).items():
                book = order_books.get(str(book_id))
                if not book:
                    continue
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

        order["status"] = "shipped"
        save_orders()
        send(chat_id, f"🚚 Buyurtma №{order_id} jo‘natildi. Statistika va ombor yangilandi.", admin_menu())
        send(
            order["chat_id"],
            "🚚 Kitobingiz jo‘natildi!\\n\\n"
            "📦 Buyurtmangiz 1–3 ish kunida yetib boradi.\\n\\n"
            "Xaridingiz uchun rahmat! ❤️",
            main_menu(order["chat_id"])
        )
        return
'''
assert text.count(old) == 1, f"ship handler count={text.count(old)}"
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
