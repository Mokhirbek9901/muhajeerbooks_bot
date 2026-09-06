from pathlib import Path
p=Path('bot.py'); t=p.read_text(encoding='utf-8')
def r(a,b,n):
 global t
 c=t.count(a)
 if c!=1: raise RuntimeError(f'{n}: {c}')
 t=t.replace(a,b,1)

r('RESTOCK_FILE = os.path.join(DATA_DIR, "restock.json")\nLOW_STOCK_LIMIT = 2','RESTOCK_FILE = os.path.join(DATA_DIR, "restock.json")\nEXPENSES_FILE = os.path.join(DATA_DIR, "expenses.json")\nLOW_STOCK_LIMIT = 2','const')
r('ratings = {}\nrestock_subscribers = {}','ratings = {}\nrestock_subscribers = {}\nexpenses = {}','global')
r('    load_ratings()\n    load_restock()\n    return json.dumps({','    load_ratings()\n    load_restock()\n    load_expenses()\n    return json.dumps({','backup-load')
r('        "ratings": ratings,\n        "restock_subscribers": restock_subscribers\n    }, ensure_ascii=False, indent=2)','        "ratings": ratings,\n        "restock_subscribers": restock_subscribers,\n        "expenses": expenses\n    }, ensure_ascii=False, indent=2)','backup-field')
r('    global books, orders, users, favorites, ratings, restock_subscribers','    global books, orders, users, favorites, ratings, restock_subscribers, expenses','restore-global')
r('    restored = {\n        "orders": data.get("orders", {}),','    load_expenses()\n    restored = {\n        "orders": data.get("orders", {}),','restore-load')
r('        "ratings": data.get("ratings", {}),\n        "restock_subscribers": data.get("restock_subscribers", {})\n    }','        "ratings": data.get("ratings", {}),\n        "restock_subscribers": data.get("restock_subscribers", {}),\n        "expenses": data.get("expenses", expenses)\n    }','restore-field')
r('        RATINGS_FILE: restored["ratings"],\n        RESTOCK_FILE: restored["restock_subscribers"]\n    }','        RATINGS_FILE: restored["ratings"],\n        RESTOCK_FILE: restored["restock_subscribers"],\n        EXPENSES_FILE: restored["expenses"]\n    }','restore-payload')
r('    load_ratings()\n    load_restock()\n\n    # Backup tiklangandan keyin','    load_ratings()\n    load_restock()\n    load_expenses()\n\n    # Backup tiklangandan keyin','restore-reload')
r('            "old_price": 0,\n            "photo_id": "",','            "old_price": 0,\n            "cost_price": 0,\n            "photo_id": "",','assasin-cost')
r('            "old_price": 0,\n            "photo_id": "",\n            "cover": "Ko‘rsatilmagan",','            "old_price": 0,\n            "cost_price": 0,\n            "photo_id": "",\n            "cover": "Ko‘rsatilmagan",','default-cost')

A='\n\n# =========================\n# YORDAMCHI\n# =========================\n'
H='''

def save_expenses():
    tmp_file = EXPENSES_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(expenses, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp_file, EXPENSES_FILE)

def load_expenses():
    global expenses
    try:
        with open(EXPENSES_FILE, "r", encoding="utf-8") as f: loaded=json.load(f)
        expenses = loaded if isinstance(loaded, dict) else {}
    except Exception:
        expenses={}
        if not os.path.exists(EXPENSES_FILE): save_expenses()

def add_postage_expense(amount):
    load_expenses(); key=datetime.now().date().isoformat(); items=expenses.setdefault(key, [])
    if not isinstance(items, list): items=[]; expenses[key]=items
    items.append({"amount":int(amount),"created_at":datetime.now().isoformat(timespec="seconds")}); save_expenses()

def postage_expense_for_period(period="all"):
    load_expenses(); now=datetime.now(); total=0
    for date_key, items in expenses.items():
        try: day=datetime.fromisoformat(str(date_key)).date()
        except Exception: continue
        include = period=="all" or (period=="today" and day==now.date()) or (period=="week" and day >= (now-timedelta(days=7)).date()) or (period=="month" and day.year==now.year and day.month==now.month)
        if include and isinstance(items,list):
            for item in items:
                try: total += int(item.get("amount",0) if isinstance(item,dict) else item)
                except Exception: pass
    return total
'''
if t.count(A)!=1: raise RuntimeError('helper-anchor')
t=t.replace(A,H+A,1)

