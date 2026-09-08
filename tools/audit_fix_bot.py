from pathlib import Path


def replace(text, old, new, label, minimum=1):
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{label}: expected >= {minimum}, found {count}")
    return text.replace(old, new)

bot_path = Path('bot.py')
b = bot_path.read_text(encoding='utf-8')

# Never resurrect historical starter/import books on a fresh Railway volume.
b = replace(
    b,
    "books = [dict(b) for b in DEFAULT_BOOKS]",
    "books = []",
    'disable default catalog seeding',
)
b = replace(
    b,
    "if not os.path.exists(BOOK_IMPORT_MARKER):",
    "if False and not os.path.exists(BOOK_IMPORT_MARKER):",
    'disable 2026-09-06 legacy import',
)

# A sale becomes real only after Jo‘natildi. delivered is legacy-compatible only.
b = replace(
    b,
    'in ("paid", "shipped", "delivered")',
    'in ("shipped", "delivered")',
    'remove paid from sales stats',
)
b = replace(
    b,
    'in ("accepted", "paid", "shipped", "delivered")',
    'in ("shipped", "delivered")',
    'remove accepted/paid from sold history',
)

# No separate Yetkazildi stage in UI; old backups still render as final Jo‘natildi.
b = replace(
    b,
    '"delivered": "✅ Yetkazildi"',
    '"delivered": "🚚 Jo‘natildi"',
    'legacy delivered customer label',
)
b = replace(
    b,
    '"delivered": "✅ Yetkazilgan"',
    '"delivered": "🚚 Jo‘natilgan"',
    'legacy delivered admin label',
)

bot_path.write_text(b, encoding='utf-8')

sync_path = Path('sync_wrapper.py')
s = sync_path.read_text(encoding='utf-8')

# Legacy cloud `done` is the same final shipping stage.
s = replace(
    s,
    '"done": "delivered",',
    '"done": "shipped",',
    'legacy done cloud mapping',
)

# If the bot restarts while an app order arrives, notify admin once as long as
# that order was not already persisted in orders.json. This avoids restart misses
# without spamming old app orders.
old_condition = '''                if (
                    initialized and cloud_id and cloud_id not in seen_order_ids
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(merged_order)'''
new_condition = '''                if (
                    key not in latest_orders
                    and cloud_id
                    and str(row.get("source") or "app") == "app"
                ):
                    new_app_orders.append(merged_order)'''
if old_condition not in s:
    raise SystemExit('restart-safe app notification condition not found')
s = s.replace(old_condition, new_condition, 1)

sync_path.write_text(s, encoding='utf-8')
print('Bot audit fixes applied: no stale seeds, shipped-only sales, restart-safe app notifications.')
