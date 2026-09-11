from pathlib import Path

path = Path("bot.py")
s = path.read_text(encoding="utf-8")


def once(old, new, label):
    global s
    if old not in s:
        raise RuntimeError(f"patch marker not found: {label}")
    s = s.replace(old, new, 1)

# 1) Persistent queue file.
once(
    'EXPENSES_FILE = os.path.join(DATA_DIR, "expenses.json")\n',
    'EXPENSES_FILE = os.path.join(DATA_DIR, "expenses.json")\nSHIPPING_QUEUE_FILE = os.path.join(DATA_DIR, "shipping_queue.json")\n',
    'shipping file',
)

# 2) Queue helpers before MENYULAR.
marker = '''# =========================\n# MENYULAR\n# =========================\n'''
helpers = r'''
# =========================
# POCHTA UCHUN ZAKASLAR
# =========================

def _shipping_queue_load():
    try:
        with open(SHIPPING_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        data = {}
    manual = data.get("manual")
    dismissed = data.get("dismissed_order_ids")
    return {
        "manual": manual if isinstance(manual, dict) else {},
        "dismissed_order_ids": [str(x) for x in dismissed] if isinstance(dismissed, list) else [],
    }


def _shipping_queue_save(data):
    safe = {
        "manual": data.get("manual", {}) if isinstance(data.get("manual", {}), dict) else {},
        "dismissed_order_ids": sorted(set(str(x) for x in data.get("dismissed_order_ids", []))),
    }
    tmp = SHIPPING_QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, SHIPPING_QUEUE_FILE)


def _shipping_books_text(order):
    lines = []
    items = order.get("items")
    if isinstance(items, list) and items:
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or "Kitob").strip() or "Kitob"
            try:
                qty = max(1, int(item.get("qty") or item.get("quantity") or 1))
            except Exception:
                qty = 1
            lines.append(f"• {name} × {qty}")
    if not lines:
        for bid, qty_raw in (order.get("cart") or {}).items():
            try:
                qty = max(1, int(qty_raw))
            except Exception:
                qty = 1
            book = find_book(bid)
            name = str((book or {}).get("name") or f"Kitob #{bid}")
            lines.append(f"• {name} × {qty}")
    return "\n".join(lines) if lines else "• Kitob ma’lumoti yo‘q"


def _shipping_source_label(source):
    return {
        "telegram": "🤖 Telegram bot",
        "app": "📱 Ilova / Web",
        "manual": "✍️ Qo‘lda",
    }.get(str(source), "📦 Zakas")


def _shipping_status_label(status):
    return {
        "pending": "🟡 Kutilmoqda",
        "accepted": "📦 Qabul qilingan",
        "paid": "🟢 To‘langan",
        "shipped": "🚚 Jo‘natilgan",
    }.get(str(status), str(status or "—"))


def shipping_queue_entries(source_filter="all"):
    load_orders()
    data = _shipping_queue_load()
    dismissed = set(data.get("dismissed_order_ids", []))
    entries = []

    for key, order in orders.items():
        if not isinstance(order, dict):
            continue
        source = str(order.get("source") or "telegram")
        if source not in ("telegram", "app"):
            continue
        status = str(order.get("status") or "pending")
        if status in ("cancelled", "stock_problem"):
            continue
        try:
            oid_num = int(order.get("order_id", key) or 0)
        except Exception:
            oid_num = 0
        if oid_num and oid_num < STATS_RESET_ORDER_ID:
            continue
        oid = str(order.get("order_id") or key)
        if oid in dismissed:
            continue
        if source_filter not in ("all", source):
            continue
        phone = str(order.get("phone") or "").strip()
        address = str(order.get("address") or "").strip()
        name = str(order.get("name") or "Noma’lum").strip() or "Noma’lum"
        if not phone and not address:
            continue
        entries.append({
            "queue_kind": "order",
            "queue_id": oid,
            "source": source,
            "name": name,
            "phone": phone or "—",
            "address": address or "—",
            "books": _shipping_books_text(order),
            "status": status,
            "created_at": str(order.get("created_at") or ""),
            "address_photo_file_id": "",
        })

    if source_filter in ("all", "manual"):
        for mid, row in (data.get("manual") or {}).items():
            if not isinstance(row, dict):
                continue
            entry = dict(row)
            entry.update({
                "queue_kind": "manual",
                "queue_id": str(mid),
                "source": "manual",
                "status": "manual",
            })
            entries.append(entry)

    entries.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    return entries


def shipping_queue_menu():
    return {
        "keyboard": [
            [{"text": "📋 Barcha zakaslar"}, {"text": "➕ Qo‘lda zakas"}],
            [{"text": "🤖 Bot zakaslari"}, {"text": "📱 Ilova zakaslari"}],
            [{"text": "✍️ Qo‘lda kiritilgan"}],
            [{"text": "⬅️ Admin panel"}],
        ],
        "resize_keyboard": True,
    }


def _shipping_copy_button(label, value):
    value = str(value or "").strip()
    if not value or value == "—" or len(value) > 256:
        return None
    return {"text": label, "copy_text": {"text": value}}


def shipping_entry_keyboard(entry):
    rows = []
    name_btn = _shipping_copy_button("👤 Ismni nusxalash", entry.get("name"))
    phone_btn = _shipping_copy_button("📞 Telefonni nusxalash", entry.get("phone"))
    address_btn = _shipping_copy_button("📍 Manzilni nusxalash", entry.get("address"))
    if name_btn:
        rows.append([name_btn])
    if phone_btn:
        rows.append([phone_btn])
    if address_btn:
        rows.append([address_btn])
    kind = "m" if entry.get("queue_kind") == "manual" else "o"
    rows.append([{
        "text": "🗑 Zakasni o‘chirish",
        "callback_data": f"shipdel_{kind}_{entry.get('queue_id')}",
    }])
    return {"inline_keyboard": rows}


def shipping_entry_text(entry, index=None):
    head = f"📦 ZAKAS {index}" if index is not None else "📦 ZAKAS"
    source = _shipping_source_label(entry.get("source"))
    lines = [
        head,
        f"{source}",
        "",
        f"👤 Ism: {entry.get('name') or '—'}",
        f"📞 Telefon: {entry.get('phone') or '—'}",
        f"📍 Manzil: {entry.get('address') or '—'}",
        "",
        "📚 Kitoblar:",
        str(entry.get("books") or "• Kitob ma’lumoti yo‘q"),
    ]
    if entry.get("queue_kind") == "order":
        lines.extend(["", f"Holati: {_shipping_status_label(entry.get('status'))}"])
    return "\n".join(lines)


def send_shipping_queue(chat_id, source_filter="all"):
    entries = shipping_queue_entries(source_filter)
    labels = {
        "all": "BARCHA ZAKASLAR",
        "telegram": "BOT ZAKASLARI",
        "app": "ILOVA ZAKASLARI",
        "manual": "QO‘LDA KIRITILGAN",
    }
    if not entries:
        send(chat_id, f"📦 {labels.get(source_filter, 'ZAKASLAR')}\n\nHozircha zakas yo‘q.", shipping_queue_menu())
        return
    send(chat_id, f"📦 {labels.get(source_filter, 'ZAKASLAR')} — {len(entries)} ta\n\nTelefon va manzilni alohida tugma bilan nusxalashingiz mumkin.")
    for index, entry in enumerate(entries[:40], 1):
        text = shipping_entry_text(entry, index)
        markup = shipping_entry_keyboard(entry)
        photo_id = str(entry.get("address_photo_file_id") or "").strip()
        if photo_id:
            try:
                api("sendPhoto", {
                    "chat_id": chat_id,
                    "photo": photo_id,
                    "caption": text,
                    "reply_markup": json.dumps(markup, ensure_ascii=False),
                })
                continue
            except Exception as exc:
                print("Zakas manzil rasmini yuborish xatosi:", exc)
        send(chat_id, text, markup)
    if len(entries) > 40:
        send(chat_id, f"ℹ️ Hozir birinchi 40 ta ko‘rsatildi. Jami {len(entries)} ta.", shipping_queue_menu())
    else:
        send(chat_id, "✅ Pochta uchun zakaslar shu yerda.", shipping_queue_menu())


def save_manual_shipping_order(state):
    data = _shipping_queue_load()
    manual = data.setdefault("manual", {})
    mid = str(int(time.time() * 1000))
    while mid in manual:
        time.sleep(0.001)
        mid = str(int(time.time() * 1000))
    manual[mid] = {
        "name": str(state.get("name") or "Noma’lum").strip() or "Noma’lum",
        "phone": str(state.get("phone") or "—").strip() or "—",
        "address": str(state.get("address") or "—").strip() or "—",
        "books": str(state.get("books") or "• Kitob ma’lumoti yo‘q").strip(),
        "address_photo_file_id": str(state.get("address_photo_file_id") or "").strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _shipping_queue_save(data)
    entry = dict(manual[mid])
    entry.update({"queue_kind": "manual", "queue_id": mid, "source": "manual", "status": "manual"})
    return entry


def delete_shipping_queue_entry(kind, queue_id):
    data = _shipping_queue_load()
    queue_id = str(queue_id)
    if kind == "m":
        existed = queue_id in data.get("manual", {})
        data.get("manual", {}).pop(queue_id, None)
    else:
        dismissed = set(data.get("dismissed_order_ids", []))
        existed = queue_id not in dismissed
        dismissed.add(queue_id)
        data["dismissed_order_ids"] = sorted(dismissed)
    _shipping_queue_save(data)
    return existed

'''
if marker not in s:
    raise RuntimeError("menus marker missing")
