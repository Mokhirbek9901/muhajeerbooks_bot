from pathlib import Path

path = Path('bot.py')
text = path.read_text(encoding='utf-8')

# 1) Instagram sale: actual received book amount must become the item revenue.
old_items = '''    items = []
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        items.append({
            "book_id": str(bid),
            "name": str(book.get("name", "Kitob")),
            "qty": int(qty),
            "unit_price": int(effective_price(book)),
            "unit_cost": int(book.get("cost_price", 0) or 0),
        })
'''
new_items = '''    # Instagram savdoda admin kiritgan haqiqiy kitob tushumi asosiy narx.
    # Katalog narxi faqat tushumni kitoblar orasida proporsional taqsimlash uchun
    # ishlatiladi. Agar biror kitob narxi 0 bo‘lsa, teng taqsimlaymiz.
    units = []
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        for _ in range(int(qty)):
            units.append(book)

    catalog_weights = [max(0, int(effective_price(book))) for book in units]
    if not units:
        raise ValueError("Kitoblar tanlanmagan.")
    if any(weight <= 0 for weight in catalog_weights):
        catalog_weights = [1 for _ in units]

    weight_total = max(1, sum(catalog_weights))
    allocated = []
    remainders = []
    used = 0
    for index, weight in enumerate(catalog_weights):
        numerator = int(books_total) * int(weight)
        amount = numerator // weight_total
        allocated.append(amount)
        remainders.append((numerator % weight_total, index))
        used += amount
    for _, index in sorted(remainders, reverse=True)[:max(0, int(books_total) - used)]:
        allocated[index] += 1

    items = []
    for book, unit_price in zip(units, allocated):
        items.append({
            "book_id": str(book.get("id")),
            "name": str(book.get("name", "Kitob")),
            "qty": 1,
            "unit_price": int(unit_price),
            "unit_cost": int(book.get("cost_price", 0) or 0),
        })
'''
if old_items not in text:
    raise SystemExit('Instagram items block not found')
text = text.replace(old_items, new_items, 1)

# 2) Statistics financial section: use the same Supabase cash report as web/app.
start_marker = '    revenue = sum(int(o.get("grand_total", 0)) for o in successful)\n'
end_marker = '    free_delivery_cost = len(free_delivery_orders) * int(DELIVERY_FEE)\n'
start = text.find(start_marker)
if start < 0:
    raise SystemExit('admin_report finance start not found')
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('admin_report finance end not found')
end += len(end_marker)
new_finance_block = '''    # Moliyaviy raqamlar web/APK bilan aynan bir xil markaziy hisobotdan olinadi.
    # Local buyurtmalar faqat TOP kitob/mijoz va status statistikasiga xizmat qiladi.
    try:
        cloud_finance = cloud_bridge.finance_report(period)
    except Exception as exc:
        print("Statistika moliya cloud xatosi:", exc)
        cloud_finance = {}

    def finance_n(key, default=0):
        try:
            return int(float(cloud_finance.get(key, default) or 0))
        except Exception:
            return int(default or 0)

    if cloud_finance:
        revenue = finance_n("total_revenue")
        books_revenue = finance_n("books_revenue")
        delivery_revenue = finance_n("delivery_revenue")
        cost_of_goods = finance_n("cost_of_goods")
        book_profit = finance_n("book_profit")
        inventory_purchases = finance_n("inventory_purchases")
        postage_expense = finance_n("postage_expense")
        store_postage_expense = finance_n("store_postage_expense")
        other_expenses = finance_n("other_expenses")
        cash_outflow_total = finance_n("cash_outflow_total")
        net_profit = finance_n("net_profit")
        missing_cost_qty = 0
    else:
        # Server bo‘lmasa eski local raqamni "sof foyda" deb ko‘rsatmaymiz.
        revenue = sum(_order_report_total(o) for o in successful)
        books_revenue = sum(_order_report_books(o) for o in successful)
        delivery_revenue = sum(_order_report_delivery(o) for o in successful)
        cost_of_goods = 0
        missing_cost_qty = 0
        for o in successful:
            order_cost, missing_qty = order_cost_summary(o)
            cost_of_goods += order_cost
            missing_cost_qty += missing_qty
        book_profit = books_revenue - cost_of_goods
        inventory_purchases = 0
        postage_expense = len(successful) * int(DELIVERY_FEE)
        store_postage_expense = max(0, postage_expense - delivery_revenue)
        other_expenses = 0
        cash_outflow_total = store_postage_expense
        net_profit = books_revenue - cash_outflow_total

    avg_order = revenue / len(successful) if successful else 0
    free_delivery_orders = [
        o for o in successful
        if _order_report_delivery(o) == 0
    ]
    free_delivery_cost = len(free_delivery_orders) * int(DELIVERY_FEE)
'''
text = text[:start] + new_finance_block + text[end:]

