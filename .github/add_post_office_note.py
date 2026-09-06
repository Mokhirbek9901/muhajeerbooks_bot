from pathlib import Path

p = Path('bot.py')
t = p.read_text(encoding='utf-8')
old = '''        send(
            order["chat_id"],
            "✅ BUYURTMANGIZ QABUL QILINDI!\\n\\n" + order_receipt_text(order),
            main_menu(order["chat_id"])
        )
'''
new = '''        send(
            order["chat_id"],
            "✅ BUYURTMANGIZ QABUL QILINDI!\\n\\n" + order_receipt_text(order) +
            "\\n\\n📦 Kitoblaringiz pochtaga topshirilganda sizga alohida xabar yuboriladi.",
            main_menu(order["chat_id"])
        )
'''
assert t.count(old) == 1, t.count(old)
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
