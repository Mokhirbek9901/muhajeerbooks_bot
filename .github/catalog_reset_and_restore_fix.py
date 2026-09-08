from pathlib import Path

# ---------------- bot.py: backup restore cloud IDs ----------------
p = Path('bot.py')
s = p.read_text(encoding='utf-8')
anchor = '''    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        raise ValueError("Backup fayli noto'g'ri yoki eski formatda.")

    load_expenses()
'''
replacement = '''    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        raise ValueError("Backup fayli noto'g'ri yoki eski formatda.")

    # To'liq katalog resetidan keyin backupdagi eski Supabase UUID (cloud_id)
    # mavjud bo'lmaydi. Telegram kitob IDlarini saqlaymiz, cloud_idni esa olib
    # tashlaymiz — sync ularni yangi cloud kitob sifatida qayta yaratadi.
    restored_books = []
    for raw_book in data.get("books", []):
        if not isinstance(raw_book, dict):
            continue
        restored_book = dict(raw_book)
        restored_book.pop("cloud_id", None)
        restored_book.pop("web_photo_source_id", None)
        restored_books.append(restored_book)

    load_expenses()
'''
if 'restored_book.pop("cloud_id", None)' not in s:
    if anchor not in s:
        raise SystemExit('restore anchor not found')
    s = s.replace(anchor, replacement, 1)
s = s.replace('        BOOKS_FILE: data["books"],', '        BOOKS_FILE: restored_books,', 1)
p.write_text(s, encoding='utf-8')

# ---------------- sync_wrapper.py: one-time coordinated full reset ----------------
p = Path('sync_wrapper.py')
w = p.read_text(encoding='utf-8')
const_anchor = '''BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
SYNC_INTERVAL = 2
'''
const_new = '''BOOKS_FILE = os.path.join(DATA_DIR, "books.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
SYNC_INTERVAL = 2
CATALOG_RESET_MARKER = os.path.join(DATA_DIR, "catalog_full_reset_20260908_v1.done")
'''
if 'CATALOG_RESET_MARKER' not in w:
    if const_anchor not in w:
        raise SystemExit('sync constants anchor not found')
    w = w.replace(const_anchor, const_new, 1)

func_anchor = '''def _read_orders():
    data = _read_json(ORDERS_FILE, {})
    return data if isinstance(data, dict) else {}


'''
func_new = func_anchor + '''def _catalog_reset_once():
    """User so'ragan bir martalik to'liq katalog reset: cloud + Railway volume."""
    if os.path.exists(CATALOG_RESET_MARKER):
        return
    result = _rpc("bot_catalog_reset", {"p_secret": SYNC_SECRET})
    _write_json(BOOKS_FILE, [])
    tmp = CATALOG_RESET_MARKER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(result or {"ok": True}, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CATALOG_RESET_MARKER)
    print("CATALOG_FULL_RESET_20260908:", result)


'''
if 'def _catalog_reset_once()' not in w:
    if func_anchor not in w:
        raise SystemExit('sync function anchor not found')
    w = w.replace(func_anchor, func_new, 1)

bottom_old = '''if SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:
    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()
else:
'''
bottom_new = '''if SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:
    # Sync boshlanishidan OLDIN ikkala katalogni atomik reset qilamiz; aks holda
    # eski Railway books.json cloudga yana qayta push bo'lib ketishi mumkin.
    _catalog_reset_once()
    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()
else:
'''
if '_catalog_reset_once()\n    threading.Thread' not in w:
    if bottom_old not in w:
        raise SystemExit('sync bottom anchor not found')
    w = w.replace(bottom_old, bottom_new, 1)

p.write_text(w, encoding='utf-8')