s = s.replace(marker, helpers + marker, 1)

# 3) Admin menu button.
once(
    '            [{"text": "📷 Instagram savdo"}],\n            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],\n',
    '            [{"text": "📷 Instagram savdo"}],\n            [{"text": "📦 Zakaslar"}],\n            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],\n',
    'admin queue button',
)

# 4) Admin text handlers before Instagram sale.
once(
    '        if text == "📷 Instagram savdo":\n',
    '''        if text == "📦 Zakaslar":\n            states.pop(chat_id, None)\n            send(chat_id, "📦 ZAKASLAR\\n\\nPochta ilovasiga ko‘chirish uchun zakaslarni shu yerda boshqarasiz.", shipping_queue_menu())\n            return\n\n        if text == "📋 Barcha zakaslar":\n            states.pop(chat_id, None); send_shipping_queue(chat_id, "all"); return\n        if text == "🤖 Bot zakaslari":\n            states.pop(chat_id, None); send_shipping_queue(chat_id, "telegram"); return\n        if text == "📱 Ilova zakaslari":\n            states.pop(chat_id, None); send_shipping_queue(chat_id, "app"); return\n        if text == "✍️ Qo‘lda kiritilgan":\n            states.pop(chat_id, None); send_shipping_queue(chat_id, "manual"); return\n        if text == "⬅️ Admin panel":\n            states.pop(chat_id, None); send(chat_id, "⚙️ Admin panel", admin_menu()); return\n        if text == "➕ Qo‘lda zakas":\n            states[chat_id] = {"action": "shipping_name"}\n            send(chat_id, "👤 Mijoz ismini yozing:", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})\n            return\n\n        if text == "📷 Instagram savdo":\n''',
    'queue handlers',
)

