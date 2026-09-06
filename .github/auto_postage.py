from pathlib import Path
p=Path('bot.py')
t=p.read_text(encoding='utf-8')

def r(old,new,name):
    global t
    c=t.count(old)
    if c!=1: raise RuntimeError(f'{name}: {c}')
    t=t.replace(old,new,1)

r('''            [{"text": "📅 Bugungi hisobot"}, {"text": "🚚 Pochta xarajati"}],''','''            [{"text": "📅 Bugungi hisobot"}],''','menu')

r('''    load_users()\n    load_expenses()\n    now = datetime.now()''','''    load_users()\n    now = datetime.now()''','report-load')

r('''    postage_expense = postage_expense_for_period(period)\n    net_profit = revenue - cost_of_goods - postage_expense''','''    # Har bir yakunlangan buyurtma uchun real pochta xarajati ₩4,000 deb hisoblanadi.\n    # Mijoz yetkazish pulini to‘lasa ham, 4+ kitobda bepul bo‘lsa ham pochta xarajati mavjud.\n    postage_expense = len(successful) * int(DELIVERY_FEE)\n    net_profit = revenue - cost_of_goods - postage_expense''','report-postage')

r('''    postage=postage_expense_for_period("today"); net_profit=revenue-cost_of_goods-postage''','''    postage=len(successful)*int(DELIVERY_FEE); net_profit=revenue-cost_of_goods-postage''','daily-postage')

old='''        if text == "🚚 Pochta xarajati":\n            states[chat_id]={"action":"postage_expense"}; send(chat_id,"🚚 Bugun pochtaga sarflagan summani yozing (₩).\\nMasalan: 12000\\n\\nBir kunda bir necha marta kiritsangiz, hammasi qo‘shib hisoblanadi."); return\n\n'''
if old in t:
    t=t.replace(old,'',1)

old='''            if action == "postage_expense":\n                try:\n                    amount=int(text.replace(",","").replace(" ",""))\n                    if amount<=0: raise ValueError\n                except ValueError: send(chat_id,"❌ Summa musbat son bo‘lsin. Masalan: 12000"); return\n                add_postage_expense(amount); states.pop(chat_id,None); send(chat_id,f"✅ Bugungi pochta xarajatiga ₩{amount:,} qo‘shildi.\\n\\n{daily_admin_report_text()}",admin_menu()); return\n\n'''
if old in t:
    t=t.replace(old,'',1)

p.write_text(t,encoding='utf-8')
