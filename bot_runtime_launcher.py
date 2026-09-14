from pathlib import Path

# Telegram kitob kartalarida ilovadagi 1-rasm ko‘rsatiladi.
# Rasm birinchi ko‘rishda Telegramga cache qilinadi, keyingi ko‘rishlarda
# Supabase URL emas, Telegram file_id ishlatiladi.


def run_bot_patched():
    source = Path("bot.py").read_text(encoding="utf-8")

    # Admin kitoblar ro‘yxatini Telegram 4096 belgi limitidan xavfsiz saqlaymiz.
    # Bu patch moliya hisobiga tegmaydi. Moliya/statistika endi bot.py ichida
    # to‘g‘ridan-to‘g‘ri shared Supabase hisobotidan olinadi.
    old_books = '''        if text == "📚 Kitoblar ro‘yxati":
            send(
                chat_id,
                admin_books_text(),
                admin_menu()
            )
            return
'''
    new_books = '''        if text == "📚 Kitoblar ro‘yxati":
            full_text = admin_books_text()
            chunks = []
            current_lines = []
            current_len = 0
            for line in full_text.splitlines():
                line_len = len(line) + 1
                if current_lines and current_len + line_len > 3500:
                    chunks.append("\\n".join(current_lines))
                    current_lines = [line]
                    current_len = line_len
                else:
                    current_lines.append(line)
                    current_len += line_len
            if current_lines:
                chunks.append("\\n".join(current_lines))
            if not chunks:
                chunks = ["📚 Hozircha kitob yo‘q."]
            for index, chunk in enumerate(chunks):
                send(chat_id, chunk, admin_menu() if index == len(chunks) - 1 else None)
            return
'''
    if old_books in source:
        source = source.replace(old_books, new_books, 1)

    # Kitobni bosganda 1-rasm + nomi + narxi + ombor holati ko‘rinadi.
    # Birinchi marta ilova/Supabase URL Telegramga beriladi; Telegram yaratgan
    # yengilroq photo file_id saqlanadi va keyingi safar Supabase rasm trafik
    # umuman ishlatilmaydi. Rasm xira bo‘lmasligi uchun 1280px gacha variant tanlanadi.
    old_detail = '''def send_book_detail(chat_id, book):
    text = book_detail_text(book)
    markup = book_detail_keyboard(book, chat_id)
    # Text-only Telegram catalog; preserve image fields for the app.
    send(chat_id, text, markup)
'''
    new_detail = r'''def _book_photo_caption(book):
    stock = int(book.get("stock", 0) or 0)
    lines = [
        "📚 MUHAJEER BOOKS",
        f"📖 {book.get('name', 'Kitob')}",
        "",
        price_text(book),
        f"📦 Holati: {'Sotuvda — ' + str(stock) + ' ta' if stock > 0 else 'Hozircha mavjud emas'}",
    ]
    author = str(book.get("author") or "").strip()
    cover = str(book.get("cover") or "").strip()
    if author and author != "Ko‘rsatilmagan":
        lines.append(f"✍️ Muallif: {author}")
    if cover and cover != "Ko‘rsatilmagan":
        lines.append(f"📕 Muqova: {cover}")
    return "\n".join(lines)


def _light_telegram_photo_id(result):
    """Telegram yaratgan variantlardan tiniq, lekin yengilroq file_id tanlaydi."""
    photos = ((result or {}).get("result") or {}).get("photo") or []
    valid = [p for p in photos if isinstance(p, dict) and p.get("file_id")]
    if not valid:
        return ""

    def area(p):
        return int(p.get("width") or 0) * int(p.get("height") or 0)

    preferred = [
        p for p in valid
        if max(int(p.get("width") or 0), int(p.get("height") or 0)) <= 1280
        and (not p.get("file_size") or int(p.get("file_size") or 0) <= 650_000)
    ]
    if not preferred:
        preferred = [
            p for p in valid
            if max(int(p.get("width") or 0), int(p.get("height") or 0)) <= 1280
        ]
    if not preferred:
        preferred = valid
    return str(max(preferred, key=area).get("file_id") or "")


def _save_telegram_photo_cache(book, file_id):
    file_id = str(file_id or "").strip()
    if not file_id:
        return
    book["photo_id"] = file_id
    book["telegram_photo_source_url"] = str(book.get("image_url") or "").strip()
    book["_telegram_photo_cache_only"] = True
    try:
        save_books()
    except Exception as exc:
        print("Telegram rasm cache lokal saqlash xatosi:", exc)
    try:
        cloud_id = str(book.get("cloud_id") or "").strip()
        if cloud_id:
            cloud_bridge.rpc("bot_sync_set_photo", {
                "p_secret": cloud_bridge.SYNC_SECRET,
                "p_cloud_id": cloud_id,
                "p_photo_id": file_id,
            })
    except Exception as exc:
        print("Telegram rasm cache cloud saqlash xatosi:", exc)


def send_book_detail(chat_id, book):
    text = book_detail_text(book)
    markup = book_detail_keyboard(book, chat_id)
    photo_id = str(book.get("photo_id") or "").strip()
    image_url = str(book.get("image_url") or "").strip()

    # Telegram photo caption limiti 1024 belgi. Ko‘p kitoblarda to‘liq ma’lumot
    # bitta kartaga sig‘adi; juda uzun tavsif bo‘lsa to‘liq matn pastda chiqadi.
    caption = text if len(text) <= 950 else _book_photo_caption(book)
    extra_text = "" if caption == text else text

    def send_photo_value(value):
        return api("sendPhoto", {
            "chat_id": chat_id,
            "photo": value,
            "caption": caption,
            "reply_markup": json.dumps(markup, ensure_ascii=False),
        })

    # Cache mavjud: faqat Telegram file_id ishlaydi, Supabase rasm egressi 0.
    if photo_id:
        try:
            result = send_photo_value(photo_id)
            if extra_text:
                send(chat_id, extra_text)
            return result
        except Exception as exc:
            print("Telegram cached rasm yuborish xatosi, URL bilan qayta uriniladi:", exc)

    # Cache yo‘q: rasm URL bir marta olinadi, keyin yengil Telegram file_id saqlanadi.
    if image_url:
        try:
            result = send_photo_value(image_url)
            cached_id = _light_telegram_photo_id(result)
            if cached_id:
                _save_telegram_photo_cache(book, cached_id)
            if extra_text:
                send(chat_id, extra_text)
            return result
        except Exception as exc:
            print("Telegram rasmli kitob kartasi xatosi:", exc)

    # Rasm yo‘q yoki Telegram rasmni ololmasa funksiyalar yo‘qolmaydi.
    return send(chat_id, text, markup)
'''
    if old_detail not in source:
        raise RuntimeError("bot.py ichidagi send_book_detail bloki topilmadi.")
    source = source.replace(old_detail, new_detail, 1)

    namespace = {"__name__": "__main__", "__file__": "bot.py"}
    exec(compile(source, "bot.py", "exec"), namespace, namespace)


