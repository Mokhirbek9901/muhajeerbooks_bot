from pathlib import Path

import app_image_sync  # Railway start old behavior: app image sync remains enabled.


def _replace_once(source, old, new, label):
    if old not in source:
        raise RuntimeError(f"Runtime patch topilmadi: {label}. bot.py o‘zgargan bo‘lishi mumkin.")
    return source.replace(old, new, 1)


def _replace_function(source, start_marker, end_marker, replacement, label):
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Runtime function topilmadi: {label}")
    end = source.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Runtime function oxiri topilmadi: {label}")
    return source[:start] + replacement.rstrip() + "\n\n" + source[end:]


def run_bot_patched():
    source = Path("bot.py").read_text(encoding="utf-8")

    # 1) Admin kitoblar ro‘yxatini Telegram 4096 belgi limitidan xavfsiz saqlaymiz.
    old_books = '''        if text == "📚 Kitoblar ro‘yxati":
            send(
                chat_id,
                admin_books_text(),
                admin_menu()
            )
            return
'''
    new_books = '''        if text == "📚 Kitoblar ro‘yxati":
            full_text = admin_books_text()
            chunks = []
            current_lines = []
            current_len = 0
            for line in full_text.splitlines():
                line_len = len(line) + 1
                if current_lines and current_len + line_len > 3500:
                    chunks.append("\\n".join(current_lines))
                    current_lines = [line]
                    current_len = line_len
                else:
                    current_lines.append(line)
                    current_len += line_len
            if current_lines:
                chunks.append("\\n".join(current_lines))
            if not chunks:
                chunks = ["📚 Hozircha kitob yo‘q."]
            for index, chunk in enumerate(chunks):
                send(chat_id, chunk, admin_menu() if index == len(chunks) - 1 else None)
            return
'''
    source = _replace_once(source, old_books, new_books, "admin book list")

    # 2) Telegram xarajat turlari ilova bilan aynan bir xil bo‘lsin.
    source = _replace_once(
        source,
        '    "🚚 Pochta": "postage",\n',
        '    "🚚 Pochta": "postage",\n    "📚 Yangi partiya kitoblar": "inventory_purchase",\n',
        "finance inventory category",
    )
    source = _replace_once(
        source,
        '        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],\n',
        '        [{"text": "🚚 Pochta"}, {"text": "📦 Qadoqlash"}],\n        [{"text": "📚 Yangi partiya kitoblar"}],\n',
        "finance inventory keyboard",
    )

    # 3) Moliya oynasi to‘liq server formulasi bilan ishlaydi.
    finance_function = r'''def finance_report_text(period="month"):
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

    def signed_won(value):
        value = int(value or 0)
        if value > 0:
            return f"+₩{value:,}"
        if value < 0:
            return f"−₩{abs(value):,}"
        return "₩0"

    def signed_percent(value):
        try:
            value = float(value or 0)
        except Exception:
            value = 0.0
        if value > 0:
            return f"+{value:.1f}%"
        if value < 0:
            return f"−{abs(value):.1f}%"
        return "0.0%"

    try:
        margin = float(r.get("margin_percent", 0) or 0)
    except Exception:
        margin = 0.0

    result = n("cash_result") if "cash_result" in r else n("net_profit")
    result_label = "✅ SOF FOYDA" if result > 0 else ("🔻 SOF ZARAR" if result < 0 else "➖ SOF NATIJA")
    postage_note = " (taxmin)" if r.get("postage_is_estimated") else ""

    return "\n".join([
        f"💰 MOLIYA — {FINANCE_PERIOD_LABELS[period].upper()}",
        "━━━━━━━━━━━━━━",
        f"💵 Jami tushum: ₩{n('total_revenue'):,}",
        f"📚 Hisobga kiradigan kitob savdosi: ₩{n('books_revenue'):,}",
        f"🚚 Mijoz to‘lagan pochta: ₩{n('delivery_revenue'):,} (foyda emas)",
        "",
        f"📚 Yangi partiya kitoblar: ₩{n('inventory_purchases'):,}",
        f"🏪 Do‘kon hisobidan pochta: ₩{n('store_postage_expense'):,}",
        f"🧾 Boshqa chiqimlar: ₩{n('other_expenses'):,}",
        f"💸 Jami hisobga kiradigan xarajat: ₩{n('cash_outflow_total'):,}",
        "━━━━━━━━━━━━━━",
        f"{result_label}: {signed_won(result)}",
        f"📈 Marja: {signed_percent(margin)}",
        "━━━━━━━━━━━━━━",
        f"📦 Sotilgan kitoblar tannarxi (ma’lumot uchun): ₩{n('cost_of_goods'):,}",
        f"📖 Sotilgan kitoblar savdo foydasi: ₩{n('book_profit'):,}",
        f"📮 Jami pochta{postage_note}: ₩{n('postage_expense'):,}",
        f"✅ Mijoz qoplagan pochta: ₩{n('postage_covered_by_customers'):,}",
        f"📚 Sotilgan kitob: {n('sold_books')} dona",
        f"📦 Jo‘natilgan buyurtma: {n('shipped_orders')} ta",
        "",
        "ℹ️ Sof natija = kitob savdosi − yangi partiya − do‘kon hisobidagi pochta − boshqa xarajatlar.",
        "Mijoz to‘lagan pochta puli foyda hisoblanmaydi va natijani kamaytirmaydi.",
        "4+ kitobda yetkazish bepul bo‘lsa, pochta do‘kon hisobidan chiqadi.",
    ])
'''
    source = _replace_function(
        source,
        'def finance_report_text(period="month"):',
        'def finance_expense_category_keyboard():',
        finance_function,
        "finance_report_text",
    )

    # 4) Eski "Bugungi hisobot"dagi foyda ham serverdagi ayni formuladan olinsin.
    source = _replace_once(
        source,
        '    postage=len(successful)*int(DELIVERY_FEE); net_profit=revenue-cost_of_goods-postage\n',
        '    cloud_finance = cloud_bridge.finance_report("today")\n    postage = int(float(cloud_finance.get("store_postage_expense", 0) or 0))\n    net_profit = int(float(cloud_finance.get("cash_result", cloud_finance.get("net_profit", 0)) or 0))\n',
        "daily finance totals",
    )

    # 5) Umumiy admin hisobotidagi foyda ham server bilan bir xil bo‘lsin.
    source = _replace_once(
        source,
        '    postage_expense = len(successful) * int(DELIVERY_FEE)\n    net_profit = revenue - cost_of_goods - postage_expense\n',
        '    cloud_finance = cloud_bridge.finance_report(period)\n    postage_expense = int(float(cloud_finance.get("store_postage_expense", 0) or 0))\n    net_profit = int(float(cloud_finance.get("cash_result", cloud_finance.get("net_profit", 0)) or 0))\n',
        "admin report finance totals",
    )

    namespace = {"__name__": "__main__", "__file__": "bot.py"}
    exec(compile(source, "bot.py", "exec"), namespace, namespace)


sync_source = Path("sync_wrapper.py").read_text(encoding="utf-8")
sync_target = 'runpy.run_path("bot.py", run_name="__main__")'
if sync_target not in sync_source:
    raise RuntimeError("sync_wrapper.py ichidagi bot start qatori topilmadi.")

sync_source = sync_source.replace(sync_target, "run_bot_patched()", 1)
sync_namespace = {
    "__name__": "__main__",
    "__file__": "sync_wrapper.py",
    "run_bot_patched": run_bot_patched,
}
exec(compile(sync_source, "sync_wrapper.py", "exec"), sync_namespace, sync_namespace)
