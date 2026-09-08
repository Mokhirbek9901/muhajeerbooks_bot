from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

old1 = 'books_total = received_total - delivery_fee if customer_pays_postage else received_total'
new1 = 'books_total = max(0, received_total - int(DELIVERY_FEE))'
if old1 not in s:
    raise SystemExit('save_instagram_sale books_total pattern not found')
s = s.replace(old1, new1, 1)

old2 = 'books_amount = received - fee if customer_pays else received'
new2 = 'books_amount = max(0, received - int(DELIVERY_FEE))'
if old2 not in s:
    raise SystemExit('instagram preview books_amount pattern not found')
s = s.replace(old2, new2, 1)

p.write_text(s, encoding='utf-8')