sync_source = Path("sync_wrapper.py").read_text(encoding="utf-8")

# Lazy Telegram photo cache lokal photo_idni o‘zgartirganda uni Telegramdan
# Supabase Storagega qayta yuklab, ilova muqovasini almashtirib yubormaymiz.
old_image_guard = '''        now_photo = str(book.get("photo_id") or "").strip()
        old_photo = str(prev.get("photo_id") or "").strip()
        if now_photo == old_photo:
            continue
'''
new_image_guard = '''        now_photo = str(book.get("photo_id") or "").strip()
        old_photo = str(prev.get("photo_id") or "").strip()
        cache_only = bool(book.pop("_telegram_photo_cache_only", False))
        if cache_only:
            changed = True
            if now_photo != old_photo:
                continue
        if now_photo == old_photo:
            continue
'''
if old_image_guard not in sync_source:
    raise RuntimeError("sync_wrapper image guard topilmadi.")
sync_source = sync_source.replace(old_image_guard, new_image_guard, 1)

# Ilovada muqova URL o‘zgarsa, oldingi Telegram cache lokalda eskirgan deb
# belgilanadi. Yangi file_id faqat mijoz shu kitobni ochganda yaratiladi.
old_row_start = '''    current = dict(current or {})
    current.update(
        {
'''
new_row_start = '''    current = dict(current or {})
    new_image_url = str(row.get("image_url") or "")
    cloud_photo_id = str(row.get("telegram_photo_id") or "")
    old_image_url = str(current.get("image_url") or "")
    old_photo_id = str(current.get("photo_id") or "")
    stale_cached_photo = (
        bool(old_image_url)
        and old_image_url != new_image_url
        and bool(old_photo_id)
        and cloud_photo_id == old_photo_id
    )
    resolved_photo_id = "" if stale_cached_photo else cloud_photo_id
    source_url = str(current.get("telegram_photo_source_url") or "")
    if stale_cached_photo:
        source_url = ""
    elif resolved_photo_id and new_image_url and not source_url:
        source_url = new_image_url

    current.update(
        {
'''
if old_row_start not in sync_source:
    raise RuntimeError("sync_wrapper _row_to_book start topilmadi.")
