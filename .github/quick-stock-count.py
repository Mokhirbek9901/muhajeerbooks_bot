from pathlib import Path
p=Path('bot.py')
t=p.read_text(encoding='utf-8')
old='''        buttons.append([
            {"text":"➖1","callback_data":f"qstock_batch_{bid}_-1"},
            {"text":f"📦 {b['name']} — {value} ta","callback_data":"qstock_noop"},
            {"text":"➕1","callback_data":f"qstock_batch_{bid}_1"},
        ])
'''
new='''        buttons.append([
            {"text":"➖1","callback_data":f"qstock_batch_{bid}_-1"},
            {"text":f"📦 {b['name']}","callback_data":"qstock_noop"},
            {"text":f"{value} ta","callback_data":"qstock_noop"},
            {"text":"➕1","callback_data":f"qstock_batch_{bid}_1"},
        ])
'''
if old not in t: raise RuntimeError('quick stock row anchor not found')
t=t.replace(old,new,1)
old='''            [{"text": "⚠️ Kam qolgan"}, {"text": "⚡ Tezkor qoldiq"}],
'''
new='''            [{"text": "⚡ Tezkor qoldiq"}],
'''
if old not in t: raise RuntimeError('admin menu anchor not found')
t=t.replace(old,new,1)
p.write_text(t,encoding='utf-8')
