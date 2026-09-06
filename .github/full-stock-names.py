from pathlib import Path
p=Path('bot.py')
t=p.read_text(encoding='utf-8')
old='''        buttons.append([\n            {"text":"➖1","callback_data":f"qstock_batch_{bid}_-1"},\n            {"text":f"📦 {b['name']}","callback_data":"qstock_noop"},\n            {"text":f"{value} ta","callback_data":"qstock_noop"},\n            {"text":"➕1","callback_data":f"qstock_batch_{bid}_1"},\n        ])'''
new='''        buttons.append([{"text":f"📦 {b['name']} — {value} ta","callback_data":"qstock_noop"}])\n        buttons.append([\n            {"text":"➖1","callback_data":f"qstock_batch_{bid}_-1"},\n            {"text":f"{value} ta","callback_data":"qstock_noop"},\n            {"text":"➕1","callback_data":f"qstock_batch_{bid}_1"},\n        ])'''
if old not in t: raise RuntimeError('quick stock row not found')
t=t.replace(old,new,1)
p.write_text(t,encoding='utf-8')
