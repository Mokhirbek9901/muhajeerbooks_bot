from pathlib import Path
import re

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

# 1) Instagram input: only book name + quantity. Keep fuzzy matching.
pat = r'def parse_instagram_sale_items\(text\):\n.*?(?=\ndef instagram_sale_items_text\()'
new = '''def parse_instagram_sale_items(text):
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
        if not matches:
            matches = _instagram_fuzzy_matches(query)

        if len(matches) != 1:
            if not matches:
                errors.append(f"• {query} — topilmadi")
            else:
                names = ", ".join(str(b.get("name", "")) for b in matches[:4])
                errors.append(f"• {query} — aniq emas: {names}")
            continue

        book = matches[0]
        bid = str(book.get("id"))
        selected[bid] = selected.get(bid, 0) + int(qty)

    if not selected and not errors:
        errors.append("Kitoblar yozilmadi.")

    return selected, errors


'''
t2, n = re.subn(pat, lambda m: new, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f'parse block not found: {n}')
t = t2

pat = r'def instagram_sale_items_text\(cart, sale_prices=None\):\n.*?(?=\ndef instagram_postage_keyboard\()'
new = '''def instagram_sale_items_text(cart):
    lines = []
    for bid, qty in cart.items():
        b = find_book(bid)
        name = b.get("name", "Kitob") if b else "Kitob"
        stock = int(b.get("stock", 0)) if b else 0
        lines.append(f"• {name} × {int(qty)}  (omborda {stock} ta)")
    return "\\n".join(lines)


'''
t2, n = re.subn(pat, lambda m: new, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f'items text block not found: {n}')
t = t2

t = t.replace(
    '[{"text": "👤 Pochta mijozdan"}, {"text": "🎁 Pochta mendan"}]',
    '[{"text": "👤 Pochtani mijoz to‘ladi"}, {"text": "🎁 Pochtani men to‘ladim"}]',
    1
)

# 2) Save: entered total is exactly what customer paid. If customer paid postage,
# ₩4,000 is delivery revenue and the rest is book revenue. If admin paid postage,
# all received money is book revenue; report already counts ₩4,000 postage expense.
pat = r'def save_instagram_sale\(state\):\n.*?(?=\n# =========================\n# BUYURTMANI YAKUNLASH)'
m = re.search(pat, t, flags=re.S)
if not m:
    raise RuntimeError('save_instagram_sale block not found')
block = m.group(0)
block = block.replace(
    '"unit_price": int(state.get("sale_prices", {}).get(str(bid), effective_price(b))),',
    '"unit_price": int(effective_price(b)),',
    1
)
old_calc = '''    books_total = sum(int(item.get("unit_price", 0)) * int(item.get("qty", 0)) for item in items)
    customer_pays_postage = bool(state.get("customer_pays_postage", False))
    delivery_fee = int(DELIVERY_FEE) if customer_pays_postage else 0
    grand_total = books_total + delivery_fee
'''
new_calc = '''    received_total = int(state.get("received_total", 0) or 0)
    if received_total <= 0:
        raise ValueError("Mijozdan olingan jami summa kiritilmagan.")

    customer_pays_postage = bool(state.get("customer_pays_postage", False))
    delivery_fee = int(DELIVERY_FEE) if customer_pays_postage else 0
    if customer_pays_postage and received_total < delivery_fee:
        raise ValueError("Jami summa pochta pulidan kam bo‘lishi mumkin emas.")

    books_total = received_total - delivery_fee if customer_pays_postage else received_total
    grand_total = received_total
'''
if old_calc not in block:
    raise RuntimeError('save calculation anchor not found')
block = block.replace(old_calc, new_calc, 1)
block = block.replace(
    '"source": "instagram",',
    '"source": "instagram",\n        "instagram_received_total": received_total,\n        "postage_paid_by": "customer" if customer_pays_postage else "admin",',
    1
)
t = t[:m.start()] + block + t[m.end():]

