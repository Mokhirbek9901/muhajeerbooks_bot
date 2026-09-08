from pathlib import Path


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Missing patch anchor: {label}")
    return text.replace(old, new, 1)

# -------------------------
# cloud_bridge.py
# -------------------------
path = Path('cloud_bridge.py')
text = path.read_text(encoding='utf-8')
anchor = '''def delete_book(book):\n'''
insert = '''def sales_list(limit=5000):
    result = rpc(
        "bot_sales_list",
        {"p_secret": SYNC_SECRET, "p_limit": int(limit)},
    )
    return result if isinstance(result, list) else []


def mark_instagram_order(cloud_id):
    return rpc(
        "bot_mark_instagram_order",
        {"p_secret": SYNC_SECRET, "p_cloud_id": str(cloud_id)},
    )


'''
text = replace_once(text, anchor, insert + anchor, 'cloud sales methods')
path.write_text(text, encoding='utf-8')

# -------------------------
# sync_wrapper.py — preserve Instagram source on cloud retry
# -------------------------
path = Path('sync_wrapper.py')
text = path.read_text(encoding='utf-8')
old = '''                try:
                    result = _rpc("bot_order_create", {
                        "p_secret": SYNC_SECRET,
                        "p_order": order,
                        "p_preserve_stock": True,
                    })
                    if isinstance(result, dict) and result.get("id"):
                        order["cloud_order_id"] = str(result.get("id"))
                        order["source"] = "telegram"
                        local_orders[str(key)] = order
                        orders_changed = True
                except Exception as e:
                    print(f"Telegram buyurtmasini cloudga retry xatosi ({key}):", e)
'''
new = '''                try:
                    original_source = str(order.get("source") or "telegram")
                    result = _rpc("bot_order_create", {
                        "p_secret": SYNC_SECRET,
                        "p_order": order,
                        "p_preserve_stock": True,
                    })
                    if isinstance(result, dict) and result.get("id"):
                        cloud_id = str(result.get("id"))
                        order["cloud_order_id"] = cloud_id
                        if original_source == "instagram":
                            try:
                                _rpc("bot_mark_instagram_order", {
                                    "p_secret": SYNC_SECRET,
                                    "p_cloud_id": cloud_id,
                                })
                            except Exception as e:
                                print(f"Instagram source sync xatosi ({key}):", e)
                            order["source"] = "instagram"
                        else:
                            order["source"] = "telegram"
                        local_orders[str(key)] = order
                        orders_changed = True
                except Exception as e:
                    print(f"Telegram/Instagram buyurtmasini cloudga retry xatosi ({key}):", e)
'''
text = replace_once(text, old, new, 'sync Instagram source')
path.write_text(text, encoding='utf-8')

# -------------------------
# bot.py — menu, list, direct Instagram cloud save
# -------------------------
path = Path('bot.py')
text = path.read_text(encoding='utf-8')

text = replace_once(
    text,
    '''            [{"text": "⚡ Tezkor qoldiq"}],
            [{"text": "📷 Instagram savdo"}],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],''',
    '''            [{"text": "⚡ Tezkor qoldiq"}],
            [{"text": "📚 Sotilgan kitoblar"}],
            [{"text": "📷 Instagram savdo"}],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],''',
    'admin sold books menu',
)

old_save = '''    orders[order_id] = order
    save_orders()
    return order


# =========================
# BUYURTMANI YAKUNLASH
'''
new_save = '''    orders[order_id] = order
    save_orders()

    # Instagram savdoni darhol markaziy tarixga ham yozamiz.
    # Stock yuqorida allaqachon kamaygan, shuning uchun preserve_stock=True.
    try:
        cloud_result = cloud_bridge.create_order(order, preserve_stock=True)
        if isinstance(cloud_result, dict) and cloud_result.get("id"):
            cloud_id = str(cloud_result["id"])
            order["cloud_order_id"] = cloud_id
            cloud_bridge.mark_instagram_order(cloud_id)
            order["source"] = "instagram"
            orders[order_id] = order
            save_orders()
    except Exception as e:
        # Local savdo yo‘qolmaydi; sync_wrapper keyingi siklda qayta urinadi.
        print("Instagram savdoni Supabase'ga yozish xatosi:", e)

    return order


def _sold_book_date(raw):
    try:
        return _local_datetime(raw).strftime("%d.%m.%Y")
    except Exception:
        return "—"


def _local_sold_rows():
    rows = []
    for order in orders.values():
        if not isinstance(order, dict):
            continue
        if str(order.get("status") or "") not in ("accepted", "paid", "shipped", "delivered"):
            continue
        sold_at = order.get("created_at", "")
        source = str(order.get("source") or "telegram")
        items = order.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("name") or item.get("title") or "Kitob")
                try:
                    qty = max(1, int(item.get("qty") or item.get("quantity") or 1))
                except Exception:
                    qty = 1
                for _ in range(qty):
                    rows.append({"title": title, "source": source, "sold_at": sold_at})
            continue
        for bid, qty_raw in (order.get("cart") or {}).items():
            book = find_book(bid)
            title = str((book or {}).get("name") or "Kitob")
            try:
                qty = max(1, int(qty_raw))
            except Exception:
                qty = 1
            for _ in range(qty):
                rows.append({"title": title, "source": source, "sold_at": sold_at})
    rows.sort(key=lambda row: str(row.get("sold_at") or ""))
    return rows


def admin_sold_books_texts():
    try:
        rows = cloud_bridge.sales_list(5000)
    except Exception as e:
        print("Sotilgan kitoblar cloud tarixi xatosi:", e)
        rows = _local_sold_rows()

    if not rows:
        return ["📚 SOTILGAN KITOBLAR\n\nHozircha sotuv yo‘q."]

    lines = []
    for index, row in enumerate(rows, 1):
        title = str(row.get("title") or "Kitob").strip() or "Kitob"
        date = _sold_book_date(row.get("sold_at"))
        lines.append(f"{index}. {title} ({date})")

    chunks = []
    current = "📚 SOTILGAN KITOBLAR\n\n"
    for line in lines:
        candidate = current + line + "\n"
        if len(candidate) > 3500 and current.strip() != "📚 SOTILGAN KITOBLAR":
            chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


# =========================
# BUYURTMANI YAKUNLASH
'''
text = replace_once(text, old_save, new_save, 'Instagram cloud save and sold list')

handler_anchor = '''        if text == "📷 Instagram savdo":
'''
handler_insert = '''        if text == "📚 Sotilgan kitoblar":
            states.pop(chat_id, None)
            try:
                messages = admin_sold_books_texts()
                for index, value in enumerate(messages):
                    send(
                        chat_id,
                        value,
                        admin_menu() if index == len(messages) - 1 else None,
                    )
            except Exception as e:
                send(chat_id, f"❌ Sotuv tarixini ochib bo‘lmadi: {e}", admin_menu())
            return

'''
text = replace_once(text, handler_anchor, handler_insert + handler_anchor, 'sold list handler')
path.write_text(text, encoding='utf-8')

print('Added shared sold-books history to bot')
