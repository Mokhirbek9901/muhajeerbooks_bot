from pathlib import Path

p = Path("bot.py")
text = p.read_text(encoding="utf-8")
old = '''        with open(ORDERS_FILE, "r", encoding="utf-8") as f:\n            orders = json.load(f)\n'''
new = '''        with open(ORDERS_FILE, "r", encoding="utf-8") as f:\n            orders = json.load(f)\n        if orders.pop("1789499997196", None) is not None:\n            save_orders()\n'''
if new in text:
    raise SystemExit(0)
if old not in text:
    raise SystemExit("load_orders marker not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
