from pathlib import Path
import re

p = Path("bot.py")
t = p.read_text(encoding="utf-8")

# 1) Instagram sale parser + display: optional actual sale price per book.
pattern = r'def parse_instagram_sale_items\(text\):\n.*?(?=\ndef instagram_postage_keyboard\(\):)'
replacement = '''def _instagram_qty_token(token):
    value = str(token or "").casefold().strip()
    if value.endswith("ta"):
        value = value[:-2].strip()
    if value.startswith("x"):
        value = value[1:].strip()
    if value.endswith("x"):
        value = value[:-1].strip()
    try:
        qty = int(value)
        return qty if qty > 0 else None
    except Exception:
        return None


def _instagram_money_token(token):
    value = str(token or "").strip().replace("₩", "").replace(",", "").replace(".", "").replace(" ", "")
    try:
        amount = int(value)
        return amount if amount > 0 else None
    except Exception:
        return None


def parse_instagram_sale_items(text):
    refresh_books()
    exact = {}
    for b in books:
        exact.setdefault(_instagram_name_key(b.get("name", "")), []).append(b)

    selected = {}
    sale_prices = {}
    errors = []

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            errors.append(f"• {line} — soni yozilmagan")
            continue

        # Ikki ko‘rinish qabul qilinadi:
        #   Dafina 1              -> katalog narxi
        #   Dafina 1 10000        -> 1 dona real sotilgan narx ₩10,000
        custom_price = None
        qty = None
        query_parts = None

        if len(parts) >= 3:
            maybe_qty = _instagram_qty_token(parts[-2])
            maybe_price = _instagram_money_token(parts[-1])
            if maybe_qty is not None and maybe_price is not None:
                qty = maybe_qty
                custom_price = maybe_price
                query_parts = parts[:-2]

        if qty is None:
            qty = _instagram_qty_token(parts[-1])
            query_parts = parts[:-1]

        if qty is None or not query_parts:
            errors.append(f"• {line} — format noto‘g‘ri. Masalan: Dafina 1 10000")
            continue

        query = " ".join(query_parts).strip()
        qkey = _instagram_name_key(query)
        matches = exact.get(qkey, [])
        if not matches:
            matches = [
                b for b in books
                if qkey and (
                    qkey in _instagram_name_key(b.get("name", ""))
                    or _instagram_name_key(b.get("name", "")) in qkey
                )
            ]

        if len(matches) != 1:
            if not matches:
                errors.append(f"• {query} — topilmadi")
            else:
                names = ", ".join(str(b.get("name", "")) for b in matches[:4])
                errors.append(f"• {query} — aniq emas: {names}")
            continue

        book = matches[0]
        bid = str(book.get("id"))
        actual_price = int(custom_price if custom_price is not None else effective_price(book))
        if actual_price <= 0:
            errors.append(f"• {query} — narxi 0. Sotilgan narxni yozing, masalan: {query} {qty} 10000")
            continue

        if bid in selected and int(sale_prices.get(bid, actual_price)) != actual_price:
            errors.append(f"• {query} — bir xil kitobni turli narxda kiritmang; alohida savdo qilib saqlang")
            continue

        selected[bid] = selected.get(bid, 0) + int(qty)
        sale_prices[bid] = actual_price

    if not selected and not errors:
        errors.append("Kitoblar yozilmadi.")

    return selected, sale_prices, errors


def instagram_sale_items_text(cart, sale_prices=None):
    sale_prices = sale_prices or {}
    lines = []
    for bid, qty in cart.items():
        b = find_book(bid)
        name = b.get("name", "Kitob") if b else "Kitob"
        stock = int(b.get("stock", 0)) if b else 0
        catalog_price = int(effective_price(b)) if b else 0
        actual_price = int(sale_prices.get(str(bid), catalog_price) or 0)
        subtotal = actual_price * int(qty)
        price_note = f"₩{actual_price:,}/dona"
        if b and catalog_price > 0 and actual_price != catalog_price:
            price_note += f" (katalog ₩{catalog_price:,})"
        lines.append(f"• {name} × {int(qty)} — {price_note} = ₩{subtotal:,}  (omborda {stock} ta)")
    return "\\n".join(lines)


'''
t2, n = re.subn(pattern, replacement, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f"Instagram parser block topilmadi: {n}")
t = t2

# 2) Save actual per-book sale price in order items and calculate total from it.
func_pat = r'def save_instagram_sale\(state\):\n.*?(?=\n# =========================\n# BUYURTMANI YAKUNLASH)'
m = re.search(func_pat, t, flags=re.S)
if not m:
    raise RuntimeError("save_instagram_sale topilmadi")
block = m.group(0)
old_price = '"unit_price": int(effective_price(b)),'
new_price = '"unit_price": int(state.get("sale_prices", {}).get(str(bid), effective_price(b))),' 
if old_price not in block:
    raise RuntimeError("Instagram unit_price anchor topilmadi")
