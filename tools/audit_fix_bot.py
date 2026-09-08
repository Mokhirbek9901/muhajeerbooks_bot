from pathlib import Path
import re

RESET_ORDER_ID = 1788893918395


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def replace_all_required(text, old, new, label, minimum=1):
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{label}: expected >= {minimum}, found {count}")
    return text.replace(old, new)


# ---------------------------------------------------------------------------
# bot.py — reset test history, make Jo'natildi the only sale, repair ratings,
# and make Instagram stock/accounting validation atomic from the bot's side.
# ---------------------------------------------------------------------------
bot_path = Path('bot.py')
b = bot_path.read_text(encoding='utf-8')

b = re.sub(
    r"STATS_RESET_ORDER_ID\s*=\s*\d+[^\n]*",
    f"STATS_RESET_ORDER_ID = {RESET_ORDER_ID}  # 2026-09-08 final production reset",
    b,
    count=1,
)

b = replace_once(
    b,
    'ORDER_HISTORY_RESET_MARKER = os.path.join(DATA_DIR, "order_history_reset_20260908_v1.done")',
    'ORDER_HISTORY_RESET_MARKER = os.path.join(DATA_DIR, "order_history_reset_20260908_v2.done")',
    'order reset marker v2',
)

b = replace_once(
    b,
    '    os.replace(tmp_orders, ORDERS_FILE)\n    marker_tmp = ORDER_HISTORY_RESET_MARKER + ".tmp"',
    '    os.replace(tmp_orders, ORDERS_FILE)\n'
    '    tmp_ratings = RATINGS_FILE + ".history_reset.tmp"\n'
    '    with open(tmp_ratings, "w", encoding="utf-8") as f:\n'
    '        json.dump({}, f, ensure_ascii=False, indent=2)\n'
    '        f.flush()\n'
    '        os.fsync(f.fileno())\n'
    '    os.replace(tmp_ratings, RATINGS_FILE)\n'
    '    marker_tmp = ORDER_HISTORY_RESET_MARKER + ".tmp"',
    'clear ratings with order reset',
)

# Old backups must never resurrect pre-reset test orders/ratings.
old_restore = '''    if is_data or is_legacy:
        load_expenses()
        payloads.update({
            ORDERS_FILE: data.get("orders", {}),
            USERS_FILE: data.get("users", {}),
            FAVORITES_FILE: data.get("favorites", {}),
            RATINGS_FILE: data.get("ratings", {}),
            RESTOCK_FILE: data.get("restock_subscribers", {}),
            EXPENSES_FILE: data.get("expenses", expenses),
        })'''
new_restore = '''    if is_data or is_legacy:
        load_expenses()
        raw_orders = data.get("orders", {})
        if not isinstance(raw_orders, dict):
            raw_orders = {}
        restored_orders = {}
        for key, value in raw_orders.items():
            if not isinstance(value, dict):
                continue
            try:
                oid = int(value.get("order_id", key) or 0)
            except Exception:
                oid = 0
            if oid >= STATS_RESET_ORDER_ID:
                restored_orders[str(key)] = value
        raw_ratings = data.get("ratings", {})
        if not isinstance(raw_ratings, dict):
            raw_ratings = {}
        restored_order_ids = {
            str(v.get("order_id", k)) for k, v in restored_orders.items()
            if isinstance(v, dict)
        }
        restored_ratings = {
            str(k): v for k, v in raw_ratings.items()
            if str(k) in restored_order_ids
        }
        payloads.update({
            ORDERS_FILE: restored_orders,
            USERS_FILE: data.get("users", {}),
            FAVORITES_FILE: data.get("favorites", {}),
            RATINGS_FILE: restored_ratings,
            RESTOCK_FILE: data.get("restock_subscribers", {}),
            EXPENSES_FILE: data.get("expenses", expenses),
        })'''
b = replace_once(b, old_restore, new_restore, 'backup reset boundary')

