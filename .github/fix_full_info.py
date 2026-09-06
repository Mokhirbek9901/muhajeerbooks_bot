from pathlib import Path

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

old = '''    if data == "saved_new_address":
        state = states.get(chat_id)
        if not state or state.get("action") != "confirm_saved_info":
            return
        state["action"] = "order_saved_address"
        send(
            chat_id,
            "📍 Yangi manzil va xona raqamini to‘liq yozing.\\n\\n"
            "Masalan: 경상북도 경산시 계양로 37길 7-3, 808호"
        )
        return
'''
new = '''    if data == "saved_new_address":
        state = states.get(chat_id)
        if not state or state.get("action") != "confirm_saved_info":
            return
        state.pop("name", None)
        state.pop("phone", None)
        state.pop("address", None)
        state["action"] = "order_name"
        send(chat_id, "📝 Yangi buyurtma uchun ismingizni yozing:")
        return
'''

if t.count(old) != 1:
    raise SystemExit(f'Expected old block once, found {t.count(old)}')

t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
