from pathlib import Path
import re


def replace_def(text, name, replacement):
    pattern = rf"(?ms)^def {re.escape(name)}\([^\n]*\):\n.*?(?=^def |\Z)"
    updated, count = re.subn(pattern, replacement.rstrip() + "\n\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not replace {name}")
    return updated


path = Path('bot.py')
text = path.read_text(encoding='utf-8')

text = replace_def(text, 'edit_book_menu', r'''def edit_book_menu(page=0):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"✏️ {b['name']}",
        "callback_data": f"edit_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("editpage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}
''')

text = replace_def(text, 'delete_book_menu', r'''def delete_book_menu(page=0):
    refresh_books()
    items = sorted(books, key=lambda b: str(b.get("name", "")).casefold())
    current, page, total = _admin_page(items, page)
    buttons = [[{
        "text": f"🗑 {b['name']}",
        "callback_data": f"delete_{b['id']}"
    }] for b in current]
    buttons.extend(_page_nav("deletepage", page, total))
    buttons.append([{"text": "⬅️ Admin panel", "callback_data": "admin"}])
    return {"inline_keyboard": buttons}
''')

old = '''    if data.startswith("editpage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        edit_book_menu(page, chat_id, message_id); return
    if data.startswith("deletepage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        delete_book_menu(page, chat_id, message_id); return
'''
new = '''    if data.startswith("editpage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        try:
            edit_message(chat_id, message_id, "✏️ Tahrirlash uchun kitob tanlang:", edit_book_menu(page))
        except Exception:
            send(chat_id, "✏️ Tahrirlash uchun kitob tanlang:", edit_book_menu(page))
        return
    if data.startswith("deletepage_"):
        if not is_admin(chat_id): return
        try: page = int(data.rsplit("_", 1)[1])
        except Exception: page = 0
        try:
            edit_message(chat_id, message_id, "🗑 O‘chirish uchun kitobni tanlang:", delete_book_menu(page))
        except Exception:
            send(chat_id, "🗑 O‘chirish uchun kitobni tanlang:", delete_book_menu(page))
        return
'''
if old not in text:
    raise RuntimeError('Missing pagination callback contract block')
text = text.replace(old, new, 1)

# Guard against the exact semantic regression this patch fixes.
for snippet in [
    'edit_book_menu()\n            )',
    'delete_book_menu()\n            )',
    'edit_book_menu() if books else admin_menu()',
]:
    if snippet not in text:
        raise RuntimeError(f'Expected legacy keyboard caller missing: {snippet}')

path.write_text(text, encoding='utf-8')
print('Admin pager contract fixed')
