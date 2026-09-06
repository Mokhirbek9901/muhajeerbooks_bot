from pathlib import Path
p=Path('bot.py')
t=p.read_text(encoding='utf-8')
old='''def quick_stock_list_keyboard():
    refresh_books(); items=sorted(books,key=lambda b:str(b.get("name","")).casefold()); buttons=[[{"text":f"📦 {b['name']} — {int(b.get('stock',0))} ta","callback_data":f"qstock_book_{b['id']}"}] for b in items[:80]]; buttons.append([{"text":"⬅️ Admin panel","callback_data":"admin"}]); return {"inline_keyboard":buttons}
'''
new='''def quick_stock_list_keyboard(chat_id=None):
    refresh_books()
    items=sorted(books,key=lambda b:str(b.get("name","")).casefold())[:80]
    draft={}
    if chat_id is not None:
        state=states.get(chat_id,{})
        if state.get("action")=="quick_stock_batch":
            draft=state.get("stock_draft",{})
    buttons=[]
    for b in items:
        bid=int(b["id"])
        value=int(draft.get(str(bid),b.get("stock",0)))
        buttons.append([
            {"text":"➖1","callback_data":f"qstock_batch_{bid}_-1"},
            {"text":f"📦 {b['name']} — {value} ta","callback_data":"qstock_noop"},
            {"text":"➕1","callback_data":f"qstock_batch_{bid}_1"},
        ])
    buttons.append([{"text":"✅ OK — Saqlash","callback_data":"qstock_save"}])
    buttons.append([{"text":"❌ Bekor qilish","callback_data":"qstock_cancel"}])
    return {"inline_keyboard":buttons}
'''
if old not in t: raise RuntimeError('keyboard anchor not found')
t=t.replace(old,new,1)
old='''        if text == "⚡ Tezkor qoldiq":
            states.pop(chat_id,None); send(chat_id,"⚡ Qoldig‘ini tez o‘zgartirish uchun kitobni tanlang:",quick_stock_list_keyboard()); return
'''
new='''        if text == "⚡ Tezkor qoldiq":
            refresh_books()
            states[chat_id]={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}
            send(chat_id,"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id)); return
'''
if old not in t: raise RuntimeError('menu anchor not found')
t=t.replace(old,new,1)
start=t.index('    if data == "qstock_list":')
end=t.index('    if data.startswith("report_"):',start)
newblock='''    if data == "qstock_list":
        if not is_admin(chat_id): return
        refresh_books()
        states[chat_id]={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}
        send(chat_id,"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id)); return
    if data == "qstock_noop":
        return
    if data.startswith("qstock_batch_"):
        if not is_admin(chat_id): return
        try:
            parts=data.split("_"); book_id=int(parts[2]); delta=int(parts[3])
        except Exception: return
        state=states.get(chat_id,{})
        if state.get("action")!="quick_stock_batch":
            refresh_books(); state={"action":"quick_stock_batch","stock_draft":{str(int(b["id"])):int(b.get("stock",0)) for b in books}}; states[chat_id]=state
        draft=state.setdefault("stock_draft",{})
        current=int(draft.get(str(book_id),0)); draft[str(book_id)]=max(0,current+delta)
        try:
            edit_message(chat_id,message.get("message_id"),"⚡ Qoldiqni ➖1 / ➕1 bilan o‘zgartiring.\\nOxirida ✅ OK — Saqlash ni bosing.",quick_stock_list_keyboard(chat_id))
        except Exception as e: print("Tezkor qoldiq yangilash xatosi:",e)
        return
    if data == "qstock_save":
        if not is_admin(chat_id): return
        state=states.get(chat_id,{})
        if state.get("action")!="quick_stock_batch": send(chat_id,"ℹ️ Saqlanadigan o‘zgarish yo‘q.",admin_menu()); return
        draft=state.get("stock_draft",{}); refresh_books(); restocked=[]; changed=0
        for b in books:
            key=str(int(b["id"])); old_stock=int(b.get("stock",0)); new_stock=int(draft.get(key,old_stock))
            if new_stock!=old_stock:
                b["stock"]=new_stock; changed+=1
                if old_stock<=0<new_stock: restocked.append(b)
        if changed: save_books()
        states.pop(chat_id,None)
        for b in restocked: notify_restock(b)
        send(chat_id,f"✅ Saqlandi. {changed} ta kitob qoldig‘i yangilandi.",admin_menu()); return
    if data == "qstock_cancel":
        if not is_admin(chat_id): return
        states.pop(chat_id,None); send(chat_id,"❌ O‘zgarishlar saqlanmadi.",admin_menu()); return
    if data.startswith("qstock_book_") or data.startswith("qstock_adj_") or data.startswith("qstock_set_"):
        if not is_admin(chat_id): return
        send(chat_id,"ℹ️ Bu eski tezkor qoldiq oynasi. ⚡ Tezkor qoldiqni qayta oching.",admin_menu()); return

'''
t=t[:start]+newblock+t[end:]
p.write_text(t,encoding='utf-8')