r('''            [{"text": "📦 Ombor"}, {"text": "🗑 Kitob o‘chirish"}],
            [discount_button],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],''','''            [{"text": "📦 Ombor"}, {"text": "🗑 Kitob o‘chirish"}],
            [{"text": "⚠️ Kam qolgan"}, {"text": "⚡ Tezkor qoldiq"}],
            [discount_button],
            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],
            [{"text": "📅 Bugungi hisobot"}, {"text": "🚚 Pochta xarajati"}],''','menu')
r('            [{"text": "💰 Narxini o‘zgartirish", "callback_data": f"eprice_{book_id}"}],\n            [{"text": "📦 Qoldig‘ini o‘zgartirish", "callback_data": f"estock_{book_id}"}],','            [{"text": "💰 Narxini o‘zgartirish", "callback_data": f"eprice_{book_id}"}],\n            [{"text": "💵 Tannarxni o‘zgartirish", "callback_data": f"ecost_{book_id}"}],\n            [{"text": "📦 Qoldig‘ini o‘zgartirish", "callback_data": f"estock_{book_id}"}],','cost-button')

A='\n\n# =========================\n# BUYURTMA HISOBI\n# =========================\n'
H='''

def low_stock_admin_text():
    refresh_books(); low=sorted([b for b in books if 0<int(b.get("stock",0))<=LOW_STOCK_LIMIT],key=lambda b:int(b.get("stock",0))); empty=sorted([b for b in books if int(b.get("stock",0))<=0],key=lambda b:str(b.get("name","")).casefold())
    lines=["⚠️ KAM QOLGAN KITOBLAR",""] + ([f"• {b['name']} — {int(b.get('stock',0))} ta" for b in low] or ["Kam qolgan kitob yo‘q."]) + ["","❌ TUGAGAN KITOBLAR",""] + ([f"• {b['name']} — 0 ta" for b in empty] or ["Tugagan kitob yo‘q."])
    return "\\n".join(lines)

def low_stock_admin_keyboard():
    refresh_books(); items=sorted([b for b in books if int(b.get("stock",0))<=LOW_STOCK_LIMIT],key=lambda b:(int(b.get("stock",0)),str(b.get("name","")).casefold()))
    buttons=[[{"text":f"📦 {b['name']} — {int(b.get('stock',0))} ta","callback_data":f"qstock_book_{b['id']}"}] for b in items[:40]]; buttons.append([{"text":"⬅️ Admin panel","callback_data":"admin"}]); return {"inline_keyboard":buttons}

def quick_stock_list_keyboard():
    refresh_books(); items=sorted(books,key=lambda b:str(b.get("name","")).casefold()); buttons=[[{"text":f"📦 {b['name']} — {int(b.get('stock',0))} ta","callback_data":f"qstock_book_{b['id']}"}] for b in items[:80]]; buttons.append([{"text":"⬅️ Admin panel","callback_data":"admin"}]); return {"inline_keyboard":buttons}

def quick_stock_adjust_keyboard(book_id):
    return {"inline_keyboard":[[{"text":"➖5","callback_data":f"qstock_adj_{book_id}_-5"},{"text":"➖1","callback_data":f"qstock_adj_{book_id}_-1"}],[{"text":"➕1","callback_data":f"qstock_adj_{book_id}_1"},{"text":"➕5","callback_data":f"qstock_adj_{book_id}_5"}],[{"text":"✏️ Aniq son yozish","callback_data":f"qstock_set_{book_id}"}],[{"text":"⬅️ Kitoblar","callback_data":"qstock_list"}]]}

def order_cost_summary(order):
    total_cost=0; missing_qty=0; items=order.get("items")
    if isinstance(items,list) and items:
        for item in items:
            qty=int(item.get("qty",0) or 0); unit_cost=item.get("unit_cost")
            if unit_cost is None:
                b=find_book(item.get("book_id")); unit_cost=int(b.get("cost_price",0) or 0) if b else 0
            unit_cost=int(unit_cost or 0); total_cost += unit_cost*qty; missing_qty += qty if unit_cost<=0 else 0
        return total_cost,missing_qty
    for bid,qty in order.get("cart",{}).items():
        qty=int(qty); b=find_book(bid); unit_cost=int(b.get("cost_price",0) or 0) if b else 0; total_cost += unit_cost*qty; missing_qty += qty if unit_cost<=0 else 0
    return total_cost,missing_qty

def daily_admin_report_text():
    load_orders(); load_users(); now=datetime.now(); successful=[]
    for o in orders.values():
        if int(o.get("order_id",0) or 0)<STATS_RESET_ORDER_ID: continue
        try: dt=datetime.fromisoformat(o.get("created_at",""))
        except Exception: continue
        if dt.date()==now.date() and o.get("status") in ("paid","shipped","delivered"): successful.append(o)
    revenue=sum(int(o.get("grand_total",0) or 0) for o in successful); books_revenue=sum(int(o.get("total",0) or 0) for o in successful); delivery_revenue=sum(int(o.get("delivery_fee",DELIVERY_FEE) or 0) for o in successful); sold_qty=sum(sum(int(q) for q in o.get("cart",{}).values()) for o in successful)
    cost_of_goods=0; missing_cost_qty=0
    for o in successful:
        c,m=order_cost_summary(o); cost_of_goods+=c; missing_cost_qty+=m
    postage=postage_expense_for_period("today"); net_profit=revenue-cost_of_goods-postage
    lines=["📅 BUGUNGI HISOBOT","",f"📦 Buyurtmalar: {len(successful)} ta",f"📚 Sotilgan kitoblar: {sold_qty} dona","",f"💰 Jami tushum: ₩{revenue:,}",f"📖 Kitob savdosi: ₩{books_revenue:,}",f"🚚 Mijozlardan yetkazish puli: ₩{delivery_revenue:,}","",f"💵 Sotilgan kitoblar tannarxi: ₩{cost_of_goods:,}",f"📮 Pochtaga sarflandi: ₩{postage:,}","━━━━━━━━━━━━━━",f"✅ BUGUNGI SOF FOYDA: ₩{net_profit:,}","━━━━━━━━━━━━━━"]
    if missing_cost_qty: lines.append(f"⚠️ {missing_cost_qty} dona sotilgan kitobda tannarx 0. Sof foyda aniq bo‘lishi uchun tannarxini kiriting.")
    return "\\n".join(lines)
'''
if t.count(A)!=1: raise RuntimeError('admin-helper-anchor')
t=t.replace(A,H+A,1)

