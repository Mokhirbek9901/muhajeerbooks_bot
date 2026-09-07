from pathlib import Path

path = Path('bot.py')
text = path.read_text(encoding='utf-8')

if 'def _local_datetime(' not in text:
    anchor = 'from datetime import datetime, timedelta\n'
    helper = '''\n\ndef _local_datetime(raw):\n    \"\"\"ISO vaqtni timezone aralashmasidan xoli, taqqoslanadigan local datetimega aylantiradi.\"\"\"\n    value = str(raw or '').strip()\n    if value.endswith('Z'):\n        value = value[:-1] + '+00:00'\n    dt = datetime.fromisoformat(value)\n    if dt.tzinfo is not None:\n        dt = dt.astimezone().replace(tzinfo=None)\n    return dt\n'''
    if anchor not in text:
        raise SystemExit('datetime import anchor topilmadi')
    text = text.replace(anchor, anchor + helper, 1)

# Barcha created_at ISO parse joylarini bir xil timezone siyosatiga o'tkazamiz.
text = text.replace('datetime.fromisoformat(', '_local_datetime(')
# Helper ichidagi chaqiruv rekursiv bo'lib qolmasin.
text = text.replace("dt = _local_datetime(value)\n    if dt.tzinfo is not None:", "dt = datetime.fromisoformat(value)\n    if dt.tzinfo is not None:", 1)

path.write_text(text, encoding='utf-8')
print('datetime compatibility patch applied')
