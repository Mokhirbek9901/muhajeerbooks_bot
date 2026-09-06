from pathlib import Path

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

old = '''        states[chat_id] = {
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
            send(chat_id, "✅ Oldingi ma’lumotlaringiz ishlatildi.\\n\\n" + preview + "\\n\\n" + order_customer_info_text(states[chat_id]), order_edit_keyboard(states[chat_id]))
        else:
            send(chat_id, cart_text(chat_id) + "\\n\\n📝 Buyurtma uchun ismingizni yozing:")
        return
'''
new = '''        states[chat_id] = {
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
                "📍 Oldingi ma’lumotlaringiz bizda saqlangan.\\n\\n"
                + order_customer_info_text(states[chat_id])
                + "\\n\\nShu manzilga yuborilsinmi?",
                {"inline_keyboard": [
                    [{"text": "✅ Shu manzilga yuborish", "callback_data": "saved_use_address"}],
                    [{"text": "📍 Boshqa manzil", "callback_data": "saved_new_address"}]
                ]}
            )
        else:
            send(chat_id, cart_text(chat_id) + "\\n\\n📝 Buyurtma uchun ismingizni yozing:")
        return
'''
assert t.count(old) == 1, t.count(old)
t = t.replace(old, new, 1)

anchor = '''    # =========================
    # SAVATCHA - NOOP
    # =========================
'''
insert = '''    if data == "saved_use_address":
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
            preview + "\\n\\n" + order_customer_info_text(state),
            order_edit_keyboard(state)
        )
        return

    if data == "saved_new_address":
        state = states.get(chat_id)
        if not state or state.get("action") != "confirm_saved_info":
            return
        state["action"] = "order_saved_address"
        send(
            chat_id,
            "📍 Yangi manzil va xona raqamini to‘liq yozing.\\n\\n"
            "Masalan: 경상북도 경산시 계양로 37길 7-3, 808호"
        )
        return

'''
assert anchor in t
t = t.replace(anchor, insert + anchor, 1)

anchor2 = '''    # =========================
    # ORDER: MANZIL
    # =========================

'''
insert2 = '''    if state and state.get("action") == "order_saved_address":
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
            preview + "\\n\\n" + order_customer_info_text(state),
            order_edit_keyboard(state)
        )
        return

'''
assert anchor2 in t
t = t.replace(anchor2, anchor2 + insert2, 1)

p.write_text(t, encoding='utf-8')
