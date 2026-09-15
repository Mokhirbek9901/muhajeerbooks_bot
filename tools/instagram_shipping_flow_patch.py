from pathlib import Path

bot_path = Path('bot.py')
bridge_path = Path('cloud_bridge.py')

bot = bot_path.read_text(encoding='utf-8')

helper_marker = 'def instagram_confirm_keyboard():\n'
if 'def instagram_shipping_offer_keyboard()' not in bot:
    helper = '''def instagram_shipping_offer_keyboard():
    return {
        "keyboard": [[
            {"text": "📮 Kiritaman"},
            {"text": "Yo‘q"},
        ]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def instagram_shipping_books_text(cart):
    lines = []
    for bid, qty in (cart or {}).items():
        book = find_book(bid)
        title = (book or {}).get("name") or f"Kitob #{bid}"
        lines.append(f"• {title} × {int(qty)}")
    return "\\n".join(lines) or "• Kitob ma’lumoti yo‘q"


'''
    if helper_marker not in bot:
        raise SystemExit('instagram confirm keyboard marker not found')
    bot = bot.replace(helper_marker, helper + helper_marker, 1)

old_parse = '''                for key in ("name", "phone", "address", "books", "raw_text"):
                    if parsed.get(key):
                        state[key] = parsed[key]
'''
new_parse = '''                for key in ("name", "phone", "address", "books", "raw_text"):
                    if key == "books" and state.get("lock_books"):
                        continue
                    if parsed.get(key):
                        state[key] = parsed[key]
'''
if old_parse in bot:
    bot = bot.replace(old_parse, new_parse, 1)
elif new_parse not in bot:
    raise SystemExit('smart shipping parse marker not found')

offer_marker = '            if action == "instagram_items":\n'
if 'if action == "instagram_shipping_offer":' not in bot:
    offer_branch = '''            if action == "instagram_shipping_offer":
                if text == "Yo‘q":
                    states.pop(chat_id, None)
                    send(
                        chat_id,
                        "✅ Instagram savdo saqlandi.\\n\\n📮 Pochta uchun manzil kiritilmadi.",
                        admin_menu(),
                    )
                    return
                if text == "📮 Kiritaman":
                    state["action"] = "shipping_smart_input"
                    send(
                        chat_id,
                        "📮 Pochta uchun ma’lumot yuboring.\\n\\n"
                        "📸 Mijoz yuborgan screenshotni jo‘natishingiz mumkin.\\n"
                        "Yoki qo‘lda bir xabarda quyidagicha yozing:\\n\\n"
                        "Ism Familiya\\n"
                        "01012345678\\n"
                        "To‘liq manzil, xona raqami\\n\\n"
                        "📚 Kitoblar avtomatik qo‘shiladi.",
                        {"remove_keyboard": True},
                    )
                    return
                send(chat_id, "📮 Pochta uchun manzil kiritasizmi?", instagram_shipping_offer_keyboard())
                return

'''
    if offer_marker not in bot:
        raise SystemExit('instagram items marker not found')
    bot = bot.replace(offer_marker, offer_branch + offer_marker, 1)

start_marker = '            if action == "instagram_confirm":\n'
end_marker = '            if action == "quick_stock_set":\n'
start = bot.find(start_marker)
end = bot.find(end_marker, start + 1) if start >= 0 else -1
if start < 0 or end < 0:
    raise SystemExit('instagram confirm block markers not found')

new_confirm = '''            if action == "instagram_confirm":
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
                        f"✅ Instagram savdo saqlandi.\\n\\n"
                        f"🔢 №{display_order_number(order)}\\n"
                        f"📚 {sum(int(q) for q in order.get('cart',{}).values())} ta kitob\\n"
                        f"💵 Mijozdan jami: ₩{int(order.get('grand_total',0)):,}\\n"
                        f"🚚 Pochta: {'mijoz to‘ladi' if fee else 'siz to‘ladingiz'}\\n"
                        f"📖 Kitob savdosi: ₩{int(order.get('total',0)):,}\\n\\n"
                        "📦 Ombor yangilandi va savdo statistikaga qo‘shildi.\\n\\n"
                        "📮 Pochta uchun ism, telefon va manzilni ham kiritasizmi?",
                        instagram_shipping_offer_keyboard(),
                    )
                except Exception as e:
                    send(chat_id, f"❌ Savdo saqlanmadi: {e}\\n\\nOmbor qayta tekshirildi.", admin_menu())
                    states.pop(chat_id, None)
                return

'''
bot = bot[:start] + new_confirm + bot[end:]

callback_start = bot.find('    if data == "shipsmart_save":\n')
callback_end = bot.find('    if data == "shipsmart_cancel":\n', callback_start + 1) if callback_start >= 0 else -1
if callback_start < 0 or callback_end < 0:
    raise SystemExit('smart shipping save callback markers not found')

new_callback = '''    if data == "shipsmart_save":
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

'''
bot = bot[:callback_start] + new_callback + bot[callback_end:]

bot_path.write_text(bot, encoding='utf-8')

bridge = bridge_path.read_text(encoding='utf-8')
if 'def enable_instagram_shipping(' not in bridge:
    marker = '\n\ndef delete_book(book):\n'
    addition = '''\n\ndef enable_instagram_shipping(cloud_id, name, phone, address):
    return rpc(
        "bot_instagram_shipping_enable",
        {
            "p_secret": SYNC_SECRET,
            "p_cloud_id": str(cloud_id),
            "p_name": str(name or "").strip(),
            "p_phone": str(phone or "").strip(),
            "p_address": str(address or "").strip(),
        },
    )
'''
    if marker not in bridge:
        raise SystemExit('cloud bridge delete_book marker not found')
    bridge = bridge.replace(marker, addition + marker, 1)
    bridge_path.write_text(bridge, encoding='utf-8')

print('Instagram shipping address flow patched')
