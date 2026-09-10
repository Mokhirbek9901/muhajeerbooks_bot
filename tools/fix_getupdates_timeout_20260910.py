from pathlib import Path

path = Path('bot.py')
text = path.read_text(encoding='utf-8')
old = '''    try:\n        with urllib.request.urlopen(req, timeout=40) as response:\n            raw = response.read().decode("utf-8", errors="replace")\n            return json.loads(raw) if raw else {}\n'''
new = '''    try:\n        http_timeout = 65 if method == "getUpdates" else 40\n        with urllib.request.urlopen(req, timeout=http_timeout) as response:\n            raw = response.read().decode("utf-8", errors="replace")\n            return json.loads(raw) if raw else {}\n'''
if old not in text:
    if 'http_timeout = 65 if method == "getUpdates" else 40' in text:
        print('Already fixed')
    else:
        raise SystemExit('Expected Telegram api() timeout block not found')
else:
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('Patched getUpdates HTTP timeout')
