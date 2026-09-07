from pathlib import Path

# 1) Bot har xabar/callbackda cloud orqali yangilangan buyurtmalarni ham o'qisin.
p = Path('bot.py')
s = p.read_text(encoding='utf-8')

old = '''def handle_message(message):\n    # Har bir yangi xabarda books.json dan eng yangi ombor holatini yuklaymiz.\n    # Shu sabab admin qoldiqni o'zgartirgach, boshqa foydalanuvchilar ham yangi sonni ko'radi.\n    load_books()\n'''
new = '''def handle_message(message):\n    # Har bir yangi xabarda kitoblar va buyurtmalarning eng yangi cloud nusxasini o'qiymiz.\n    load_books()\n    load_orders()\n'''
assert old in s, 'handle_message block not found'
s = s.replace(old, new, 1)

old = '''def handle_callback(callback):\n    # Callback kelganda ham omborning eng yangi holatini yuklaymiz.\n    load_books()\n'''
new = '''def handle_callback(callback):\n    # Callback kelganda ham kitoblar va buyurtmalarning eng yangi holatini yuklaymiz.\n    load_books()\n    load_orders()\n'''
assert old in s, 'handle_callback block not found'
s = s.replace(old, new, 1)

# App rasmini Telegram URL orqali ham ishlatish inactive xabarlarda saqlansin.
s = s.replace(
    '''        and str(b.get("photo_id", "")).strip()\n''',
    '''        and str(b.get("photo_id", "") or b.get("image_url", "")).strip()\n''',
    1,
)
s = s.replace(
    '''                    "photo": book["photo_id"],\n''',
    '''                    "photo": str(book.get("photo_id", "") or book.get("image_url", "")),\n''',
    1,
)
p.write_text(s, encoding='utf-8')

# 2) Sync loop: faqat BOTDA HAQIQATAN o'zgargan kitobni cloudga push qiladi.
# Shu bilan appdan o'chirilgan kitob eski local nusxadan qayta tirilmaydi.
p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')
start = s.index('def sync_loop():')
end_marker = 'runpy.run_path("bot.py", run_name="__main__")'
end = s.index(end_marker, start)

tail = r'''def _book_fingerprint(book):
    if not isinstance(book, dict):
        return ""
    payload = {
        k: book.get(k)
        for k in (
            "cloud_id", "name", "author", "category", "description",
            "price", "old_price", "cost_price", "stock", "discount_percent",
            "image_url", "photo_id", "cover", "recommended", "is_active",
        )
    }
    return _hash(payload)


def sync_loop():
    initialized = False
    seen_order_ids = set()
    last_book_ids = set()
    last_book_fingerprints = {}

    while True:
        try:
            # -------------------------
            # BOOKS — ikki tomonlama, conflict-safe sync
            # -------------------------
            local = _read_books()
            if local and _sync_telegram_covers(local):
                _write_books(local)

            if not initialized:
                # Faqat hali cloud_id olmagan eski/local kitoblar bir marta yuboriladi.
                unsynced = [
                    b for b in local
                    if isinstance(b, dict) and not str(b.get("cloud_id") or "").strip()
                ]
                if unsynced:
                    _push(unsynced)
            else:
                current_ids = _book_ids(local)

                # Botdan o'chirilgan kitob — clouddan ham o'chadi.
                for tid in sorted(last_book_ids - current_ids):
                    try:
                        _rpc(
                            "bot_sync_delete",
                            {"p_secret": SYNC_SECRET, "p_telegram_id": tid, "p_cloud_id": None},
                        )
                        print(f"Bot → ilova kitob o‘chirildi: telegram_id={tid}")
                    except Exception as e:
                        print(f"Bot delete sync xatosi ({tid}):", e)

                # MUHIM: butun local katalogni push qilmaymiz.
                # Faqat botda oldingi sikldan beri haqiqatan o'zgargan/yangi kitoblar yuboriladi.
                changed = []
                for book in local:
                    if not isinstance(book, dict):
                        continue
                    try:
                        tid = int(book.get("id") or 0)
                    except Exception:
                        continue
                    if tid <= 0:
                        continue
                    fp = _book_fingerprint(book)
                    if last_book_fingerprints.get(tid) != fp:
                        changed.append(book)
                if changed:
                    _push(changed)

            # Cloud holati doim yakuniy merge bosqichi bo'ladi.
            rows = _pull_rows()
            cloud_local = _merge_cloud(local, rows)
            if _hash(cloud_local) != _hash(local):
                _write_books(cloud_local)
                local = cloud_local
            else:
                local = cloud_local

            last_book_ids = _book_ids(local)
            last_book_fingerprints = {
                int(b.get("id")): _book_fingerprint(b)
                for b in local
                if isinstance(b, dict) and str(b.get("id") or "").isdigit()
            }

            # -------------------------
            # ORDERS — Supabase yagona markaziy baza
            # -------------------------
            local_orders = _read_orders()

            # Cloudga hali yozilmagan eski/yangi Telegram buyurtmalarini retry qilamiz.
            if _import_unsynced_orders(local_orders):
                _write_orders(local_orders)

            cloud_orders = _pull_orders()
            books_by_uuid = {
                str(b.get("id")): b for b in rows if isinstance(b, dict)
            }

            current_cloud_ids = {
                str(r.get("id"))
                for r in cloud_orders
                if isinstance(r, dict) and r.get("id")
            }
            if not initialized:
                # Restart paytida eski app buyurtmalariga notification yog'ilib ketmasin.
                seen_order_ids = set(current_cloud_ids)

            latest_local = _read_orders()
            merged_orders = dict(latest_local)
            new_app_orders = []

            for row in cloud_orders:
                if not isinstance(row, dict):
                    continue
                raw_number = row.get("telegram_order_id") or row.get("order_number")
                try:
                    key = str(int(raw_number))
                except Exception:
                    continue

                merged = _cloud_order_to_bot(row, books_by_uuid, latest_local.get(key))
                if merged is None:
                    continue
                merged_orders[key] = merged

                cloud_id = str(row.get("id") or "")
                if (
                    initialized
                    and cloud_id
                    and cloud_id not in seen_order_ids
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(merged)

            if _hash(merged_orders) != _hash(latest_local):
                _write_orders(merged_orders)

            for order in new_app_orders:
                try:
                    _notify_admin_app_order(order)
                    print(f"Ilova → bot yangi buyurtma: {order.get('order_id')}")
                except Exception as e:
                    print("Ilova buyurtmasi admin notification xatosi:", e)

            seen_order_ids.update(current_cloud_ids)
            initialized = True

        except urllib.error.HTTPError as e:
            try:
                details = e.read().decode("utf-8")
            except Exception:
                details = str(e)
            print("Supabase sync HTTP xatosi:", e.code, details)
        except Exception as e:
            print("Supabase sync xatosi:", e)

        time.sleep(SYNC_INTERVAL)


if SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:
    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()
else:
    print("Supabase sync environment variablelari topilmadi; bot odatdagi rejimda ishlaydi.")

'''

s = s[:start] + tail + end_marker + '\n'
p.write_text(s, encoding='utf-8')
