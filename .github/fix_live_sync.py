from pathlib import Path

p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')

start = s.index('def _sync_app_images_to_telegram(')
end = s.index('def _push_unmapped_books(', start)
image_func = r'''def _sync_app_images_to_telegram(rows, previous_rows):
    previous = {
        str(row.get("id")): row
        for row in (previous_rows or [])
        if isinstance(row, dict) and row.get("id")
    }
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        cloud_id = str(row.get("id") or "")
        if not cloud_id:
            continue
        image_url = str(row.get("image_url") or "").strip()
        photo_id = str(row.get("telegram_photo_id") or "").strip()
        old = previous.get(cloud_id, {})
        old_image = str(old.get("image_url") or "").strip()
        old_photo = str(old.get("telegram_photo_id") or "").strip()
        app_image_changed = bool(old) and image_url != old_image and photo_id == old_photo
        needs_photo = bool(image_url) and (not photo_id or app_image_changed)
        app_image_removed = bool(old) and not image_url and bool(old_image) and photo_id == old_photo
        try:
            if needs_photo:
                new_id = _telegram_file_id_from_url(image_url)
                if new_id:
                    _rpc("bot_sync_set_photo", {
                        "p_secret": SYNC_SECRET,
                        "p_cloud_id": cloud_id,
                        "p_photo_id": new_id,
                    })
                    print(f"Ilova → Telegram rasm yangilandi: {row.get('title','')}")
                    changed = True
            elif app_image_removed and photo_id:
                _rpc("bot_sync_set_photo", {
                    "p_secret": SYNC_SECRET,
                    "p_cloud_id": cloud_id,
                    "p_photo_id": "",
                })
                print(f"Ilova → Telegram rasm o‘chirildi: {row.get('title','')}")
                changed = True
        except Exception as e:
            print("Ilova rasm sync xatosi:", e)
    return changed


'''
s = s[:start] + image_func + s[end:]

start = s.index('def sync_loop():')
end = s.index('\n\nif SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:', start)
loop = r'''def sync_loop():
    initialized = False
    seen_order_ids = set()
    last_local_books = []
    last_book_ids = set()
    last_book_fingerprints = {}
    last_cloud_rows = []

    while True:
        try:
            local = _read_books()
            if initialized and _prepare_bot_image_changes(local, last_local_books):
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
                        _rpc("bot_sync_delete", {
                            "p_secret": SYNC_SECRET,
                            "p_telegram_id": tid,
                            "p_cloud_id": None,
                        })
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
                    fp = _book_fingerprint(book)
                    if last_book_fingerprints.get(tid) != fp:
                        changed.append(book)
                if changed:
                    _push_books(changed)

            rows = _pull_books()
            if _sync_app_images_to_telegram(rows, last_cloud_rows):
                rows = _pull_books()

            merged, unmapped = _merge_books(local, rows)
            if unmapped:
                _push_unmapped_books(merged, unmapped)
                rows = _pull_books()
                merged, _ = _merge_books(merged, rows)

            latest_local = _read_books()
            if _hash(latest_local) == _hash(local):
                if _hash(merged) != _hash(latest_local):
                    _write_json(BOOKS_FILE, merged)
                local = merged
            else:
                local = latest_local

            last_local_books = [dict(b) for b in local if isinstance(b, dict)]
            last_book_ids = _book_ids(local)
            last_book_fingerprints = {
                int(b.get("id")): _book_fingerprint(b)
                for b in local
                if isinstance(b, dict) and str(b.get("id") or "").isdigit()
            }
            last_cloud_rows = [dict(r) for r in rows if isinstance(r, dict)]

            local_orders = _read_orders()
            orders_changed = False
            for key, order in list(local_orders.items()):
                if not isinstance(order, dict):
                    continue
                if str(order.get("cloud_order_id") or "").strip():
                    continue
                if str(order.get("source") or "telegram") == "app":
                    continue
                try:
                    result = _rpc("bot_order_create", {
                        "p_secret": SYNC_SECRET,
                        "p_order": order,
                        "p_preserve_stock": True,
                    })
                    if isinstance(result, dict) and result.get("id"):
                        order["cloud_order_id"] = str(result.get("id"))
                        order["source"] = "telegram"
                        local_orders[str(key)] = order
                        orders_changed = True
                except Exception as e:
                    print(f"Telegram buyurtmasini cloudga retry xatosi ({key}):", e)
            if orders_changed:
                _write_json(ORDERS_FILE, local_orders)

            cloud_orders = _pull_orders()
            books_by_uuid = {
                str(r.get("id")): r for r in rows if isinstance(r, dict) and r.get("id")
            }
            current_cloud_ids = {
                str(r.get("id"))
                for r in cloud_orders
                if isinstance(r, dict) and r.get("id")
            }
            if not initialized:
                seen_order_ids = set(current_cloud_ids)

            latest_orders = _read_orders()
            merged_orders = dict(latest_orders)
            new_app_orders = []
            for row in cloud_orders:
                if not isinstance(row, dict):
                    continue
                raw_number = row.get("telegram_order_id") or row.get("order_number")
                try:
                    key = str(int(raw_number))
                except Exception:
                    continue
                merged_order = _cloud_order_to_bot(row, books_by_uuid, latest_orders.get(key))
                if merged_order is None:
                    continue
                merged_orders[key] = merged_order
                cloud_id = str(row.get("id") or "")
                if (
                    initialized and cloud_id and cloud_id not in seen_order_ids
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(merged_order)

            if _hash(merged_orders) != _hash(latest_orders):
                _write_json(ORDERS_FILE, merged_orders)

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
'''
s = s[:start] + loop + s[end:]
p.write_text(s, encoding='utf-8')
