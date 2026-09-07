from pathlib import Path

# Repair sync_wrapper using the current helper names and make app-origin orders pull-only.
p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')

# App-origin orders must not masquerade as Telegram customers.
s = s.replace(
'''    linked_chat = int(row.get("telegram_chat_id") or existing.get("chat_id") or 0)
    if linked_chat <= 0 and ADMIN_ID:
        linked_chat = int(ADMIN_ID)
''',
'''    linked_chat = int(row.get("telegram_chat_id") or existing.get("chat_id") or 0)
''',
1,
)

start = s.index('def _book_fingerprint(book):')
end = s.index('if SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:', start)
new_tail = r'''def _book_fingerprint(book):
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
    last_books = []
    last_book_ids = set()
    last_book_fingerprints = {}
    last_orders = {}
    seen_cloud_orders = set()

    while True:
        try:
            # BOOKS — botdagi faqat haqiqiy o'zgarish push bo'ladi; cloud oxirgi manba.
            local = _read_books()
            if initialized and _prepare_bot_image_changes(local, last_books):
                _write_json(BOOKS_FILE, local)

            if not initialized:
                unsynced = [
                    b for b in local
                    if isinstance(b, dict) and not str(b.get("cloud_id") or "").strip()
                ]
                if unsynced:
                    _push_books(unsynced)
            else:
                current_ids = _book_ids(local)
                for tid in sorted(last_book_ids - current_ids):
                    try:
                        _rpc(
                            "bot_sync_delete",
                            {"p_secret": SYNC_SECRET, "p_telegram_id": tid, "p_cloud_id": None},
                        )
                        print(f"Bot → ilova kitob o‘chirildi: telegram_id={tid}")
                    except Exception as e:
                        print(f"Bot delete sync xatosi ({tid}):", e)

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
                    if last_book_fingerprints.get(tid) != _book_fingerprint(book):
                        changed.append(book)
                if changed:
                    _push_books(changed)

            rows = _pull_books()
            # Appdan yangi rasm kelsa Telegram file_id ham tayyorlanadi.
            if _sync_app_images_to_telegram(rows):
                rows = _pull_books()

            merged, unmapped = _merge_books(local, rows)
            if unmapped:
                _push_unmapped_books(merged, unmapped)
                rows = _pull_books()
                merged, _ = _merge_books(merged, rows)

            if _hash(merged) != _hash(local):
                _write_json(BOOKS_FILE, merged)

            last_books = [dict(b) for b in merged]
            last_book_ids = _book_ids(merged)
            last_book_fingerprints = {
                int(b.get("id")): _book_fingerprint(b)
                for b in merged
                if isinstance(b, dict) and str(b.get("id") or "").isdigit()
            }

            # ORDERS — Supabase yagona markaz. App orderlari botdan qayta push qilinmaydi.
            local_orders = _read_orders()
            if not initialized:
                for order in local_orders.values():
                    if (
                        isinstance(order, dict)
                        and str(order.get("source") or "telegram") != "app"
                    ):
                        try:
                            _push_order(order)
                        except Exception as e:
                            print("Eski bot buyurtmasi sync xatosi:", e)
            else:
                for key, order in local_orders.items():
                    if not isinstance(order, dict):
                        continue
                    if str(order.get("source") or "telegram") == "app":
                        continue
                    prev = last_orders.get(str(key))
                    if prev is None or _hash(order) != _hash(prev):
                        try:
                            _push_order(order)
                        except Exception as e:
                            print(f"Buyurtma sync xatosi ({key}):", e)

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
                seen_cloud_orders = set(current_cloud_ids)

            latest_local = _read_orders()
            merged_orders = dict(latest_local)
            new_app_orders = []
            for row in cloud_orders:
                if not isinstance(row, dict):
                    continue
                try:
                    key = str(int(row.get("telegram_order_id") or 0))
                except Exception:
                    continue
                if key == "0":
                    continue
                item = _cloud_order_to_bot(row, books_by_uuid, latest_local.get(key))
                if item is None:
                    continue
                merged_orders[key] = item
                cloud_id = str(row.get("id") or "")
                if (
                    initialized
                    and cloud_id
                    and cloud_id not in seen_cloud_orders
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(item)

            if _hash(merged_orders) != _hash(latest_local):
                _write_json(ORDERS_FILE, merged_orders)

            for order in new_app_orders:
                try:
                    _notify_admin_app_order(order)
                    print(f"Ilova → bot buyurtma: {order.get('order_id')}")
                except Exception as e:
                    print("Ilova buyurtma notification xatosi:", e)

            seen_cloud_orders.update(current_cloud_ids)
            last_orders = {
                str(k): dict(v) for k, v in merged_orders.items() if isinstance(v, dict)
            }
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


'''
s = s[:start] + new_tail + s[end:]
p.write_text(s, encoding='utf-8')

# Prefer the cloud image URL for synced books so replacing/removing an app image is reflected immediately.
p = Path('bot.py')
b = p.read_text(encoding='utf-8')
old = '''    # Telegramdagi file_id bo'lsa undan, programmadan yuklangan rasm bo'lsa public URLdan foydalanamiz.
    photo = str(book.get("photo_id", "") or book.get("image_url", "") or "").strip()
'''
new = '''    image_url = str(book.get("image_url", "") or "").strip()
    photo_id = str(book.get("photo_id", "") or "").strip()
    # Cloudga ulangan kitobda image_url rasmning yagona haqiqiy manbasi.
    photo = image_url if str(book.get("cloud_id", "") or "").strip() else (image_url or photo_id)
'''
assert old in b, 'send_book_detail image block not found'
b = b.replace(old, new, 1)

# Inactive promo also follows the same cloud image source.
b = b.replace(
'''        and (str(b.get("photo_id", "")).strip() or str(b.get("image_url", "")).strip())
''',
'''        and (str(b.get("image_url", "")).strip() if str(b.get("cloud_id", "")).strip() else (str(b.get("image_url", "")).strip() or str(b.get("photo_id", "")).strip()))
''',
1,
)
b = b.replace(
'''                    "photo": str(book.get("photo_id", "") or book.get("image_url", "")),
''',
'''                    "photo": (str(book.get("image_url", "") or "").strip() if str(book.get("cloud_id", "") or "").strip() else str(book.get("image_url", "") or book.get("photo_id", "") or "").strip()),
''',
1,
)
p.write_text(b, encoding='utf-8')
