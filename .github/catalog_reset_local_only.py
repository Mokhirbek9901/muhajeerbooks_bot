from pathlib import Path
p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')
old = '    result = _rpc("bot_catalog_reset", {"p_secret": SYNC_SECRET})\n    _write_json(BOOKS_FILE, [])\n'
new = '    result = {"ok": True, "database_reset": "done_by_admin_sql"}\n    _write_json(BOOKS_FILE, [])\n'
if old not in s:
    if 'database_reset": "done_by_admin_sql"' in s:
        raise SystemExit(0)
    raise SystemExit('catalog reset rpc line not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
