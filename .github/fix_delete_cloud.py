from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')
old = '''        if book:\n            books.remove(book)\n            save_books()\n\n            send(\n                chat_id,\n                f"🗑 O‘chirildi: {book['name']}",\n                admin_menu()\n            )\n        return\n'''
new = '''        if book:\n            try:\n                cloud_bridge.delete_book(book)\n            except Exception as e:\n                send(chat_id, f"❌ Kitob o‘chirilmadi: {e}", admin_menu())\n                return\n            books.remove(book)\n            save_books()\n\n            send(\n                chat_id,\n                f"🗑 O‘chirildi: {book['name']}",\n                admin_menu()\n            )\n        return\n'''
if 'cloud_bridge.delete_book(book)' not in s:
    assert old in s, 'delete block not found'
    s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
