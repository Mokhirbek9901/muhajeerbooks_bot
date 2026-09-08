from pathlib import Path

# App-created order notifications in Telegram are informational only.
p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')
old = '''    kb = {\n        "inline_keyboard": [\n            [\n                {\n                    "text": "✅ Buyurtmani qabul qilish",\n                    "callback_data": f"accept_{order.get('order_id')}",\n                }\n            ],\n            [\n                {\n                    "text": "📦 Buyurtmani ochish",\n                    "callback_data": f"adminorder_{order.get('order_id')}",\n                }\n            ],\n        ]\n    }\n    _telegram_send(ADMIN_ID, text, kb)'''
new = '''    text += "\\n\\n🔒 Bu buyurtma faqat ilova admin panelidan boshqariladi."\n    _telegram_send(ADMIN_ID, text)'''
if old in s:
    s = s.replace(old, new, 1)
elif 'faqat ilova admin panelidan boshqariladi' not in s:
    raise SystemExit('app notification keyboard block not found')
p.write_text(s, encoding='utf-8')

# Bot admin menus must never offer controls for app-created orders.
p = Path('bot.py')
s = p.read_text(encoding='utf-8')
needle = '''def admin_order_status_keyboard(order_id, status):\n    buttons=[]'''
replacement = '''def admin_order_status_keyboard(order_id, status):\n    order = orders.get(str(order_id)) or {}\n    if str(order.get("source") or "telegram") == "app":\n        return []\n    buttons=[]'''
if needle in s:
    s = s.replace(needle, replacement, 1)
elif 'if str(order.get("source") or "telegram") == "app":\n        return []' not in s:
    raise SystemExit('admin_order_status_keyboard not found')

# Show a clear origin label when an app order is opened from the bot history.
detail_old = '''def admin_order_detail(order):\n    return order_receipt_text(order)'''
detail_new = '''def admin_order_detail(order):\n    text = order_receipt_text(order)\n    if str(order.get("source") or "telegram") == "app":\n        return "📱 ILOVADAN ZAKAS — boshqarish faqat ilovada\\n\\n" + text\n    return text'''
if detail_old in s:
    s = s.replace(detail_old, detail_new, 1)

p.write_text(s, encoding='utf-8')