sync_source = sync_source.replace(old_row_start, new_row_start, 1)

old_row_images = '''            "image_url": str(row.get("image_url") or ""),
            "photo_id": str(row.get("telegram_photo_id") or ""),
'''
new_row_images = '''            "image_url": new_image_url,
            "photo_id": resolved_photo_id,
            "telegram_photo_source_url": source_url,
'''
if old_row_images not in sync_source:
    raise RuntimeError("sync_wrapper image fields topilmadi.")
sync_source = sync_source.replace(old_row_images, new_row_images, 1)

# Supabase egressni keskin kamaytirish uchun:
# - birinchi ishga tushishda va har soatda to‘liq reconcile;
# - qolgan vaqtda faqat o‘zgargan kitob/buyurtma/tombstone qatorlarini olish.
# Sinxron oralig‘i 60 soniya bo‘lib qoladi, funksiyalar kamaymaydi.
sync_loop_start = sync_source.find("def sync_loop():")
sync_loop_end = sync_source.find("\n\nif SUPABASE_URL and SUPABASE_ANON_KEY and SYNC_SECRET:", sync_loop_start)
if sync_loop_start < 0 or sync_loop_end < 0:
    raise RuntimeError("sync_wrapper.py ichidagi sync_loop bloki topilmadi.")