r('def admin_report_text(period="all"):\n    load_users()\n    now = datetime.now()','def admin_report_text(period="all"):\n    load_users()\n    load_expenses()\n    now = datetime.now()','report-load')
r('''    delivery_revenue = sum(int(o.get("delivery_fee", DELIVERY_FEE)) for o in successful)
    avg_order = revenue / len(successful) if successful else 0''','''    delivery_revenue = sum(int(o.get("delivery_fee", DELIVERY_FEE)) for o in successful)
    cost_of_goods = 0
    missing_cost_qty = 0
    for o in successful:
        order_cost, missing_qty = order_cost_summary(o); cost_of_goods += order_cost; missing_cost_qty += missing_qty
    postage_expense = postage_expense_for_period(period)
    net_profit = revenue - cost_of_goods - postage_expense
    avg_order = revenue / len(successful) if successful else 0''','report-calc')
r('''        f"🚚 Yetkazib berish: ₩{delivery_revenue:,}",
        f"📈 O‘rtacha buyurtma: ₩{avg_order:,.0f}",''','''        f"🚚 Yetkazib berish: ₩{delivery_revenue:,}",
        f"💵 Sotilgan kitoblar tannarxi: ₩{cost_of_goods:,}",
        f"📮 Pochtaga sarflandi: ₩{postage_expense:,}",
        f"✅ Sof foyda: ₩{net_profit:,}",
        f"📈 O‘rtacha buyurtma: ₩{avg_order:,.0f}",''','report-lines')