# 3) Initial admin prompt.
old_prompt = '''                "📷 INSTAGRAM SAVDO\\n\\n"
                "Har qatorga: KITOB NOMI + SONI + 1 DONA SOTILGAN NARXINI yozing.\\n\\n"
                "Masalan:\\n"
                "Dafina 1 10000\\n"
                "Boy ota kambag‘al ota 2 12000\\n\\n"
                "Narxni arzonroq yoki qimmatroq yozishingiz mumkin.\\n"
                "Narx yozmasangiz, botdagi hozirgi narx olinadi.",'''
new_prompt = '''                "📷 INSTAGRAM SAVDO\\n\\n"
                "Har qatorga KITOB NOMI + SONINI yozing.\\n\\n"
                "Masalan:\\n"
                "Dafina 1\\n"
                "Boy ota kambag‘al ota 2\\n\\n"
                "Nomda ozgina xato bo‘lsa ham bot topishga harakat qiladi.",'''
if old_prompt not in t:
    raise RuntimeError('initial prompt anchor not found')
t = t.replace(old_prompt, new_prompt, 1)

# 4) State flow.
pat = r'            if action == "instagram_items":\n.*?(?=            if action == "quick_stock_set":)'
new = '''            if action == "instagram_items":
                cart, errors = parse_instagram_sale_items(text)
                if errors:
                    send(
                        chat_id,
                        "❌ Ayrim kitoblarni aniqlay olmadim:\\n\\n" + "\\n".join(errors) +
                        "\\n\\nQaytadan yozing. Masalan:\\nDafina 1"
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
                    send(chat_id, "❌ Omborda yetarli emas:\\n\\n" + "\\n".join(shortages))
                    return

                state["cart"] = cart
                state["action"] = "instagram_amount"
                send(
                    chat_id,
                    "✅ Kitoblar topildi:\\n\\n" +
                    instagram_sale_items_text(cart) +
                    "\\n\\n💰 Mijozdan olgan JAMI summani yozing.\\n"
                    "Pochta puli ham ichida bo‘lsa, qo‘shib yozing.\\n"
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
                    f"💰 Mijozdan olindi: ₩{amount:,}\\n\\n🚚 Pochta pulini kim to‘ladi?",
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
                books_total = received - fee if customer_pays else received
                state["books_total"] = books_total
                state["action"] = "instagram_confirm"
                postage_text = "Mijoz to‘ladi — ₩4,000" if customer_pays else "Siz to‘ladingiz — ₩4,000 xarajat"

                send(
                    chat_id,
                    "🧾 INSTAGRAM SAVDO — TEKSHIRING\\n\\n" +
                    instagram_sale_items_text(state.get("cart", {})) +
                    f"\\n\\n💵 Mijozdan jami: ₩{received:,}" +
                    f"\\n🚚 Pochta: {postage_text}" +
                    f"\\n📚 Kitob savdosi: ₩{books_total:,}" +
                    "\\n\\n✅ Saqlasangiz ombordan kitoblar ayriladi va savdo barcha statistikaga qo‘shiladi.",
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
                        f"✅ Instagram savdo saqlandi.\\n\\n"
                        f"🔢 №{order['order_id']}\\n"
                        f"📚 {sum(int(q) for q in order.get('cart',{}).values())} ta kitob\\n"
                        f"💵 Mijozdan jami: ₩{int(order.get('grand_total',0)):,}\\n"
                        f"🚚 Pochta: {'mijoz to‘ladi' if fee else 'siz to‘ladingiz'}\\n"
                        f"📖 Kitob savdosi: ₩{int(order.get('total',0)):,}\\n\\n"
                        "📦 Ombor yangilandi va savdo statistikaga qo‘shildi.",
                        admin_menu()
                    )
                except Exception as e:
                    send(chat_id, f"❌ Savdo saqlanmadi: {e}\\n\\nOmbor qayta tekshirildi.", admin_menu())
                    states.pop(chat_id, None)
                return

'''
t2, n = re.subn(pat, lambda m: new, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f'instagram state block not found: {n}')
t = t2

p.write_text(t, encoding='utf-8')
print('Instagram simple flow enabled')