# Only current final stage is a sale. Legacy delivered is display-compatible only.
b = replace_once(
    b,
    'if o.get("status") in ("shipped", "delivered"):',
    'if o.get("status") == "shipped":',
    'best sellers shipped only',
)
b = replace_once(
    b,
    'if dt.date()==now.date() and o.get("status") in ("paid","shipped","delivered"): successful.append(o)',
    'if dt.date()==now.date() and o.get("status") == "shipped": successful.append(o)',
    'daily report shipped only',
)
b = replace_once(
    b,
    '    paid_statuses = ("shipped", "delivered")',
    '    paid_statuses = ("shipped",)',
    'admin report shipped only',
)
b = replace_once(
    b,
    '        if str(order.get("status") or "") not in ("shipped", "delivered"):',
    '        if str(order.get("status") or "") != "shipped":',
    'local sold rows shipped only',
)

# Accepted status must render normally in customer history.
old_status_block = '''    status_names = {
        "pending": "🟡 To‘lov kutilmoqda",
        "paid": "🟢 To‘lov tasdiqlangan",'''
new_status_block = '''    status_names = {
        "pending": "🟡 To‘lov kutilmoqda",
        "accepted": "📦 Buyurtma qabul qilingan",
        "paid": "🟢 To‘lov tasdiqlangan",'''
b = replace_once(b, old_status_block, new_status_block, 'accepted customer status label')

# Since Jo'natildi is final, ratings must unlock there, not at removed Yetkazildi stage.
b = replace_once(
    b,
    '        if o.get("status") == "delivered":\n            for bid, qty in o.get("cart", {}).items():',
    '        if o.get("status") == "shipped":\n            for bid, qty in o.get("cart", {}).items():',
    'rating keyboard final stage',
)
b = replace_all_required(
    b,
    'order.get("status") != "delivered"',
    'order.get("status") != "shipped"',
    'rating validation final stage',
    minimum=2,
)

# Replace Instagram sale function as one unit. All validation happens before any
# stock mutation; book revenue subtracts delivery only when customer paid it.
start = b.find('def save_instagram_sale(state):')
end = b.find('\ndef _sold_book_date(raw):', start)
if start < 0 or end < 0:
    raise SystemExit('Instagram sale function boundaries not found')
