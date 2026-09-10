from pathlib import Path

path = Path('bot.py')
text = path.read_text(encoding='utf-8')
old = 'send(chat_id, f"✅ {book[\'name\']} hozir sotuvda mavjud.", book_keyboard(book, chat_id))'
new = 'send(chat_id, f"✅ {book[\'name\']} hozir sotuvda mavjud.", book_detail_keyboard(book, chat_id))'
if old not in text:
    if new in text:
        print('Already fixed')
    else:
        raise RuntimeError('Missing restock deep-link keyboard target')
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print('Restock deep-link runtime fix applied')
