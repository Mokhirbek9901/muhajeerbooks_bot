from pathlib import Path

# Botdagi o‘chirish faqat aniq admin amali bilan Supabase'ga yuboriladi.
p = Path('bot.py')
s = p.read_text(encoding='utf-8')
old = '''        if book:\n            books.remove(book)\n            save_books()\n\n            send(\n                chat_id,\n                f"🗑 O‘chirildi: {book['name']}",\n                admin_menu()\n            )\n        return\n'''
new = '''        if book:\n            try:\n                cloud_bridge.delete_book(book)\n            except Exception as e:\n                send(chat_id, f"❌ Kitob o‘chirilmadi: {e}", admin_menu())\n                return\n            books.remove(book)\n            save_books()\n\n            send(\n                chat_id,\n                f"🗑 O‘chirildi: {book['name']}",\n                admin_menu()\n            )\n        return\n'''
if 'cloud_bridge.delete_book(book)' not in s:
    assert old in s, 'delete block not found'
    s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# Muhim: books.json vaqtincha qisqarib qolsa yoki boshqa thread uni qayta yozsa,
# buni kitob o‘chirildi deb qabul qilmaymiz. O‘chirish faqat yuqoridagi
# cloud_bridge.delete_book(book) orqali amalga oshadi.
p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')
start = '''                current_ids = _book_ids(local)\n                for tid in sorted(last_book_ids - current_ids):\n'''
end = '''\n                changed = []\n'''
if start in s:
    i = s.index(start)
    j = s.index(end, i)
    replacement = '''                current_ids = _book_ids(local)\n                # O‘chirishni local ro‘yxatdagi farqdan taxmin qilmaymiz.\n                # Botdagi haqiqiy delete cloud_bridge.delete_book(book) orqali atomik bajariladi.\n'''
    s = s[:i] + replacement + s[j:]
assert 'for tid in sorted(last_book_ids - current_ids)' not in s, 'unsafe inferred delete still present'
p.write_text(s, encoding='utf-8')