# 5) Manual order state machine before Instagram states.
once(
    '            if action == "instagram_items":\n',
    '''            if action == "shipping_name":\n                if not text:\n                    send(chat_id, "❌ Ismni yozing.")\n                    return\n                state["name"] = text\n                state["action"] = "shipping_phone"\n                send(chat_id, "📞 Telefon raqamini yozing.\\nMasalan: 01012345678")\n                return\n\n            if action == "shipping_phone":\n                if not text:\n                    send(chat_id, "❌ Telefon raqamini yozing.")\n                    return\n                state["phone"] = text\n                state["action"] = "shipping_address"\n                send(chat_id, "📍 To‘liq manzilni yozing.\\n\\nIstasangiz manzil screenshot/rasmini ham yuborishingiz mumkin. Rasm yuborsangiz, nusxa olish uchun keyin manzil matnini ham so‘rayman.")\n                return\n\n            if action == "shipping_address":\n                photos = message.get("photo") or []\n                caption = str(message.get("caption") or "").strip()\n                if photos:\n                    state["address_photo_file_id"] = str(photos[-1].get("file_id") or "")\n                    if caption:\n                        state["address"] = caption\n                        state["action"] = "shipping_books"\n                        send(chat_id, "📚 Qaysi kitob(lar)ni zakas qilganini yozing.\\nMasalan:\\nDafina 1 ta\\nSaodat asri 2 ta")\n                    else:\n                        state["action"] = "shipping_address_text"\n                        send(chat_id, "✅ Manzil rasmi saqlandi.\\n\\n📍 Endi nusxa olish uchun manzilni MATN ko‘rinishida yozing:")\n                    return\n                if not text:\n                    send(chat_id, "❌ Manzilni yozing yoki manzil rasmini yuboring.")\n                    return\n                state["address"] = text\n                state["action"] = "shipping_books"\n                send(chat_id, "📚 Qaysi kitob(lar)ni zakas qilganini yozing.\\nMasalan:\\nDafina 1 ta\\nSaodat asri 2 ta")\n                return\n\n            if action == "shipping_address_text":\n                if not text:\n                    send(chat_id, "❌ Manzil matnini yozing.")\n                    return\n                state["address"] = text\n                state["action"] = "shipping_books"\n                send(chat_id, "📚 Qaysi kitob(lar)ni zakas qilganini yozing.\\nMasalan:\\nDafina 1 ta\\nSaodat asri 2 ta")\n                return\n\n            if action == "shipping_books":\n                if not text:\n                    send(chat_id, "❌ Kitob nomi va sonini yozing.")\n                    return\n                state["books"] = text\n                entry = save_manual_shipping_order(state)\n                states.pop(chat_id, None)\n                send(chat_id, "✅ Zakas Zakaslar bo‘limiga saqlandi.")\n                photo_id = str(entry.get("address_photo_file_id") or "").strip()\n                if photo_id:\n                    try:\n                        api("sendPhoto", {\n                            "chat_id": chat_id,\n                            "photo": photo_id,\n                            "caption": shipping_entry_text(entry),\n                            "reply_markup": json.dumps(shipping_entry_keyboard(entry), ensure_ascii=False),\n                        })\n                    except Exception:\n                        send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))\n                else:\n                    send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))\n                send(chat_id, "📦 Zakaslar", shipping_queue_menu())\n                return\n\n            if action == "instagram_items":\n''',
    'manual state flow',
)