r('''    if top:
        for i, (bid, qty) in enumerate(top, 1):''','''    if missing_cost_qty:
        lines.insert(lines.index("🏆 TOP 10 KITOB:"), f"⚠️ Tannarxi kiritilmagan sotuv: {missing_cost_qty} dona")

    if top:
        for i, (bid, qty) in enumerate(top, 1):''','report-warning')
old='''                    "qty": int(qty),
                    "unit_price": int(effective_price(book))
                })'''; new='''                    "qty": int(qty),
                    "unit_price": int(effective_price(book)),
                    "unit_cost": int(book.get("cost_price", 0) or 0)
                })'''
if t.count(old)<2: raise RuntimeError('order-cost-snapshot')
t=t.replace(old,new)

r('''        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return

        if text == "📦 Buyurtmalar":''','''        if text == "📊 Hisobot":
            states.pop(chat_id, None)
            send(chat_id, admin_report_text(), admin_report_keyboard())
            return

        if text == "📅 Bugungi hisobot":
            states.pop(chat_id, None); send(chat_id, daily_admin_report_text(), admin_menu()); return

        if text == "🚚 Pochta xarajati":
            states[chat_id] = {"action":"postage_expense"}; send(chat_id,"📮 Bugun pochtaga sarflagan summani yozing (₩).\\nMasalan: 12000\\n\\nBir kunda bir necha marta kiritsangiz, hammasi qo‘shib hisoblanadi."); return

        if text == "📦 Buyurtmalar":''','daily-command')
r('''        if text == "📦 Ombor":
            lines = ["📦 Ombor qoldig‘i:"]''','''        if text == "⚠️ Kam qolgan":
            states.pop(chat_id,None); send(chat_id,low_stock_admin_text(),low_stock_admin_keyboard()); return

        if text == "⚡ Tezkor qoldiq":
            states.pop(chat_id,None); send(chat_id,"⚡ Qoldig‘ini tez o‘zgartirish uchun kitobni tanlang:",quick_stock_list_keyboard()); return

        if text == "📦 Ombor":
            lines = ["📦 Ombor qoldig‘i:"]''','stock-command')
r('''            if action == "global_discount":
                try:''','''            if action == "postage_expense":
                try:
                    amount=int(text.replace(",","").replace(" ",""))
                    if amount<=0: raise ValueError
                except ValueError: send(chat_id,"❌ Summa musbat son bo‘lsin. Masalan: 12000"); return
                add_postage_expense(amount); states.pop(chat_id,None); send(chat_id,f"✅ Bugungi pochta xarajatiga ₩{amount:,} qo‘shildi.\\n\\n{daily_admin_report_text()}",admin_menu()); return

            if action == "quick_stock_set":
                try:
                    value=int(text.replace(",","").replace(" ",""))
                    if value<0: raise ValueError
                except ValueError: send(chat_id,"❌ Qoldiq 0 yoki undan katta son bo‘lsin."); return
                refresh_books(); book=next((b for b in books if int(b.get("id",-1))==int(state.get("book_id",-1))),None)
                if not book: states.pop(chat_id,None); send(chat_id,"❌ Kitob topilmadi.",admin_menu()); return
                old_stock=int(book.get("stock",0)); book["stock"]=value; save_books()
                if old_stock<=0<value: notify_restock(book)
                states.pop(chat_id,None); send(chat_id,f"✅ {book['name']} — {value} ta",quick_stock_adjust_keyboard(book["id"])); return

            if action == "global_discount":
                try:''','states')

r('''                state["price"] = price
                state["action"] = "add_stock"

                send(
                    chat_id,
                    "📦 Endi qoldiq sonini yozing.\\nMasalan: 10"
                )
                return

            if action == "add_stock":''','''                state["price"] = price
                state["action"] = "add_cost_price"
                send(chat_id,"💵 Endi kitob tannarxini yozing (₩).\\nMasalan: 10000\\nTannarx hali ma’lum bo‘lmasa: 0")
                return

            if action == "add_cost_price":
                try:
                    cost_price=int(text.replace(",","").replace(" ",""))
                    if cost_price<0: raise ValueError
                except ValueError: send(chat_id,"❌ Tannarx 0 yoki undan katta son bo‘lsin."); return
                state["cost_price"]=cost_price; state["action"]="add_stock"; send(chat_id,"📦 Endi qoldiq sonini yozing.\\nMasalan: 10"); return

            if action == "add_stock":''','add-cost')