block = block.replace(old_price, new_price, 1)
old_total = 'books_total = int(state.get("sale_amount", 0))'
new_total = 'books_total = sum(int(item.get("unit_price", 0)) * int(item.get("qty", 0)) for item in items)'
if old_total not in block:
    raise RuntimeError("Instagram books_total anchor topilmadi")
block = block.replace(old_total, new_total, 1)
t = t[:m.start()] + block + t[m.end():]

# 3) Make admin instructions explicit and simple.
old_prompt = '''                "Sotilgan kitoblarni har qatorga nomi va soni bilan yozing.\\n\\n"
                "Masalan:\\n"
                "Dafina 1\\n"
                "Boy ota kambag‘al ota 2\\n\\n"
                "Oxiridagi son — nechta sotilganini bildiradi.",'''
new_prompt = '''                "Har qatorga: KITOB NOMI + SONI + 1 DONA SOTILGAN NARXINI yozing.\\n\\n"
                "Masalan:\\n"
                "Dafina 1 10000\\n"
                "Boy ota kambag‘al ota 2 12000\\n\\n"
                "Narxni arzonroq yoki qimmatroq yozishingiz mumkin.\\n"
                "Narx yozmasangiz, botdagi hozirgi narx olinadi.",'''
if old_prompt not in t:
    raise RuntimeError("Instagram admin prompt anchor topilmadi")
t = t.replace(old_prompt, new_prompt, 1)

# 4) Simplify flow: custom prices calculate book total automatically, then ask postage.
state_pat = r'            if action == "instagram_items":\n.*?(?=            if action == "quick_stock_set":)'
state_new = '''            if action == "instagram_items":
                cart, sale_prices, errors = parse_instagram_sale_items(text)
                if errors:
                    send(
                        chat_id,
                        "❌ Ayrim qatorlarni aniqlay olmadim:\\n\\n" + "\\n".join(errors) +
                        "\\n\\nQaytadan yozing. Masalan:\\nDafina 1 10000"
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
                state["sale_prices"] = sale_prices
                amount = sum(int(sale_prices[str(bid)]) * int(qty) for bid, qty in cart.items())
                state["sale_amount"] = amount
                state["action"] = "instagram_postage"
                send(
                    chat_id,
                    "✅ Kitoblar va sotilgan narxlar:\\n\\n" +
                    instagram_sale_items_text(cart, sale_prices) +
                    f"\\n\\n💰 Kitoblar jami: ₩{amount:,}\\n\\n🚚 Pochta pulini kim to‘ladi?",
                    instagram_postage_keyboard()
                )
                return

            if action == "instagram_postage":
                if text not in ("👤 Pochta mijozdan", "🎁 Pochta mendan"):
                    send(chat_id, "Quyidagi 2 ta tugmadan birini tanlang.", instagram_postage_keyboard())
                    return

                state["customer_pays_postage"] = text == "👤 Pochta mijozdan"
                state["action"] = "instagram_confirm"
                fee = int(DELIVERY_FEE) if state["customer_pays_postage"] else 0
                sale_prices = state.get("sale_prices", {})
                amount = sum(
                    int(sale_prices.get(str(bid), 0)) * int(qty)
                    for bid, qty in state.get("cart", {}).items()
                )
                state["sale_amount"] = amount
                postage_text = "Mijoz +₩4,000 to‘ladi" if fee else "Siz to‘laysiz (hisobotda ₩4,000 xarajat)"
                send(
                    chat_id,
                    "🧾 INSTAGRAM SAVDO — TEKSHIRING\\n\\n" +
                    instagram_sale_items_text(state.get("cart", {}), sale_prices) +
                    f"\\n\\n💰 Kitoblar: ₩{amount:,}" +
                    f"\\n🚚 Pochta: {postage_text}" +
                    f"\\n💵 Jami tushum: ₩{amount + fee:,}" +
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
                        f"💰 Kitoblar: ₩{int(order.get('total',0)):,}\\n"
                        f"🚚 Yetkazish: {'₩4,000 mijozdan' if fee else 'sizdan ₩4,000'}\\n"
                        f"💵 Tushum: ₩{int(order.get('grand_total',0)):,}\\n\\n"
                        "📦 Ombor yangilandi va savdo statistikaga qo‘shildi.",
                        admin_menu()
                    )
                except Exception as e:
                    send(chat_id, f"❌ Savdo saqlanmadi: {e}\\n\\nOmbor qayta tekshirildi.", admin_menu())
                    states.pop(chat_id, None)
                return

'''
t2, n = re.subn(state_pat, state_new, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f"Instagram state block topilmadi: {n}")
t = t2

p.write_text(t, encoding="utf-8")
print("Instagram custom sale prices enabled")
