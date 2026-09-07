from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

old_status = '''ORDER_STATUS_NAMES = {
    "pending": "🟡 Kutilmoqda", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "✅ Yetkazilgan",
    "cancelled": "❌ Bekor qilingan", "stock_problem": "⚠️ Ombor muammosi"
}'''
new_status = '''ORDER_STATUS_NAMES = {
    "pending": "🟡 Kutilmoqda", "accepted": "📦 Qabul qilingan", "paid": "🟢 To‘langan",
    "shipped": "🚚 Jo‘natilgan", "delivered": "✅ Yetkazilgan",
    "cancelled": "❌ Bekor qilingan", "stock_problem": "⚠️ Ombor muammosi"
}'''
if '"accepted": "📦 Qabul qilingan"' not in s:
    assert old_status in s, 'status map not found'
    s = s.replace(old_status, new_status, 1)

old_keyboard = '''def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "paid":
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}
'''
new_keyboard = '''def admin_order_status_keyboard(order_id, status):
    buttons=[]
    if status == "pending":
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
        buttons.append([{ "text":"❌ Bekor qilish", "callback_data":f"cancelorder_{order_id}" }])
    elif status == "accepted":
        # Programma adminida qabul qilingan buyurtmada ombor allaqachon rezerv qilingan.
        buttons.append([{ "text":"💳 To‘lov qilindi", "callback_data":f"paid_{order_id}" }])
    elif status == "paid":
        buttons.append([{ "text":"🚚 Jo‘natildi", "callback_data":f"ship_{order_id}" }])
    buttons.append([{ "text":"⬅️ Buyurtmalar", "callback_data":"admin_orders" }])
    return {"inline_keyboard":buttons}
'''
if 'elif status == "accepted":' not in s[s.index('def admin_order_status_keyboard'):s.index('def finalize_order')]:
    assert old_keyboard in s, 'admin order keyboard not found'
    s = s.replace(old_keyboard, new_keyboard, 1)

old_paid = '''        if order["status"] != "pending":
            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon qayta ishlangan."
            )
            return

        # Eng so‘nggi books.json ni bir marta yuklaymiz.
'''
new_paid = '''        if order["status"] not in ("pending", "accepted"):
            send(
                chat_id,
                "⚠️ Bu zakaz allaqachon qayta ishlangan."
            )
            return

        # Programma adminida qabul qilingan bo‘lsa, cloud ombor allaqachon kamaygan.
        # Shu sabab Telegramda yana ombor kamaytirilmaydi.
        if order["status"] == "accepted":
            order["status"] = "paid"
            save_orders()
            send(
                chat_id,
                f"✅ Zakaz №{order_id} to‘lov qilindi deb belgilandi.\n\n📦 Ombor avval rezerv qilingan.",
                admin_order_status_keyboard(order_id, "paid")
            )
            customer_chat = int(order.get("chat_id", 0) or 0)
            if customer_chat and customer_chat != int(chat_id):
                try:
                    send(
                        customer_chat,
                        "✅ BUYURTMANGIZ QABUL QILINDI!\n\n" + order_receipt_text(order) +
                        "\n\n📦 Kitoblaringiz pochtaga topshirilganda sizga alohida xabar yuboriladi.",
                        main_menu(customer_chat)
                    )
                except Exception as e:
                    print("Mijozga status yuborish xatosi:", e)
            return

        # Eng so‘nggi books.json ni bir marta yuklaymiz.
'''
if 'order["status"] not in ("pending", "accepted")' not in s:
    assert old_paid in s, 'paid handler guard not found'
    s = s.replace(old_paid, new_paid, 1)

p.write_text(s, encoding='utf-8')