old_stats_lines = '''        f"💵 Sotilgan kitoblar tannarxi: ₩{cost_of_goods:,}",
        f"📮 Pochtaga sarflandi: ₩{postage_expense:,}",
        f"✅ Sof foyda: ₩{net_profit:,}",
'''
new_stats_lines = '''        f"💵 Sotilgan kitoblar tannarxi: ₩{cost_of_goods:,}",
        f"📖 Kitobdan qolgan foyda: ₩{book_profit:,}",
        f"📦 Yangi partiya kitoblar: ₩{inventory_purchases:,}",
        f"📮 Do‘kon hisobidan pochta: ₩{store_postage_expense:,}",
        f"🧾 Boshqa chiqimlar: ₩{other_expenses:,}",
        f"➖ Hisobga kiradigan jami chiqim: ₩{cash_outflow_total:,}",
        f"{'✅ Sof foyda' if net_profit >= 0 else '🔻 Sof zarar'}: {'-' if net_profit < 0 else ''}₩{abs(net_profit):,}",
'''
if old_stats_lines not in text:
    raise SystemExit('statistics display block not found')
text = text.replace(old_stats_lines, new_stats_lines, 1)

# 3) Daily report: same shared finance report; never show obsolete local net profit.
daily_start = text.find('def daily_admin_report_text():\n')
daily_end_marker = '\n\n# =========================\n# BUYURTMA HISOBI\n'
daily_end = text.find(daily_end_marker, daily_start)
if daily_start < 0 or daily_end < 0:
    raise SystemExit('daily report function not found')
new_daily = '''def daily_admin_report_text():
    try:
        r = cloud_bridge.finance_report("today")
    except Exception as exc:
        return f"❌ Bugungi moliya hisoboti serverdan olinmadi: {exc}"

    def n(key):
        try:
            return int(float(r.get(key, 0) or 0))
        except Exception:
            return 0

    net = n("net_profit")
    margin = float(r.get("margin_percent", 0) or 0)
    return "\\n".join([
        "📅 BUGUNGI HISOBOT",
        "",
        f"📦 Jo‘natilgan buyurtma: {n('shipped_orders')} ta",
        f"📚 Sotilgan kitoblar: {n('sold_books')} dona",
        "",
        f"💰 Jami tushum: ₩{n('total_revenue'):,}",
        f"📖 Hisobga kiradigan kitob savdosi: ₩{n('books_revenue'):,}",
        f"🚚 Mijozlardan yetkazish puli: ₩{n('delivery_revenue'):,}",
        f"💵 Kitob tannarxi: ₩{n('cost_of_goods'):,}",
        f"📚 Kitobdan qolgan foyda: ₩{n('book_profit'):,}",
        f"📦 Yangi partiya kitoblar: ₩{n('inventory_purchases'):,}",
        f"📮 Do‘kon hisobidan pochta: ₩{n('store_postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        "━━━━━━━━━━━━━━",
        f"{'✅ BUGUNGI SOF FOYDA' if net >= 0 else '🔻 BUGUNGI SOF ZARAR'}: {'-' if net < 0 else ''}₩{abs(net):,}",
        f"📈 Marja: {margin:.1f}%",
        "━━━━━━━━━━━━━━",
        "ℹ️ Natija = kitob savdosi − yangi partiya − do‘kon hisobidan pochta − boshqa chiqimlar.",
    ])
'''
text = text[:daily_start] + new_daily + text[daily_end:]

