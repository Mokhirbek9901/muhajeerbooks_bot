from pathlib import Path

path = Path('bot.py')
s = path.read_text(encoding='utf-8')


def replace_function(name, next_name, body):
    global s
    start = s.find(f'def {name}(')
    if start < 0:
        raise RuntimeError(f'{name} not found')
    end = s.find(f'def {next_name}(', start)
    if end < 0:
        raise RuntimeError(f'{next_name} not found after {name}')
    s = s[:start] + body.rstrip() + '\n\n\n' + s[end:]

replace_function('shipping_queue_entries', 'shipping_queue_menu', r'''def shipping_queue_entries(source_filter="all"):
    rows = cloud_bridge.shipping_queue_list()
    entries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "")
        if source_filter not in ("all", source):
            continue
        entry = dict(row)
        entry["queue_kind"] = str(entry.get("queue_kind") or ("manual" if source == "manual" else "order"))
        entry["queue_id"] = str(entry.get("queue_id") or "")
        entry["name"] = str(entry.get("name") or "Noma’lum")
        entry["phone"] = str(entry.get("phone") or "—")
        entry["address"] = str(entry.get("address") or "—")
        entry["books"] = str(entry.get("books") or "• Kitob ma’lumoti yo‘q")
        entry["address_photo_file_id"] = str(entry.get("address_photo_file_id") or "")
        entries.append(entry)
    return entries''')

replace_function('save_manual_shipping_order', 'delete_shipping_queue_entry', r'''def save_manual_shipping_order(state):
    result = cloud_bridge.shipping_queue_add(
        state.get("name"),
        state.get("phone"),
        state.get("address"),
        state.get("books"),
        state.get("address_photo_file_id", ""),
    )
    if not isinstance(result, dict):
        raise RuntimeError("Zakas serverga saqlanmadi")
    return result''')

# delete function ends at MENYULAR marker, so replace manually.
start = s.find('def delete_shipping_queue_entry(')
end = s.find('# =========================\n# MENYULAR', start)
if start < 0 or end < 0:
    raise RuntimeError('delete_shipping_queue_entry markers not found')
s = s[:start] + r'''def delete_shipping_queue_entry(kind, queue_id):
    return bool(cloud_bridge.shipping_queue_dismiss(kind, queue_id))


''' + s[end:]

path.write_text(s, encoding='utf-8')
print('shared cloud shipping queue patch applied')
