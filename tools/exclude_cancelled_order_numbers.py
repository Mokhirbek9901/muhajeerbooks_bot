from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

old = '''def display_order_number(order):
    try:
        stored = int(order.get("display_order_number") or 0)
'''
new = '''def display_order_number(order):
    if str(order.get("status") or "").strip() == "cancelled":
        return ""
    try:
        stored = int(order.get("display_order_number") or 0)
'''
assert old in s
s = s.replace(old, new, 1)

old = '''    if not force and _order_display_cache and now - _order_display_cache_at < 60:
'''
new = '''    if not force and _order_display_cache and now - _order_display_cache_at < 10:
'''
assert old in s
s = s.replace(old, new, 1)

old = '''    if isinstance(result, dict):
        if result.get("id"):
            order["cloud_order_id"] = str(result["id"])
        _apply_cloud_stocks(result.get("stocks"))
    return result
'''
new = '''    if isinstance(result, dict):
        if result.get("id"):
            order["cloud_order_id"] = str(result["id"])
        _apply_cloud_stocks(result.get("stocks"))
    if status == "cancelled":
        try:
            refresh_display_order_numbers(force=True)
        except Exception:
            pass
    return result
'''
assert old in s
s = s.replace(old, new, 1)

old = '''        lines.append(
            f"🔢 №{display_order_number(o)} — {status}\\n"
            f"💵 ₩{int(o.get('grand_total', 0)):,}"
        )
'''
new = '''        number = display_order_number(o)
        number_prefix = f"🔢 №{number} — " if number else ""
        lines.append(
            f"{number_prefix}{status}\\n"
            f"💵 ₩{int(o.get('grand_total', 0)):,}"
        )
'''
assert old in s
s = s.replace(old, new, 1)

old = '''        send(chat_id, f"❌ Zakaz №{display_order_number(order)} bekor qilindi.", admin_menu())
'''
new = '''        send(chat_id, "❌ Zakaz bekor qilindi.", admin_menu())
'''
assert old in s
s = s.replace(old, new, 1)

old = '''                f"❌ Zakaz №{display_order_number(order)} bekor qilindi.\\n\\nAgar xatolik bo‘lsa, admin bilan bog‘laning.",
'''
new = '''                "❌ Zakaz bekor qilindi.\\n\\nAgar xatolik bo‘lsa, admin bilan bog‘laning.",
'''
assert old in s
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
