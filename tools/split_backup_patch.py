from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

start = s.index('def create_backup():')
end = s.index('\ndef download_telegram_file', start)
new_backup = '''def create_books_backup():
    """Faqat kitoblar katalogini alohida JSON backup qiladi."""
    refresh_books()
    return json.dumps({
        "backup_version": 2,
        "backup_type": "books",
        "created_at": datetime.now().isoformat(),
        "books": books,
    }, ensure_ascii=False, indent=2)


def create_data_backup():
    """Kitoblardan tashqari doimiy ma'lumotlarni alohida JSON backup qiladi."""
    load_orders()
    load_users()
    load_favorites()
    load_ratings()
    load_restock()
    load_expenses()
    return json.dumps({
        "backup_version": 2,
        "backup_type": "data",
        "created_at": datetime.now().isoformat(),
        "orders": orders,
        "users": users,
        "favorites": favorites,
        "ratings": ratings,
        "restock_subscribers": restock_subscribers,
        "expenses": expenses,
    }, ensure_ascii=False, indent=2)


def restore_backup_file(path):
    """Books/data v2 backup yoki eski full backupni xavfsiz tiklaydi."""
    global books, orders, users, favorites, ratings, restock_subscribers, expenses

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Backup fayli noto'g'ri formatda.")

    backup_type = str(data.get("backup_type") or "").strip().lower()
    is_books = backup_type == "books"
    is_data = backup_type == "data"
    is_legacy = not backup_type and isinstance(data.get("books"), list)
    if not (is_books or is_data or is_legacy):
        raise ValueError("Backup turi aniqlanmadi.")

    payloads = {}

    if is_books or is_legacy:
        if not isinstance(data.get("books"), list):
            raise ValueError("Kitoblar backupida books ro'yxati yo'q.")
        restored_books = []
        for raw_book in data.get("books", []):
            if not isinstance(raw_book, dict):
                continue
            restored_book = dict(raw_book)
            restored_book.pop("cloud_id", None)
            restored_book.pop("web_photo_source_id", None)
            restored_books.append(restored_book)
        payloads[BOOKS_FILE] = restored_books

    if is_data or is_legacy:
        load_expenses()
        payloads.update({
            ORDERS_FILE: data.get("orders", {}),
            USERS_FILE: data.get("users", {}),
            FAVORITES_FILE: data.get("favorites", {}),
            RATINGS_FILE: data.get("ratings", {}),
            RESTOCK_FILE: data.get("restock_subscribers", {}),
            EXPENSES_FILE: data.get("expenses", expenses),
        })

    temp_files = []
    try:
        for target, value in payloads.items():
            tmp = target + ".restore.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            temp_files.append((tmp, target))
        for tmp, target in temp_files:
            os.replace(tmp, target)
    except Exception:
        for tmp, _ in temp_files:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
        raise

    if is_books or is_legacy:
        load_books()
    if is_data or is_legacy:
        load_orders()
        load_users()
        load_favorites()
        load_ratings()
        load_restock()
        load_expenses()

    carts.clear()
    states.clear()
    return len(books), len(orders), len(users)

'''
s = s[:start] + new_backup + s[end:]

marker = '        if text == "💾 Backup":'
cb_start = s.index(marker)
except_pos = s.index('            except Exception as e:', cb_start)
new_cb = '''        if text == "💾 Backup":
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                books_backup = create_books_backup()
                data_backup = create_data_backup()
                send_document(
                    chat_id,
                    f"muhajeer_books_kitoblar_{stamp}.json",
                    books_backup,
                    "📚 KITOBLAR BACKUP — faqat kitoblar, narxlar, qoldiq va kitob ma'lumotlari."
                )
                send_document(
                    chat_id,
                    f"muhajeer_books_malumotlar_{stamp}.json",
                    data_backup,
                    "🗂 MA'LUMOTLAR BACKUP — buyurtmalar, foydalanuvchilar, sevimlilar, reytinglar va xarajatlar."
                )
                send(
                    chat_id,
                    "✅ 2 ta alohida backup fayl yuborildi:\\n\\n"
                    "1️⃣ 📚 Kitoblar\\n"
                    "2️⃣ 🗂 Buyurtmalar va boshqa ma'lumotlar\\n\\n"
                    "Ikkalasini ham saqlab qo'ying.",
                    admin_menu()
                )
'''
s = s[:cb_start] + new_cb + s[except_pos:]

s = s.replace(
    "Oldin bot bergan `muhajeer_books_backup.json` faylini shu yerga yuboring.",
    "Bot bergan 📚 Kitoblar yoki 🗂 Ma'lumotlar backup JSON fayllaridan birini shu yerga yuboring."
)
s = s.replace(
    "⚠️ Backup tiklanganda hozirgi kitoblar, buyurtmalar va foydalanuvchilar ma'lumotlari backupdagi holat bilan almashtiriladi.",
    "⚠️ Qaysi backup turi yuborilsa, faqat o'sha bo'lim backupdagi holat bilan almashtiriladi."
)

anchor = 'expenses = {}\n'
reset_code = '''ORDER_HISTORY_RESET_MARKER = os.path.join(DATA_DIR, "order_history_reset_20260908_v1.done")
if not os.path.exists(ORDER_HISTORY_RESET_MARKER):
    tmp_orders = ORDERS_FILE + ".history_reset.tmp"
    with open(tmp_orders, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_orders, ORDERS_FILE)
    marker_tmp = ORDER_HISTORY_RESET_MARKER + ".tmp"
    with open(marker_tmp, "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat() + "\\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(marker_tmp, ORDER_HISTORY_RESET_MARKER)
    print("ORDER_HISTORY_RESET_20260908: local orders cleared")

'''
if 'ORDER_HISTORY_RESET_MARKER' not in s:
    s = s.replace(anchor, anchor + reset_code, 1)

p.write_text(s, encoding='utf-8')
