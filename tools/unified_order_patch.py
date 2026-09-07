from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

# 1) Accepted statusni bot UI tanisin.
if '"accepted": "📦 Qabul qilingan"' not in s:
    old = '''ORDER_STATUS_NAMES = {
    "pending": "🟡 Kutilmoqda", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "✅ Yetkazilgan",
    "cancelled": "❌ Bekor qilingan", "stock_problem": "⚠️ Ombor muammosi"
}'''
    new = '''ORDER_STATUS_NAMES = {
    "pending": "🟡 Kutilmoqda", "accepted": "📦 Qabul qilingan", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "✅ Yetkazilgan",
    "cancelled": "❌ Bekor qilingan", "stock_problem": "⚠️ Ombor muammosi"
}'''
    assert old in s, 'ORDER_STATUS_NAMES not found'
    s = s.replace(old, new, 1)

# Mijoz buyurtmalar tarixida ham accepted ko‘rinsin.
user_map_old = '''        "pending": "🟡 To‘lov kutilmoqda",
        "paid": "🟢 To‘lov tasdiqlangan",'''
user_map_new = '''        "pending": "🟡 To‘lov kutilmoqda",
        "accepted": "📦 Buyurtma qabul qilingan",
        "paid": "🟢 To‘lov tasdiqlangan",'''
if user_map_new not in s and user_map_old in s:
    s = s.replace(user_map_old, user_map_new, 1)

# 2) Accepted app orderda To‘lov qilindi tugmasi chiqsin.
old_keyboard = '''def admin_order_status_keyboard(order_id, status):
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
new_keyboard = '''def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "accepted":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "paid":
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    elif status == "shipped":
        buttons.append([{ "text":"✅ Yetkazildi", "callback_data":f"deliver_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}
'''
segment = s[s.index('def admin_order_status_keyboard'):s.index('# =========================\n# BUYURTMANI YAKUNLASH')]
if 'elif status == "accepted":' not in segment:
    assert old_keyboard in s, 'admin_order_status_keyboard not found'
    s = s.replace(old_keyboard, new_keyboard, 1)

# 3) App adminida accepted bo‘lgan buyurtmani Telegram admin paid qila olsin.
# Cloud core stock_reserved ni tekshiradi, shuning uchun ombor ikkinchi marta kamaymaydi.
old_guard = '''        if order.get("status") != "pending":
            send(chat_id, "⚠️ Bu zakaz allaqachon qayta ishlangan.")
            return
        try:
            _cloud_set_order_status(order, "paid")
'''
new_guard = '''        if order.get("status") not in ("pending", "accepted"):
            send(chat_id, "⚠️ Bu zakaz allaqachon qayta ishlangan.")
            return
        try:
            _cloud_set_order_status(order, "paid")
'''
if 'order.get("status") not in ("pending", "accepted")' not in s:
    assert old_guard in s, 'paid status guard not found'
    s = s.replace(old_guard, new_guard, 1)

p.write_text(s, encoding='utf-8')