new_instagram = '''def save_instagram_sale(state):
    refresh_books()
    cart = {str(k): int(v) for k, v in state.get("cart", {}).items()}
    if not cart:
        raise ValueError("Kitoblar tanlanmagan.")

    received_total = int(state.get("received_total", 0) or 0)
    if received_total <= 0:
        raise ValueError("Mijozdan olingan jami summa kiritilmagan.")

    customer_pays_postage = bool(state.get("customer_pays_postage", False))
    delivery_fee = int(DELIVERY_FEE) if customer_pays_postage else 0
    if customer_pays_postage and received_total < delivery_fee:
        raise ValueError("Jami summa pochta pulidan kam bo‘lishi mumkin emas.")

    # Admin pochta to'lasa, mijozdan olingan summa to'liq kitob savdosi.
    # Mijoz pochta to'lasa, faqat o'sha 4,000 won ajratiladi.
    books_total = max(0, received_total - delivery_fee)
    grand_total = received_total

    by_id = {str(b.get("id")): b for b in books}
    for bid, qty in cart.items():
        if qty <= 0:
            raise ValueError("Kitob soni noto‘g‘ri.")
        book = by_id.get(str(bid))
        if not book:
            raise ValueError(f"Kitob topilmadi: ID {bid}")
        if int(book.get("stock", 0)) < int(qty):
            raise ValueError(
                f"{book.get('name')} omborda yetarli emas. "
                f"Hozir {int(book.get('stock', 0))} ta."
            )

    items = []
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        items.append({
            "book_id": str(bid),
            "name": str(book.get("name", "Kitob")),
            "qty": int(qty),
            "unit_price": int(effective_price(book)),
            "unit_cost": int(book.get("cost_price", 0) or 0),
        })

    order_id = str(int(time.time() * 1000))
    while order_id in orders or int(order_id) < STATS_RESET_ORDER_ID:
        time.sleep(0.001)
        order_id = str(int(time.time() * 1000))

    order = {
        "order_id": order_id,
        "chat_id": 0,
        "username": "",
        "name": "Instagram savdo",
        "phone": "",
        "address": "Instagram",
        "cart": cart,
        "items": items,
        "total": int(books_total),
        "delivery_fee": int(delivery_fee),
        "grand_total": int(grand_total),
        "discount": 0,
        "status": "shipped",
        "payment_declared": True,
        "receipt_file_id": "",
        "source": "instagram",
        "instagram_received_total": int(received_total),
        "postage_paid_by": "customer" if customer_pays_postage else "admin",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    # Faqat HAMMA tekshiruvdan o'tgandan keyin qoldiq bir marta kamayadi.
    for bid, qty in cart.items():
        book = by_id[str(bid)]
        book["stock"] = int(book.get("stock", 0)) - int(qty)
    save_books()

    orders[order_id] = order
    save_orders()

    # Markaziy bazaga yozish muvaffaqiyatsiz bo'lsa local savdo saqlanib qoladi;
    # sync_wrapper keyingi siklda aynan shu order_id bilan qayta urinadi.
    try:
        cloud_result = cloud_bridge.create_order(order, preserve_stock=True)
        if isinstance(cloud_result, dict) and cloud_result.get("id"):
            cloud_id = str(cloud_result["id"])
            order["cloud_order_id"] = cloud_id
            orders[order_id] = order
            save_orders()
            try:
                cloud_bridge.mark_instagram_order(cloud_id)
            except Exception as mark_error:
                print("Instagram source belgilash xatosi:", mark_error)
    except Exception as e:
        print("Instagram savdoni Supabase'ga yozish xatosi:", e)

    return order
'''
b = b[:start] + new_instagram + b[end:]

bot_path.write_text(b, encoding='utf-8')


# ---------------------------------------------------------------------------
# sync_wrapper.py — clear old local test orders BEFORE sync thread starts.
# This prevents a Railway volume from re-uploading old tests after DB reset.
# ---------------------------------------------------------------------------
sync_path = Path('sync_wrapper.py')
s = sync_path.read_text(encoding='utf-8')

s = replace_once(
    s,
    'ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")\nSYNC_INTERVAL = 2',
    'ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")\n'
    'RATINGS_FILE = os.path.join(DATA_DIR, "ratings.json")\n'
    'ORDER_RESET_MARKER = os.path.join(DATA_DIR, "order_history_reset_20260908_v2.done")\n'
    'SYNC_INTERVAL = 2',
    'sync reset constants',
)

anchor = '''def _catalog_reset_once():
    """User so'ragan bir martalik to'liq katalog reset: cloud + Railway volume."""'''
if anchor not in s:
    raise SystemExit('catalog reset anchor not found')
reset_func = '''def _order_reset_once():
    """Production reset: old test orders/ratings cannot re-enter cloud on restart."""
    if os.path.exists(ORDER_RESET_MARKER):
        return
    _write_json(ORDERS_FILE, {})
    _write_json(RATINGS_FILE, {})
    tmp = ORDER_RESET_MARKER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"reset_order_id": %d, "at": datetime.now(timezone.utc).isoformat()}))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ORDER_RESET_MARKER)
    print("ORDER_HISTORY_RESET_20260908_V2: local orders and ratings cleared")


''' % RESET_ORDER_ID
s = s.replace(anchor, reset_func + anchor, 1)

s = replace_once(
    s,
    '    _catalog_reset_once()\n    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()',
    '    _order_reset_once()\n'
    '    _catalog_reset_once()\n'
    '    threading.Thread(target=sync_loop, daemon=True, name="supabase-live-sync").start()',
    'reset before sync thread',
)

sync_path.write_text(s, encoding='utf-8')
print('Final bot hardening prepared: reset boundary, shipped-only accounting, ratings, Instagram safety.')