r('''                new_book = {"id": new_id, "name": state["name"], "price": state["price"], "stock": state["stock"],
                            "category": state.get("category", "Boshqalar"),''','''                new_book = {"id": new_id, "name": state["name"], "price": state["price"], "cost_price": state.get("cost_price", 0), "stock": state["stock"],
                            "category": state.get("category", "Boshqalar"),''','new-book-cost')
r('            if action in ("change_old_price", "change_category", "change_cover", "change_author", "change_description", "change_photo"):','            if action in ("change_old_price", "change_cost_price", "change_category", "change_cover", "change_author", "change_description", "change_photo"):','cost-group')
r('''                    book["old_price"] = value
                elif action == "change_category":''','''                    book["old_price"] = value
                elif action == "change_cost_price":
                    try:
                        value=int(text.replace(",","").replace(" ",""))
                        if value<0: raise ValueError
                    except ValueError: send(chat_id,"❌ Tannarx 0 yoki undan katta son bo‘lsin."); return
                    book["cost_price"]=value
                elif action == "change_category":''','cost-branch')
r('''        send(
            chat_id,
            "💰 Yangi narxni yozing (₩).\\nMasalan: 35000"
        )
        return

    # =========================
    # STOCK
    # =========================''','''        send(
            chat_id,
            "💰 Yangi narxni yozing (₩).\\nMasalan: 35000"
        )
        return

    if data.startswith("ecost_"):
        if not is_admin(chat_id): return
        book_id=int(data.split("_",1)[1]); states[chat_id]={"action":"change_cost_price","book_id":book_id}; book=find_book(book_id); current=int(book.get("cost_price",0) or 0) if book else 0; send(chat_id,f"💵 Yangi tannarxni yozing (₩).\\nHozirgi: ₩{current:,}\\nTannarx ma’lum bo‘lmasa: 0"); return

    # =========================
    # STOCK
    # =========================''','ecost-cb')
r('''    if data.startswith("report_"):
        if not is_admin(chat_id): return''','''    if data == "qstock_list":
        if not is_admin(chat_id): return
        send(chat_id,"⚡ Qoldig‘ini tez o‘zgartirish uchun kitobni tanlang:",quick_stock_list_keyboard()); return
    if data.startswith("qstock_book_"):
        if not is_admin(chat_id): return
        try: book_id=int(data.rsplit("_",1)[1])
        except Exception: return
        book=find_book(book_id)
        if not book: send(chat_id,"❌ Kitob topilmadi."); return
        send(chat_id,f"⚡ {book['name']}\\n📦 Hozir: {int(book.get('stock',0))} ta",quick_stock_adjust_keyboard(book_id)); return
    if data.startswith("qstock_adj_"):
        if not is_admin(chat_id): return
        try: parts=data.split("_"); book_id=int(parts[2]); delta=int(parts[3])
        except Exception: return
        refresh_books(); book=next((b for b in books if int(b.get("id",-1))==book_id),None)
        if not book: send(chat_id,"❌ Kitob topilmadi."); return
        old_stock=int(book.get("stock",0)); new_stock=max(0,old_stock+delta); book["stock"]=new_stock; save_books()
        if old_stock<=0<new_stock: notify_restock(book)
        send(chat_id,f"✅ {book['name']} — {new_stock} ta",quick_stock_adjust_keyboard(book_id)); return
    if data.startswith("qstock_set_"):
        if not is_admin(chat_id): return
        try: book_id=int(data.rsplit("_",1)[1])
        except Exception: return
        book=find_book(book_id)
        if not book: return
        states[chat_id]={"action":"quick_stock_set","book_id":book_id}; send(chat_id,f"✏️ {book['name']} uchun aniq qoldiq sonini yozing.\\nHozir: {int(book.get('stock',0))} ta"); return

    if data.startswith("report_"):
        if not is_admin(chat_id): return''','qstock-cb')

p.write_text(t,encoding='utf-8')