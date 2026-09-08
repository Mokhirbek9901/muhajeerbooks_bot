from pathlib import Path

p = Path('sync_wrapper.py')
s = p.read_text(encoding='utf-8')
s = s.replace('from datetime import datetime\n', 'from datetime import datetime, timezone\n', 1)
old = '''def _parse_iso(value):
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None
'''
new = '''def _parse_iso(value):
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
'''
if old in s:
    s = s.replace(old, new, 1)
elif 'dt = dt.replace(tzinfo=timezone.utc)' not in s:
    raise SystemExit('_parse_iso pattern not found')
p.write_text(s, encoding='utf-8')
