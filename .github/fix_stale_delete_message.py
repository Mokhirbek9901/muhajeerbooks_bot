from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')
old = '''        if not book:
            send(
                chat_id,
                "ℹ️ Bu eski tugma. Kitob allaqachon o‘chirilgan yoki ro‘yxat yangilangan.\\n"
                "Kitoblar ro‘yxatini qayta oching.",
                admin_menu()
            )
            return
'''
new = '''        if not book:
            # Eski Telegram inline xabari katalog emas. Kitob allaqachon o‘chirilgan
            # bo‘lsa, o‘sha eski xabarning tugmalarini ham olib tashlaymiz.
            try:
                edit_message(
                    chat_id,
                    message.get("message_id"),
                    "🗑 Bu kitob allaqachon o‘chirilgan.\\n\\n✅ Eski tugma ham tozalandi.",
                    {"inline_keyboard": []}
                )
            except Exception:
                send(
                    chat_id,
                    "ℹ️ Bu eski tugma. Kitob allaqachon o‘chirilgan yoki ro‘yxat yangilangan.",
                    admin_menu()
                )
            return
'''
if old not in s:
    if 'Eski tugma ham tozalandi' in s:
        raise SystemExit(0)
    raise SystemExit('stale delete block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
