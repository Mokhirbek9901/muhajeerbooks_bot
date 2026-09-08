from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')
old = '                new_id = max([int(b["id"]) for b in books], default=0) + 1\n'
new = '''                # O‘chirilgan kitob IDsi qayta ishlatilmasin. Timestamp-asosli ID\n                # eski tombstone bilan to‘qnashmaydi va cloud syncda kitob qayta tirilmaydi.\n                new_id = max(\n                    max([int(b["id"]) for b in books], default=0) + 1,\n                    int(time.time() * 1000),\n                )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'Timestamp-asosli ID' not in s:
    raise SystemExit('new_id pattern not found')
p.write_text(s, encoding='utf-8')