# 6) Admin unknown-message whitelist includes queue keyboard texts so they are not rejected.
once(
    '            "📞 Bog‘lanish"\n        ):\n',
    '            "📞 Bog‘lanish",\n            "📦 Zakaslar",\n            "📋 Barcha zakaslar",\n            "➕ Qo‘lda zakas",\n            "🤖 Bot zakaslari",\n            "📱 Ilova zakaslari",\n            "✍️ Qo‘lda kiritilgan",\n            "⬅️ Admin panel"\n        ):\n',
    'admin whitelist',
)

# 7) Callback delete confirmation before HOME.
once(
    '    # =========================\n    # HOME\n    # =========================\n',
    '''    if data.startswith("shipdel_"):\n        if not is_admin(chat_id):\n            return\n        parts = data.split("_", 2)\n        if len(parts) != 3 or parts[1] not in ("m", "o"):\n            return\n        kind, queue_id = parts[1], parts[2]\n        send(\n            chat_id,\n            "⚠️ Rostdan ham bu zakasni POCHTA ZAKASLAR ro‘yxatidan o‘chirasizmi?\\n\\nAsl buyurtma, ombor va statistika o‘zgarmaydi.",\n            {"inline_keyboard": [\n                [{"text": "✅ Ha, o‘chirish", "callback_data": f"shipdelok_{kind}_{queue_id}"}],\n                [{"text": "❌ Yo‘q", "callback_data": "shipdelno"}],\n            ]},\n        )\n        return\n\n    if data.startswith("shipdelok_"):\n        if not is_admin(chat_id):\n            return\n        parts = data.split("_", 2)\n        if len(parts) != 3 or parts[1] not in ("m", "o"):\n            return\n        delete_shipping_queue_entry(parts[1], parts[2])\n        send(chat_id, "✅ Zakas pochta ro‘yxatidan o‘chirildi. Asl buyurtmaga tegilmadi.", shipping_queue_menu())\n        return\n\n    if data == "shipdelno":\n        if is_admin(chat_id):\n            send(chat_id, "❎ O‘chirish bekor qilindi.", shipping_queue_menu())\n        return\n\n    # =========================\n    # HOME\n    # =========================\n''',
    'delete callbacks',
)

path.write_text(s, encoding="utf-8")
print("shipping queue patch applied")
