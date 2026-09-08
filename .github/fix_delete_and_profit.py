from pathlib import Path
import re

# -------------------------
# bot.py
# -------------------------
bot = Path('bot.py')
s = bot.read_text(encoding='utf-8')

# Tannarx 0 bo'lsa, keyinchalik kitobga tannarx kiritilganda eski buyurtmalar
# ham joriy kitob tannarxidan foydalanib qayta hisoblasin.
old_cost = '''def order_cost_summary(order):
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
'''
new_cost = '''def order_cost_summary(order):
    total_cost=0; missing_qty=0; items=order.get("items")
    if isinstance(items,list) and items:
        for item in items:
            qty=int(item.get("qty",0) or 0)
            try:
                unit_cost=int(item.get("unit_cost") or 0)
            except Exception:
                unit_cost=0
            # Buyurtma vaqtida tannarx 0 bo'lgan bo'lsa, keyinchalik kitobga
            # tannarx kiritilganda tarixiy hisobot ham avtomatik aniqlashadi.
            if unit_cost <= 0:
                b=find_book(item.get("book_id"))
                current_cost=int(b.get("cost_price",0) or 0) if b else 0
                if current_cost > 0:
                    unit_cost=current_cost
            total_cost += unit_cost*qty
            missing_qty += qty if unit_cost<=0 else 0
        return total_cost,missing_qty
    for bid,qty in order.get("cart",{}).items():
        qty=int(qty); b=find_book(bid); unit_cost=int(b.get("cost_price",0) or 0) if b else 0; total_cost += unit_cost*qty; missing_qty += qty if unit_cost<=0 else 0
'''
if old_cost in s:
    s = s.replace(old_cost, new_cost, 1)
elif 'tarixiy hisobot ham avtomatik aniqlashadi' not in s:
    raise SystemExit('order_cost_summary pattern not found')

# Jo'natildi endi yakuniy bosqich: statistika faqat jo'natilgan/yakunlangan savdoni oladi.
s = s.replace('paid_statuses = ("paid", "shipped", "delivered")', 'paid_statuses = ("shipped", "delivered")')

# Delete callback: cloud + localni atomikroq tozalash va eski tugmada aniq javob.
old_delete = '''    if data.startswith("delete_"):
        if not is_admin(chat_id):
            return

        book_id = int(data.split("_", 1)[1])
        book = find_book(book_id)

        if book:
            try:
                cloud_bridge.delete_book(book)
            except Exception as e:
                send(chat_id, f"❌ Kitob o‘chirilmadi: {e}", admin_menu())
                return
            books.remove(book)
            save_books()

            send(
                chat_id,
                f"🗑 O‘chirildi: {book['name']}",
                admin_menu()
            )
        return
'''
new_delete = '''    if data.startswith("delete_"):
        if not is_admin(chat_id):
            return

        try:
            book_id = int(data.split("_", 1)[1])
        except Exception:
            send(chat_id, "❌ Kitob ID noto‘g‘ri.", admin_menu())
            return

        refresh_books()
        book = find_book(book_id)
        if not book:
            send(
                chat_id,
                "ℹ️ Bu eski tugma. Kitob allaqachon o‘chirilgan yoki ro‘yxat yangilangan.\n"
                "Kitoblar ro‘yxatini qayta oching.",
                admin_menu()
            )
            return

        try:
            cloud_bridge.delete_book(book)
        except Exception as e:
            send(chat_id, f"❌ Kitob o‘chirilmadi: {e}", admin_menu())
            return

        # Bir xil ID/cloud_id bilan qolgan stale lokal nusxalarni ham birdan tozalaymiz.
        target_cloud = str(book.get("cloud_id") or "")
        target_id = str(book.get("id") or "")
        books[:] = [
            b for b in books
            if str(b.get("id") or "") != target_id
            and (not target_cloud or str(b.get("cloud_id") or "") != target_cloud)
        ]
        save_books()
        refresh_books()

        send(
            chat_id,
            f"🗑 O‘chirildi: {book['name']}\n\n✅ Bot va ilova katalogidan olib tashlandi.",
            edit_book_menu() if books else admin_menu()
        )
        return
'''
if old_delete in s:
    s = s.replace(old_delete, new_delete, 1)
elif 'Bot va ilova katalogidan olib tashlandi' not in s:
    raise SystemExit('delete callback pattern not found')

bot.write_text(s, encoding='utf-8')

# -------------------------
# sync_wrapper.py
# -------------------------
sync = Path('sync_wrapper.py')
w = sync.read_text(encoding='utf-8')

if 'from datetime import datetime' not in w:
    w = w.replace('import urllib.request\n', 'import urllib.request\nfrom datetime import datetime\n', 1)

pull_anchor = '''def _pull_books():
    rows = _rpc("bot_sync_pull", {"p_secret": SYNC_SECRET})
    return rows if isinstance(rows, list) else []
'''
pull_new = pull_anchor + '''\n\ndef _pull_tombstones():
    rows = _rpc("bot_sync_tombstones_pull", {"p_secret": SYNC_SECRET})
    return rows if isinstance(rows, list) else []


def _parse_iso(value):
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _remove_tombstoned_local(items, tombstones):
    tomb_by_id = {}
    for row in tombstones or []:
        try:
            tid = int(row.get('telegram_id') or 0)
        except Exception:
            continue
        if tid > 0:
            tomb_by_id[tid] = row

    cleaned = []
    removed = []
    for book in items or []:
        if not isinstance(book, dict):
            continue
        try:
            tid = int(book.get('id') or 0)
        except Exception:
            tid = 0
        tomb = tomb_by_id.get(tid)
        if not tomb:
            cleaned.append(book)
            continue

        book_cloud = str(book.get('cloud_id') or '').strip()
        tomb_cloud = str(tomb.get('cloud_id') or '').strip()
        created = _parse_iso(book.get('created_at'))
        deleted = _parse_iso(tomb.get('deleted_at'))

        # Aynan o'chirilgan cloud nusxasi yoki tombstonedan eski lokal nusxa — olib tashlanadi.
        stale_same_cloud = bool(book_cloud and tomb_cloud and book_cloud == tomb_cloud)
        stale_by_time = not (created and deleted and created > deleted)
        if stale_same_cloud or stale_by_time:
            removed.append(book)
            continue
        cleaned.append(book)
    return cleaned, removed
'''
if 'def _pull_tombstones():' not in w:
    if pull_anchor not in w:
        raise SystemExit('_pull_books anchor not found')
    w = w.replace(pull_anchor, pull_new, 1)

loop_anchor = '''        try:
            local = _read_books()
            if initialized and _prepare_bot_image_changes(local, last_local_books):
'''
loop_new = '''        try:
            local = _read_books()
            tombstones = _pull_tombstones()
            local, removed_stale = _remove_tombstoned_local(local, tombstones)
            if removed_stale:
                _write_json(BOOKS_FILE, local)
                print("Tombstone bo‘yicha lokal katalog tozalandi:", ", ".join(str(b.get('name') or b.get('id')) for b in removed_stale))
            if initialized and _prepare_bot_image_changes(local, last_local_books):
'''
if 'removed_stale = _remove_tombstoned_local' not in w:
    if loop_anchor not in w:
        raise SystemExit('sync loop anchor not found')
    w = w.replace(loop_anchor, loop_new, 1)

sync.write_text(w, encoding='utf-8')