optimized_sync_loop = r'''
def _pull_books_delta(since):
    rows = _rpc("bot_sync_pull_delta", {"p_secret": SYNC_SECRET, "p_since": since})
    return rows if isinstance(rows, list) else []


def _pull_tombstones_delta(since):
    rows = _rpc("bot_sync_tombstones_pull_delta", {"p_secret": SYNC_SECRET, "p_since": since})
    return rows if isinstance(rows, list) else []


def _pull_orders_delta(since):
    rows = _rpc("bot_order_sync_pull_delta", {"p_secret": SYNC_SECRET, "p_since": since})
    return rows if isinstance(rows, list) else []


def _merge_books_delta(local, rows):
    by_id = {}
    by_cloud = {}
    by_title = {}
    used = set()

    for book in local or []:
        if not isinstance(book, dict):
            continue
        try:
            tid = int(book.get("id") or 0)
        except Exception:
            tid = 0
        if tid <= 0:
            continue
        copy = dict(book)
        by_id[tid] = copy
        used.add(tid)
        cloud_id = str(copy.get("cloud_id") or "").strip()
        if cloud_id:
            by_cloud[cloud_id] = copy
        by_title.setdefault(_norm_title(copy.get("name")), []).append(copy)

    next_id = max(used, default=0) + 1
    unmapped = set()

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        cloud_id = str(row.get("id") or "").strip()
        try:
            tid = int(row.get("telegram_id") or 0)
        except Exception:
            tid = 0

        current = None
        if tid > 0:
            current = by_id.get(tid)
        if current is None and cloud_id:
            current = by_cloud.get(cloud_id)
            if current is not None:
                try:
                    tid = int(current.get("id") or 0)
                except Exception:
                    tid = 0

        if tid <= 0:
            candidates = [
                b for b in by_title.get(_norm_title(row.get("title")), [])
                if int(b.get("id") or 0) not in used
            ]
            if len(candidates) == 1:
                current = candidates[0]
                tid = int(current.get("id") or 0)
            else:
                while next_id in used:
                    next_id += 1
                tid = next_id
                next_id += 1
            if cloud_id:
                unmapped.add(cloud_id)

        used.add(tid)
        updated = _row_to_book(row, current or {}, tid)
        by_id[tid] = updated
        if cloud_id:
            by_cloud[cloud_id] = updated

    out = sorted(by_id.values(), key=lambda x: int(x.get("id") or 0))
    return out, unmapped


def _local_books_by_uuid(local):
    out = {}
    for book in local or []:
        if not isinstance(book, dict):
            continue
        cloud_id = str(book.get("cloud_id") or "").strip()
        if not cloud_id:
            continue
        out[cloud_id] = {
            "telegram_id": book.get("id"),
            "title": book.get("name"),
            "cost_price": book.get("cost_price"),
        }
    return out


def sync_loop():
    initialized = False
    last_local_books = []
    last_book_fingerprints = {}
    book_cursor = "1970-01-01T00:00:00+00:00"
    order_cursor = "1970-01-01T00:00:00+00:00"
    tomb_cursor = "1970-01-01T00:00:00+00:00"
    last_full_reconcile = 0.0
    full_reconcile_every = 60 * 60

    while True:
        try:
            now_ts = time.time()
            cycle_cursor = datetime.fromtimestamp(
                max(0, now_ts - 15), timezone.utc
            ).isoformat()
            full_reconcile = (
                (not initialized)
                or (now_ts - last_full_reconcile >= full_reconcile_every)
            )

            local = _read_books()

            tombstones = (
                _pull_tombstones()
                if full_reconcile
                else _pull_tombstones_delta(tomb_cursor)
            )
            local, removed_stale = _remove_tombstoned_local(local, tombstones)
            if removed_stale:
                _write_json(BOOKS_FILE, local)
                print(
                    "Tombstone bo‘yicha lokal katalog tozalandi:",
                    ", ".join(str(b.get("name") or b.get("id")) for b in removed_stale),
                )

            if initialized and _prepare_bot_image_changes(local, last_local_books):
                _write_json(BOOKS_FILE, local)

            books_pushed = False
            if not initialized:
                unsynced = [
                    b for b in local
                    if isinstance(b, dict)
                    and not str(b.get("cloud_id") or "").strip()
                ]
                if unsynced:
                    _push_books(unsynced)
                    books_pushed = True
            else:
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
                    books_pushed = True

            if full_reconcile or books_pushed:
                rows = _pull_books()
                merged, unmapped = _merge_books(local, rows)
                if unmapped:
                    _push_unmapped_books(merged, unmapped)
                    rows = _pull_books()
                    merged, _ = _merge_books(merged, rows)
            else:
                rows = _pull_books_delta(book_cursor)
                merged, unmapped = _merge_books_delta(local, rows)
                if unmapped:
                    _push_unmapped_books(merged, unmapped)

            latest_local = _read_books()
            if _hash(latest_local) == _hash(local):
                if _hash(merged) != _hash(latest_local):
                    _notify_restock_transitions(latest_local, merged)
                    _write_json(BOOKS_FILE, merged)
                local = merged
            else:
                local = latest_local

            last_local_books = [
                dict(b) for b in local if isinstance(b, dict)
            ]
            last_book_fingerprints = {
                int(b.get("id")): _book_fingerprint(b)
                for b in local
                if isinstance(b, dict) and str(b.get("id") or "").isdigit()
            }

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
                    original_source = str(order.get("source") or "telegram")
                    result = _rpc("bot_order_create", {
                        "p_secret": SYNC_SECRET,
                        "p_order": order,
                        "p_preserve_stock": True,
                    })
                    if isinstance(result, dict) and result.get("id"):
                        cloud_id = str(result.get("id"))
                        order["cloud_order_id"] = cloud_id
                        if original_source == "instagram":
                            try:
                                _rpc("bot_mark_instagram_order", {
                                    "p_secret": SYNC_SECRET,
                                    "p_cloud_id": cloud_id,
                                })
                            except Exception as e:
                                print(f"Instagram source sync xatosi ({key}):", e)
                            order["source"] = "instagram"
                        else:
                            order["source"] = "telegram"
                        local_orders[str(key)] = order
                        orders_changed = True
                except Exception as e:
                    print(
                        f"Telegram/Instagram buyurtmasini cloudga retry xatosi ({key}):",
                        e,
                    )

            if orders_changed:
                _write_json(ORDERS_FILE, local_orders)

            cloud_orders = (
                _pull_orders()
                if full_reconcile
                else _pull_orders_delta(order_cursor)
            )
            books_by_uuid = _local_books_by_uuid(local)

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

                merged_order = _cloud_order_to_bot(
                    row, books_by_uuid, latest_orders.get(key)
                )
                if merged_order is None:
                    continue

                merged_orders[key] = merged_order
                cloud_id = str(row.get("id") or "")
                if (
                    key not in latest_orders
                    and cloud_id
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

            book_cursor = cycle_cursor
            order_cursor = cycle_cursor
            tomb_cursor = cycle_cursor
            if full_reconcile:
                last_full_reconcile = time.time()
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

sync_source = (
    sync_source[:sync_loop_start]
    + optimized_sync_loop
    + sync_source[sync_loop_end:]
)

sync_target = 'runpy.run_path("bot.py", run_name="__main__")'
if sync_target not in sync_source:
    raise RuntimeError("sync_wrapper.py ichidagi bot start qatori topilmadi.")

sync_source = sync_source.replace(sync_target, "run_bot_patched()", 1)

sync_namespace = {
    "__name__": "__main__",
    "__file__": "sync_wrapper.py",
    "run_bot_patched": run_bot_patched,
}
exec(compile(sync_source, "sync_wrapper.py", "exec"), sync_namespace, sync_namespace)