# 4) Finance screen text: match web/app cards and formula.
old_finance_display = '''        f"📦 Sotilgan kitoblar tannarxi: ₩{n('cost_of_goods'):,}",
        f"📖 Kitobdan foyda: ₩{n('book_profit'):,}",
        f"📮 Pochta xarajati{postage_note}: ₩{n('postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        f"➖ Jami chiqim: ₩{n('total_expenses'):,}",
        "━━━━━━━━━━━━━━",
        f"✅ SOF FOYDA: ₩{n('net_profit'):,}",
        f"📈 Sof marja: {margin:.1f}%",
'''
new_finance_display = '''        f"📦 Kitob tannarxi: ₩{n('cost_of_goods'):,}",
        f"📖 Kitobdan qolgan foyda: ₩{n('book_profit'):,}",
        f"📚 Yangi partiya kitoblar: ₩{n('inventory_purchases'):,}",
        f"📮 Do‘kon hisobidan pochta: ₩{n('store_postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        f"➖ Hisobga kiradigan jami chiqim: ₩{n('cash_outflow_total'):,}",
        "━━━━━━━━━━━━━━",
        f"{'✅ SOF FOYDA' if n('net_profit') >= 0 else '🔻 SOF ZARAR'}: {'-' if n('net_profit') < 0 else ''}₩{abs(n('net_profit')):,}",
        f"📈 Sof marja: {margin:.1f}%",
'''
if old_finance_display not in text:
    raise SystemExit('finance report display block not found')
text = text.replace(old_finance_display, new_finance_display, 1)

old_formula = '''        "ℹ️ Sof foyda = kitob + yetkazish tushumi − tannarx − pochta − boshqa chiqimlar.",
        "Kitobning kelish narxini alohida chiqimga yana qo‘shmang — tannarxda hisoblangan.",
'''
new_formula = '''        "ℹ️ Sof natija = kitob savdosi − yangi partiya kitoblar − do‘kon hisobidan pochta − boshqa chiqimlar.",
        "Mijoz to‘lagan pochta puli foyda emas; u pochta xarajatini qoplaydi.",
'''
if old_formula not in text:
    raise SystemExit('finance formula text not found')
text = text.replace(old_formula, new_formula, 1)

# 5) Telegram expense entry can also record inventory purchases.
old_categories = '''FINANCE_EXPENSE_CATEGORIES = {
    "🚚 Pochta": "postage",
    "📦 Qadoqlash": "packaging",
'''
new_categories = '''FINANCE_EXPENSE_CATEGORIES = {
    "🚚 Pochta": "postage",
    "📚 Yangi partiya kitoblar": "inventory_purchase",
    "📦 Qadoqlash": "packaging",
'''
if old_categories not in text:
    raise SystemExit('finance categories block not found')
text = text.replace(old_categories, new_categories, 1)

old_keyboard = '''def finance_expense_category_keyboard():
    return {"keyboard": [
        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],
'''
new_keyboard = '''def finance_expense_category_keyboard():
    return {"keyboard": [
        [{"text": "📚 Yangi partiya kitoblar"}],
        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],
'''
if old_keyboard not in text:
    raise SystemExit('finance keyboard block not found')
text = text.replace(old_keyboard, new_keyboard, 1)

path.write_text(text, encoding='utf-8')
print('Shared finance/statistics fix applied')
