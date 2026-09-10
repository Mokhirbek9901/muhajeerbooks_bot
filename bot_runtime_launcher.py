from pathlib import Path

import app_image_sync  # Railway start old behavior: app image sync remains enabled.


def _replace_once(source, old, new, label):
    if old not in source:
        raise RuntimeError(f"Runtime patch topilmadi: {label}. bot.py o‘zgargan bo‘lishi mumkin.")
    return source.replace(old, new, 1)


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

    # 2) Telegram xarajat turlari ilova bilan bir xil bo‘lsin.
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

    # 3) Bot moliya hisobotida ham ilovadagi ayni server natijasini +/− ko‘rsatamiz.
    old_margin = '''    try:
        margin = float(r.get("margin_percent", 0) or 0)
    except Exception:
        margin = 0.0
    postage_note = " (taxmin)" if r.get("postage_is_estimated") else ""
'''
    new_margin = '''    def signed_won(value):
        value = int(value or 0)
        if value > 0:
            return f"+₩{value:,}"
        if value < 0:
            return f"−₩{abs(value):,}"
        return "₩0"

    postage_note = " (taxmin)" if r.get("postage_is_estimated") else ""
'''
    source = _replace_once(source, old_margin, new_margin, "finance signed result helper")

    source = _replace_once(
        source,
        '        f"📦 Sotilgan kitoblar tannarxi: ₩{n(\'cost_of_goods\'):,}",\n',
        '        f"📦 Sotilgan kitoblar tannarxi: ₩{n(\'cost_of_goods\'):,}",\n        f"📚 Yangi partiya kitoblar: ₩{n(\'inventory_purchases\'):,}",\n',
        "finance inventory report line",
    )
    source = _replace_once(
        source,
        '        f"✅ SOF FOYDA: ₩{n(\'net_profit\'):,}",\n        f"📈 Sof marja: {margin:.1f}%",\n',
        '        f"{\'✅ SOF FOYDA\' if n(\'net_profit\') >= 0 else \'🔻 SOF ZARAR\'}: {signed_won(n(\'net_profit\'))}",\n        f"💸 Umumiy xarajat: ₩{n(\'cash_outflow_total\'):,}",\n',
        "finance cash result lines",
    )
    source = _replace_once(
        source,
        '        "ℹ️ Sof foyda = kitob + yetkazish tushumi − tannarx − pochta − boshqa chiqimlar.",\n        "Kitobning kelish narxini alohida chiqimga yana qo‘shmang — tannarxda hisoblangan.",\n',
        '        "ℹ️ Sof natija = jami tushum − barcha kiritilgan xarajatlar.",\n        "Yangi partiya, pochta, qadoqlash, reklama, transport va boshqa chiqimlar ham shu natijaga kiradi.",\n',
        "finance formula help",
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
