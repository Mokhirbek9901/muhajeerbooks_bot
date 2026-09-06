from pathlib import Path
p=Path('bot.py'); t=p.read_text(encoding='utf-8')
old='''            [{"text": "⚡ Tezkor qoldiq"}],\n            [discount_button],\n            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],\n            [{"text": "📅 Bugungi hisobot"}],\n            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],\n            [{"text": "🧪 Random xabarni sinash"}],\n            [{"text": "💾 Backup"}, {"text": "📥 Backup tiklash"}],\n            [{"text": "🏠 Asosiy menyu"}],'''
new='''            [{"text": "⚡ Tezkor qoldiq"}],\n            [{"text": "📊 Hisobot"}, {"text": "📦 Buyurtmalar"}],\n            [{"text": "📅 Bugungi hisobot"}],\n            [{"text": "👥 Foydalanuvchilar"}, {"text": "📢 Xabar yuborish"}],\n            [{"text": "🧪 Random xabarni sinash"}],\n            [{"text": "💾 Backup"}, {"text": "📥 Backup tiklash"}],\n            [discount_button],\n            [{"text": "🏠 Asosiy menyu"}],'''
if old not in t: raise RuntimeError('admin menu block not found')
p.write_text(t.replace(old,new,1),encoding='utf-8')
