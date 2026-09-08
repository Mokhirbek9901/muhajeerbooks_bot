from pathlib import Path
import re

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

# Patch only save_instagram_sale so Instagram sales always store the actual received amount correctly.
pat = r'(def save_instagram_sale\(state\):\n.*?)(\n# =========================\n# BUYURTMANI YAKUNLASH)'
m = re.search(pat, t, flags=re.S)
if not m:
    raise RuntimeError('save_instagram_sale block not found')
block = m.group(1)

# Ensure order fields are overwritten from the actual amount entered by admin before saving.
anchor = '    orders[order_id] = order\n    save_orders()'
replacement = '''    # Instagram savdoda statistika uchun aynan admin kiritgan real jami summa ishlatiladi.\n    # Mijoz pochta to‘lagan bo‘lsa, 4,000 won yetkazish sifatida ajratiladi;\n    # qolgan qismi kitob savdosi hisoblanadi. Admin pochta to‘lasa, jami summa kitob savdosi.\n    order["total"] = int(books_total)\n    order["delivery_fee"] = int(delivery_fee)\n    order["grand_total"] = int(grand_total)\n    order["instagram_received_total"] = int(received_total)\n    order["postage_paid_by"] = "customer" if customer_pays_postage else "admin"\n\n    orders[order_id] = order\n    save_orders()'''
if anchor not in block:
    raise RuntimeError('order save anchor not found')
block = block.replace(anchor, replacement, 1)

t = t[:m.start(1)] + block + t[m.end(1):]

# Add safe report helpers so all reports use real Instagram totals, including any Instagram
# orders saved by the new flow that contain instagram_received_total.
helper_anchor = 'def daily_admin_report_text():'
if helper_anchor not in t:
    raise RuntimeError('daily report anchor not found')
helpers = '''def _order_report_total(order):\n    if str(order.get("source", "")) == "instagram":\n        received = int(order.get("instagram_received_total", 0) or 0)\n        if received > 0:\n            return received\n    return int(order.get("grand_total", 0) or 0)\n\n\ndef _order_report_delivery(order):\n    if str(order.get("source", "")) == "instagram":\n        received = int(order.get("instagram_received_total", 0) or 0)\n        if received > 0:\n            return int(DELIVERY_FEE) if str(order.get("postage_paid_by", "")) == "customer" else 0\n    return int(order.get("delivery_fee", DELIVERY_FEE) or 0)\n\n\ndef _order_report_books(order):\n    if str(order.get("source", "")) == "instagram":\n        received = int(order.get("instagram_received_total", 0) or 0)\n        if received > 0:\n            return max(0, received - _order_report_delivery(order))\n    return int(order.get("total", 0) or 0)\n\n\n'''
if 'def _order_report_total(order):' not in t:
    t = t.replace(helper_anchor, helpers + helper_anchor, 1)

# Daily report calculations.
t = t.replace(
    'revenue=sum(int(o.get("grand_total",0) or 0) for o in successful); books_revenue=sum(int(o.get("total",0) or 0) for o in successful); delivery_revenue=sum(int(o.get("delivery_fee",DELIVERY_FEE) or 0) for o in successful);',
    'revenue=sum(_order_report_total(o) for o in successful); books_revenue=sum(_order_report_books(o) for o in successful); delivery_revenue=sum(_order_report_delivery(o) for o in successful);',
    1
)

# General report may contain same compact calculation; replace every remaining exact occurrence safely.
t = t.replace(
    'revenue=sum(int(o.get("grand_total",0) or 0) for o in selected)',
    'revenue=sum(_order_report_total(o) for o in selected)'
)
t = t.replace(
    'book_revenue=sum(int(o.get("total",0) or 0) for o in selected)',
    'book_revenue=sum(_order_report_books(o) for o in selected)'
)
t = t.replace(
    'delivery_revenue=sum(int(o.get("delivery_fee",DELIVERY_FEE) or 0) for o in selected)',
    'delivery_revenue=sum(_order_report_delivery(o) for o in selected)'
)

p.write_text(t, encoding='utf-8')
print('patched instagram statistics')
