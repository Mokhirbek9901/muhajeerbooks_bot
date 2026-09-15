from pathlib import Path


def need_replace(text, old, new, label, count=1):
    actual = text.count(old)
    if actual < count:
        raise SystemExit(f'{label}: expected at least {count}, found {actual}')
    return text.replace(old, new, count)

# Cloud helper for the global display-number map.
p = Path('cloud_bridge.py')
s = p.read_text(encoding='utf-8')
marker = "\ndef sales_list(limit=5000):\n"
insert = '''\ndef order_number_map():
    result = rpc(
        "bot_order_number_map",
        {"p_secret": SYNC_SECRET},
    )
    return result if isinstance(result, dict) else {}


def sales_list(limit=5000):
'''
s = need_replace(s, marker, insert, 'cloud order number map')
p.write_text(s, encoding='utf-8')

# Bot: show one central four-digit sequence while keeping internal Telegram IDs untouched.
p = Path('bot.py')
s = p.read_text(encoding='utf-8')
marker = "\ndef normalize_cover(text):\n"
helpers = '''
_order_display_cache = {}
_order_display_cache_at = 0.0


def refresh_display_order_numbers(force=False):
    global _order_display_cache, _order_display_cache_at
    now = time.time()
    if not force and _order_display_cache and now - _order_display_cache_at < 60:
        return _order_display_cache
    try:
        result = cloud_bridge.order_number_map()
        if isinstance(result, dict):
            clean = {}
            for key, value in result.items():
                try:
                    number = int(value)
                except Exception:
                    continue
                if number > 0:
                    clean[str(key)] = number
            _order_display_cache = clean
            _order_display_cache_at = now
    except Exception as exc:
        print("Zakas tartib raqamlari sync xatosi:", exc)
    return _order_display_cache


def display_order_number(order):
    try:
        stored = int(order.get("display_order_number") or 0)
    except Exception:
        stored = 0
    if stored > 0:
        return f"{stored:04d}"

    key = str(order.get("order_id") or "").strip()
    if key:
        mapping = refresh_display_order_numbers(False)
        number = mapping.get(key)
        if number is None:
            mapping = refresh_display_order_numbers(True)
            number = mapping.get(key)
        if number:
            return f"{int(number):04d}"
    return key


def find_order_by_display_number(text, chat_id=None):
    needle = str(text or "").strip()
    if not needle.isdigit():
        return None
    normalized = needle.zfill(4)
    refresh_display_order_numbers(False)
    for order in orders.values():
        if chat_id is not None and int(order.get("chat_id", -1)) != int(chat_id):
            continue
        if str(order.get("order_id") or "") == needle:
            return order
        if display_order_number(order) == normalized:
            return order
    return None


def normalize_cover(text):
'''
s = need_replace(s, marker, helpers, 'bot display number helpers')

s = need_replace(
    s,
    'f"🔢 Buyurtma №{order.get(\'order_id\')}"',
    'f"🔢 Buyurtma №{display_order_number(order)}"',
    'receipt number',
)
s = need_replace(
    s,
    'f"🔢 №{o.get(\'order_id\')} — {status}\\n"',
    'f"🔢 №{display_order_number(o)} — {status}\\n"',
    'customer order list',
)
s = need_replace(
    s,
    'lines.append(f"№{o.get(\'order_id\')} | {o.get(\'name\', \'Noma’lum\')} | ₩{int(o.get(\'grand_total\', 0)):,} | {ORDER_STATUS_NAMES.get(o.get(\'status\'), o.get(\'status\'))}")',
    'lines.append(f"№{display_order_number(o)} | {o.get(\'name\', \'Noma’lum\')} | ₩{int(o.get(\'grand_total\', 0)):,} | {ORDER_STATUS_NAMES.get(o.get(\'status\'), o.get(\'status\'))}")',
    'admin order list',
)
s = need_replace(
    s,
    'buttons.append([{"text": f"№{o.get(\'order_id\')} — {status_name(o.get(\'status\'))}", "callback_data": f"adminorder_{o.get(\'order_id\')}"}])',
    'buttons.append([{"text": f"№{display_order_number(o)} — {status_name(o.get(\'status\'))}", "callback_data": f"adminorder_{o.get(\'order_id\')}"}])',
    'admin order buttons',
)

# Texts that have a local order variable available.
s = s.replace('f"🛒 YANGI BUYURTMA №{order_id}\\n', 'f"🛒 YANGI BUYURTMA №{display_order_number(order)}\\n')
s = s.replace('f"📸 To‘lov cheki · Buyurtma №{order_id}"', 'f"📸 To‘lov cheki · Buyurtma №{display_order_number(order)}"')
s = s.replace('f"🔢 №{order[\'order_id\']}\\n"', 'f"🔢 №{display_order_number(order)}\\n"')
s = s.replace('f"✅ Buyurtma №{order_id} qabul qilindi.\\n', 'f"✅ Buyurtma №{display_order_number(order)} qabul qilindi.\\n')
s = s.replace('f"🚚 Buyurtma №{order_id} jo‘natildi."', 'f"🚚 Buyurtma №{display_order_number(order)} jo‘natildi."')
s = s.replace('f"❌ Zakaz №{order_id} bekor qilindi."', 'f"❌ Zakaz №{display_order_number(order)} bekor qilindi."')
s = s.replace('f"❌ Zakaz №{order_id} bekor qilindi.\\n', 'f"❌ Zakaz №{display_order_number(order)} bekor qilindi.\\n')

# New lookup accepts 0001-style number but still accepts the old internal ID as fallback.
s = s.replace(
    'send(chat_id, "🔢 Buyurtma raqamini yozing. Masalan: 1750000000000\\n❌ Bekor qilish uchun tugmani bosing.",',
    'send(chat_id, "🔢 Buyurtma raqamini yozing. Masalan: 0001\\n❌ Bekor qilish uchun tugmani bosing.",',
)
s = need_replace(
    s,
    '        order = orders.get(text)\n        states.pop(chat_id, None)\n        if not order or int(order.get("chat_id", -1)) != int(chat_id):',
    '        order = find_order_by_display_number(text, chat_id)\n        states.pop(chat_id, None)\n        if not order:',
    'lookup by display number',
)
s = need_replace(
    s,
    '        send(chat_id, f"🧾 BUYURTMA №{text}\\n\\n{status_name(order.get(\'status\'))}\\n💵 Jami: ₩{int(order.get(\'grand_total\',0)):,}", main_menu(chat_id))',
    '        send(chat_id, f"🧾 BUYURTMA №{display_order_number(order)}\\n\\n{status_name(order.get(\'status\'))}\\n💵 Jami: ₩{int(order.get(\'grand_total\',0)):,}", main_menu(chat_id))',
    'lookup response number',
)

p.write_text(s, encoding='utf-8')
print('Bot global four-digit order numbering applied.')
