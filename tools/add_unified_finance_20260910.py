from pathlib import Path

path = Path('bot.py')
text = path.read_text(encoding='utf-8')

helpers = r'''

FINANCE_PERIOD_LABELS = {
    "today": "Bugun",
    "week": "Shu hafta",
    "month": "Shu oy",
    "all": "Hammasi",
}

FINANCE_EXPENSE_CATEGORIES = {
    "🚚 Pochta": "postage",
    "📦 Qadoqlash": "packaging",
    "📣 Reklama": "ads",
    "🚕 Transport": "transport",
    "🧾 Boshqa": "other",
}


def finance_report_keyboard():
    return {"inline_keyboard": [
        [{"text": "📅 Bugun", "callback_data": "finance_today"}, {"text": "📆 Shu hafta", "callback_data": "finance_week"}],
        [{"text": "🗓 Shu oy", "callback_data": "finance_month"}, {"text": "📊 Hammasi", "callback_data": "finance_all"}],
        [{"text": "⬅️ Admin panel", "callback_data": "admin"}],
    ]}


def finance_report_text(period="month"):
    period = period if period in FINANCE_PERIOD_LABELS else "month"
    try:
        r = cloud_bridge.finance_report(period)
    except Exception as exc:
        return f"❌ Moliya hisoboti serverdan olinmadi: {exc}"

    def n(key):
        try:
            return int(float(r.get(key, 0) or 0))
        except Exception:
            return 0

    try:
        margin = float(r.get("margin_percent", 0) or 0)
    except Exception:
        margin = 0.0
    postage_note = " (taxmin)" if r.get("postage_is_estimated") else ""
    return "\n".join([
        f"💰 MOLIYA — {FINANCE_PERIOD_LABELS[period].upper()}",
        "━━━━━━━━━━━━━━",
        f"💵 Jami tushum: ₩{n('total_revenue'):,}",
        f"📚 Kitob savdosi: ₩{n('books_revenue'):,}",
        f"🚚 Yetkazish tushumi: ₩{n('delivery_revenue'):,}",
        "",
        f"📦 Sotilgan kitoblar tannarxi: ₩{n('cost_of_goods'):,}",
        f"📖 Kitobdan foyda: ₩{n('book_profit'):,}",
        f"📮 Pochta xarajati{postage_note}: ₩{n('postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        f"➖ Jami chiqim: ₩{n('total_expenses'):,}",
        "━━━━━━━━━━━━━━",
        f"✅ SOF FOYDA: ₩{n('net_profit'):,}",
        f"📈 Sof marja: {margin:.1f}%",
        "",
        f"📚 Sotilgan kitob: {n('sold_books')} dona",
        f"📦 Jo‘natilgan buyurtma: {n('shipped_orders')} ta",
        "",
        "ℹ️ Sof foyda = kitob + yetkazish tushumi − tannarx − pochta − boshqa chiqimlar.",
        "Kitobning kelish narxini alohida chiqimga yana qo‘shmang — tannarxda hisoblangan.",
    ])


def finance_expense_category_keyboard():
    return {"keyboard": [
        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],
        [{"text": "📣 Reklama"}, {"text": "🚕 Transport"}],
        [{"text": "🧾 Boshqa"}],
        [{"text": "❌ Bekor qilish"}],
    ], "resize_keyboard": True}
'''

if 'def finance_report_text(period="month"):' not in text:
    marker = '\ndef handle_message(message):\n'
    if marker not in text:
        raise SystemExit('handle_message marker not found')
    text = text.replace(marker, helpers + marker, 1)

old_menu = '''            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],
            [{"text": "📅 Bugungi hisobot"}],
            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],'''
new_menu = '''            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],
            [{"text": "📅 Bugungi hisobot"}],
            [{"text": "💰 Moliya"}, {"text": "➕ Xarajat"}],
            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],'''
if new_menu not in text:
    if old_menu not in text:
        raise SystemExit('admin menu marker not found')
    text = text.replace(old_menu, new_menu, 1)

state_marker = '''    state = states.get(chat_id)

    # =========================
    # TO‘LOV CHEKI RASMI
'''
state_block = '''    state = states.get(chat_id)

    # =========================
    # ADMIN: MOLIYA XARAJATI
    # =========================
    if state and is_admin(chat_id) and state.get("action") in ("finance_expense_category", "finance_expense_amount"):
        if text == "❌ Bekor qilish":
            states.pop(chat_id, None)
            send(chat_id, "Xarajat kiritish bekor qilindi.", admin_menu())
            return

        if state.get("action") == "finance_expense_category":
            category = FINANCE_EXPENSE_CATEGORIES.get(text)
            if not category:
                send(chat_id, "Xarajat turini tugmalardan tanlang.", finance_expense_category_keyboard())
                return
            states[chat_id] = {"action": "finance_expense_amount", "category": category, "category_label": text}
            send(chat_id, f"{text} xarajat summasini yozing (₩).\\nMasalan: 12000", {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
            return

        if state.get("action") == "finance_expense_amount":
            try:
                amount = int(text.replace(",", "").replace(" ", ""))
                if amount <= 0:
                    raise ValueError
            except Exception:
                send(chat_id, "❌ Summani faqat musbat raqamda yozing. Masalan: 12000")
                return
            try:
                cloud_bridge.add_finance_expense(amount, state.get("category", "other"), state.get("category_label", ""))
            except Exception as exc:
                send(chat_id, f"❌ Xarajat serverga saqlanmadi: {exc}", admin_menu())
                return
            states.pop(chat_id, None)
            send(chat_id, f"✅ Xarajat saqlandi: ₩{amount:,}", admin_menu())
            send(chat_id, finance_report_text("month"), finance_report_keyboard())
            return

    # =========================
    # TO‘LOV CHEKI RASMI
'''
if 'ADMIN: MOLIYA XARAJATI' not in text:
    if state_marker not in text:
        raise SystemExit('state marker not found')
    text = text.replace(state_marker, state_block, 1)

command_marker = '''        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return
'''
command_block = '''        if text == "💰 Moliya":
            states.pop(chat_id, None)
            send(chat_id, finance_report_text("month"), finance_report_keyboard())
            return

        if text == "➕ Xarajat":
            states[chat_id] = {"action": "finance_expense_category"}
            send(chat_id, "🧾 Xarajat turini tanlang:", finance_expense_category_keyboard())
            return

        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return
'''
if 'if text == "💰 Moliya":' not in text:
    if command_marker not in text:
        raise SystemExit('admin report command marker not found')
    text = text.replace(command_marker, command_block, 1)

callback_marker = '''    data = callback.get("data", "")

    try:
        api(
            "answerCallbackQuery",
            {"callback_query_id": callback_id}
        )
    except Exception as e:
        print("Callback answer xatosi:", e)
'''
callback_block = callback_marker + '''

    if data.startswith("finance_"):
        if not is_admin(chat_id):
            return
        period = data.split("_", 1)[1]
        if period not in FINANCE_PERIOD_LABELS:
            period = "month"
        send(chat_id, finance_report_text(period), finance_report_keyboard())
        return
'''
if 'if data.startswith("finance_"):' not in text:
    if callback_marker not in text:
        raise SystemExit('callback marker not found')
    text = text.replace(callback_marker, callback_block, 1)

path.write_text(text, encoding='utf-8')
print('Unified finance bot patch applied')
