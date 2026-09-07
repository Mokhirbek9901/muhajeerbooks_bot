from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

# Customer-facing order status label.
needle = '''        "pending": "🟡 To‘lov kutilmoqda",\n        "paid": "🟢 To‘lov tasdiqlangan",\n'''
if '"accepted": "📦 Buyurtma qabul qilingan"' not in s:
    assert needle in s, 'customer status map not found'
    s = s.replace(
        needle,
        '''        "pending": "🟡 To‘lov kutilmoqda",\n        "accepted": "📦 Buyurtma qabul qilingan",\n        "paid": "🟢 To‘lov tasdiqlangan",\n''',
        1,
    )

# Admin status map.
needle = '''    "pending": "🟡 Kutilmoqda", "paid": "🟢 To‘langan",\n'''
if '"accepted": "📦 Qabul qilingan"' not in s:
    assert needle in s, 'admin status map not found'
    s = s.replace(
        needle,
        '''    "pending": "🟡 Kutilmoqda", "accepted": "📦 Qabul qilingan", "paid": "🟢 To‘langan",\n''',
        1,
    )

# Add accepted filter in admin orders.
needle = '''        [{"text": f"🟡 Kutilmoqda ({counts['pending']})", "callback_data": "adminorders_pending"}],\n        [{"text": f"🚚 Jo‘natilgan ({counts['shipped']})", "callback_data": "adminorders_shipped"}],\n'''
if 'adminorders_accepted' not in s:
    assert needle in s, 'admin order filter block not found'
    s = s.replace(
        needle,
        '''        [{"text": f"🟡 Kutilmoqda ({counts['pending']})", "callback_data": "adminorders_pending"}],\n        [{"text": f"📦 Qabul qilingan ({counts['accepted']})", "callback_data": "adminorders_accepted"}],\n        [{"text": f"🚚 Jo‘natilgan ({counts['shipped']})", "callback_data": "adminorders_shipped"}],\n''',
        1,
    )

# Accepted app order can be paid or cancelled from Telegram too.
start = s.index('def admin_order_status_keyboard(order_id, status):')
end = s.index('# =========================\n# BUYURTMANI YAKUNLASH', start)
block = s[start:end]
if 'elif status == "accepted":' not in block:
    needle = '''    elif status == "paid":\n        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])\n'''
    assert needle in block, 'paid keyboard branch not found'
    block = block.replace(
        needle,
        '''    elif status == "accepted":\n        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])\n        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])\n    elif status == "paid":\n        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])\n''',
        1,
    )
s = s[:start] + block + s[end:]

# paid_ must accept both pending and app-side accepted; cloud core prevents double stock subtraction.
start = s.index('    if data.startswith("paid_"):')
end = s.index('    # =========================\n    # ADMIN: ORDER CANCEL', start)
block = s[start:end]
needle = '''        if order.get("status") != "pending":\n'''
if 'not in ("pending", "accepted")' not in block:
    assert needle in block, 'paid guard not found'
    block = block.replace(needle, '''        if order.get("status") not in ("pending", "accepted"):\n''', 1)
s = s[:start] + block + s[end:]

# Cancel must also work after app admin has accepted/reserved stock; cloud restores it atomically.
start = s.index('    if data.startswith("cancelorder_"):')
end = s.index('# =========================\n# MAIN', start)
block = s[start:end]
needle = '''        if order.get("status") != "pending":\n'''
if 'not in ("pending", "accepted")' not in block:
    assert needle in block, 'cancel guard not found'
    block = block.replace(needle, '''        if order.get("status") not in ("pending", "accepted"):\n''', 1)
s = s[:start] + block + s[end:]

p.write_text(s, encoding='utf-8')
