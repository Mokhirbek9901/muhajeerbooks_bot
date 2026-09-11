from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

# Imports needed for parsing and OCR.
if 'import re\n' not in s[:500]:
    s = s.replace('import io\n', 'import io\nimport re\nimport subprocess\n', 1)
elif 'import subprocess\n' not in s[:500]:
    s = s.replace('import re\n', 'import re\nimport subprocess\n', 1)

# Smart intake helpers.
marker = '\n\n# =========================\n# MENYULAR\n# =========================\n'
if 'def parse_smart_shipping_text(' not in s:
    helper = r'''


def _shipping_clean_line(value):
    return ' '.join(str(value or '').replace('\u200b', ' ').split()).strip()


def _shipping_phone_from_text(raw):
    raw = str(raw or '')
    patterns = [
        r'(?<!\d)(?:\+?82[-\s]?)?0?10[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)',
        r'(?<!\d)\+?\d[\d\s()\-]{7,18}\d(?!\d)',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw)
        if not m:
            continue
        value = m.group(0).strip()
        digits = ''.join(ch for ch in value if ch.isdigit())
        if 8 <= len(digits) <= 15:
            if value.startswith('+'):
                return '+' + digits
            return digits
    return ''


def _shipping_is_address_line(line):
    line = _shipping_clean_line(line)
    if not line:
        return False
    low = line.casefold()
    if any(key in low for key in ('manzil', 'address', '주소', '배송지', '받는 주소', '받는주소')):
        return True
    # Korean postal-address signals.
    if re.search(r'(특별시|광역시|특별자치시|특별자치도|[가-힣]+도|[가-힣]+시|[가-힣]+군|[가-힣]+구)', line):
        if re.search(r'(로|길|동|읍|면|리|번길|대로|\d+-\d+|\d+호)', line):
            return True
    if re.search(r'\b\d{5}\b', line) and re.search(r'[가-힣]', line):
        return True
    return False


def _shipping_extract_address(lines):
    labels = ('manzil', 'address', '주소', '배송지', '받는 주소', '받는주소')
    for i, raw in enumerate(lines):
        line = _shipping_clean_line(raw)
        low = line.casefold()
        if any(key in low for key in labels):
            value = re.sub(r'^(?:📍\s*)?(?:manzil|address|주소|배송지|받는\s*주소)\s*[:：\-]?\s*', '', line, flags=re.I).strip()
            parts = [value] if value else []
            for nxt in lines[i + 1:i + 3]:
                nxt = _shipping_clean_line(nxt)
                if not nxt or _shipping_phone_from_text(nxt):
                    break
                if _shipping_is_address_line(nxt) or re.search(r'(\d+호|층|동\s*\d+|\d+동|\d+[-–]\d+)', nxt):
                    parts.append(nxt)
                else:
                    break
            if parts:
                return ', '.join(parts)

    for i, raw in enumerate(lines):
        line = _shipping_clean_line(raw)
        if not _shipping_is_address_line(line):
            continue
        parts = [line]
        for nxt in lines[i + 1:i + 3]:
            nxt = _shipping_clean_line(nxt)
            if not nxt or _shipping_phone_from_text(nxt):
                break
            if _shipping_is_address_line(nxt) or re.search(r'(\d+호|층|\d+동|\d+[-–]\d+)', nxt):
                parts.append(nxt)
            else:
                break
        return ', '.join(parts)
    return ''


def _shipping_extract_name(lines, phone='', address=''):
    label_re = re.compile(r'^(?:👤\s*)?(?:ism|name|이름|성명|수취인|받는\s*분|받는\s*사람)\s*[:：\-]?\s*(.+)$', re.I)
    for raw in lines:
        line = _shipping_clean_line(raw)
        m = label_re.match(line)
        if m:
            value = _shipping_clean_line(m.group(1))
            if 1 < len(value) <= 80:
                return value

    # Common screenshot shape: name / phone / address on separate lines.
    for raw in lines:
        line = _shipping_clean_line(raw)
        if not line or len(line) > 60:
            continue
        low = line.casefold()
        if _shipping_phone_from_text(line) or _shipping_is_address_line(line):
            continue
        if address and line in address:
            continue
        if any(key in low for key in ('주문', '배송', '주소', '전화', 'phone', 'tel', 'mobile', 'order', 'manzil', 'kitob', 'book', '₩', '원')):
            continue
        if re.search(r'[A-Za-z가-힣А-Яа-яʻʼ’‘`\']', line):
            return line.strip(' -:：')
    return ''


def _shipping_qty_from_line(line, book_name):
    line = str(line or '')
    # Prefer quantity close to a book line; ignore prices/phones by capping at 99.
    candidates = []
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*(?:ta|dona|x|×)?(?!\d)', line, flags=re.I):
        try:
            value = int(m.group(1))
        except Exception:
            continue
        if 1 <= value <= 99:
            candidates.append(value)
    return candidates[-1] if candidates else 1


def _shipping_extract_books(lines, whole_text):
    refresh_books()
    found = {}
    whole_key = _search_key(whole_text)

    # High-confidence exact/substring matches first.
    for book in books:
        name = str(book.get('name') or '').strip()
        key = _search_key(name)
        if len(key.replace(' ', '')) < 4 or not key:
            continue
        match_line = ''
        for raw in lines:
            line_key = _search_key(raw)
            if key == line_key or key in line_key:
                match_line = str(raw)
                break
        if not match_line and key in whole_key:
            match_line = str(whole_text)
        if match_line:
            found[str(book.get('id'))] = {
                'name': name,
                'qty': _shipping_qty_from_line(match_line, name),
            }

    # If no exact title was present, try conservative fuzzy matching on short lines.
    if not found:
        for raw in lines:
            line = _shipping_clean_line(raw)
            if not line or len(line) > 90:
                continue
            if _shipping_phone_from_text(line) or _shipping_is_address_line(line):
                continue
            query = re.sub(r'(?<!\d)\d{1,2}\s*(?:ta|dona|x|×)?\s*$', '', line, flags=re.I).strip(' -:：•')
            if len(_search_key(query).replace(' ', '')) < 4:
                continue
            matches = _instagram_fuzzy_matches(query)
            if not matches:
                continue
            book = matches[0]
            if _fuzzy_ratio(query, book.get('name', '')) < 0.80:
                continue
            found[str(book.get('id'))] = {
                'name': str(book.get('name') or 'Kitob'),
                'qty': _shipping_qty_from_line(line, book.get('name', '')),
            }

    if not found:
        return ''
    return '\n'.join(f"• {item['name']} × {int(item['qty'])}" for item in found.values())


def parse_smart_shipping_text(raw):
    raw = str(raw or '').strip()
    lines = [_shipping_clean_line(x) for x in raw.splitlines() if _shipping_clean_line(x)]
    phone = _shipping_phone_from_text(raw)
    address = _shipping_extract_address(lines)
    name = _shipping_extract_name(lines, phone, address)
    book_text = _shipping_extract_books(lines, raw)
    return {
        'name': name,
        'phone': phone,
        'address': address,
        'books': book_text,
        'raw_text': raw,
    }


def _shipping_ocr_photo(file_id):
    tmp = os.path.join(DATA_DIR, f"shipping_ocr_{int(time.time() * 1000)}.jpg")
    try:
        download_telegram_file(file_id, tmp)
        last_error = ''
        for lang in ('kor+eng', 'eng'):
            try:
                result = subprocess.run(
                    ['tesseract', tmp, 'stdout', '-l', lang, '--psm', '6'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=30,
                    check=False,
                )
                text = str(result.stdout or '').strip()
                if text:
                    return text
                last_error = str(result.stderr or '').strip()
            except Exception as exc:
                last_error = str(exc)
        raise RuntimeError(last_error or 'Rasmdagi matn aniqlanmadi')
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def smart_shipping_preview(state):
    return (
        '📦 ZAKAS — TEKSHIRING\n\n'
        f"👤 Ism: {state.get('name') or '—'}\n"
        f"📞 Telefon: {state.get('phone') or '—'}\n"
        f"📍 Manzil: {state.get('address') or '—'}\n\n"
        '📚 Kitoblar:\n'
        f"{state.get('books') or '—'}"
    )


def smart_shipping_confirm_keyboard():
    return {'inline_keyboard': [
        [{'text': '✅ Saqlash', 'callback_data': 'shipsmart_save'}],
        [{'text': '❌ Bekor qilish', 'callback_data': 'shipsmart_cancel'}],
    ]}


def _smart_shipping_ask_next(chat_id, state):
    if not str(state.get('name') or '').strip():
        state['action'] = 'shipping_smart_missing_name'
        send(chat_id, '👤 Ismni topolmadim. Faqat mijoz ismini yozing:')
        return
    if not str(state.get('phone') or '').strip():
        state['action'] = 'shipping_smart_missing_phone'
        send(chat_id, '📞 Telefon raqamini topolmadim. Faqat raqamni yozing:')
        return
    if not str(state.get('address') or '').strip():
        state['action'] = 'shipping_smart_missing_address'
        send(chat_id, '📍 Manzilni topolmadim. Faqat to‘liq manzilni yozing:')
        return
    if not str(state.get('books') or '').strip():
        state['action'] = 'shipping_smart_missing_books'
        send(
            chat_id,
            '📚 Matn/rasm ichida kitob nomi yo‘q ekan.\n\n'
            'Faqat qaysi kitob(lar)ga zakas qilganini yozing.\n'
            'Masalan:\nDafina 1 ta\nSaodat asri 2 ta'
        )
        return
    state['action'] = 'shipping_smart_confirm'
    send(chat_id, smart_shipping_preview(state), smart_shipping_confirm_keyboard())


def _send_saved_shipping_entry(chat_id, entry):
    send(chat_id, '✅ Zakas Zakaslar bo‘limiga saqlandi.')
    photo_id = str(entry.get('address_photo_file_id') or '').strip()
    if photo_id:
        try:
            api('sendPhoto', {
                'chat_id': chat_id,
                'photo': photo_id,
                'caption': shipping_entry_text(entry),
                'reply_markup': json.dumps(shipping_entry_keyboard(entry), ensure_ascii=False),
            })
        except Exception:
            send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))
    else:
        send(chat_id, shipping_entry_text(entry), shipping_entry_keyboard(entry))
    send(chat_id, '📦 Zakaslar', shipping_queue_menu())
'''
    s = s.replace(marker, helper + marker, 1)

# Rename the add button while preserving compatibility with old Telegram keyboards.
s = s.replace('{"text": "➕ Qo‘lda zakas"}', '{"text": "➕ SMS / rasm"}')

# Replace the old step-by-step entry start.
start = '        if text == "➕ Qo‘lda zakas":\n'
end = '        if text == "📷 Instagram savdo":\n'
if start in s:
    a = s.index(start)
    b = s.index(end, a)
    new = '''        if text in ("➕ SMS / rasm", "➕ Qo‘lda zakas"):\n            states[chat_id] = {"action": "shipping_smart_input"}\n            send(\n                chat_id,\n                "📩 ZAKASNI TEZ KIRITISH\\n\\n"\n                "Instagram yoki boshqa joydan kelgan xabarni BUTUNLIGICHA yuboring.\\n"\n                "Yoki manzil/zakas screenshotini rasm qilib yuboring.\\n\\n"\n                "Men ism, telefon, manzil va kitoblarni o‘zim ajrataman. "\n                "Agar kitob nomi xabarda bo‘lmasa, faqat kitobni alohida so‘rayman.",\n                {"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}\n            )\n            return\n\n'''
    s = s[:a] + new + s[b:]

# Replace legacy manual field-by-field state handlers.
start = '            if action == "shipping_name":\n'
end = '            if action == "instagram_items":\n'
if start in s:
    a = s.index(start)
    b = s.index(end, a)
    new = '''            if action == "shipping_smart_input":\n                photos = message.get("photo") or []\n                caption = str(message.get("caption") or "").strip()\n                raw = text\n                photo_id = ""\n                if photos:\n                    photo_id = str(photos[-1].get("file_id") or "")\n                    try:\n                        ocr_text = _shipping_ocr_photo(photo_id)\n                    except Exception as exc:\n                        print("Zakas OCR xatosi:", exc)\n                        ocr_text = ""\n                    raw = "\\n".join(x for x in (ocr_text, caption) if x).strip()\n                    state["address_photo_file_id"] = photo_id\n                if not raw:\n                    send(chat_id, "❌ Matnni o‘qiy olmadim. Xabarni matn ko‘rinishida yuboring yoki tiniqroq screenshot yuboring.")\n                    return\n                parsed = parse_smart_shipping_text(raw)\n                for key in ("name", "phone", "address", "books", "raw_text"):\n                    if parsed.get(key):\n                        state[key] = parsed[key]\n                _smart_shipping_ask_next(chat_id, state)\n                return\n\n            if action == "shipping_smart_missing_name":\n                if not text:\n                    send(chat_id, "❌ Ismni yozing.")\n                    return\n                state["name"] = text.strip()\n                _smart_shipping_ask_next(chat_id, state)\n                return\n\n            if action == "shipping_smart_missing_phone":\n                phone = _shipping_phone_from_text(text)\n                if not phone:\n                    send(chat_id, "❌ Telefon raqamini to‘g‘ri yozing. Masalan: 01012345678")\n                    return\n                state["phone"] = phone\n                _smart_shipping_ask_next(chat_id, state)\n                return\n\n            if action == "shipping_smart_missing_address":\n                if not text:\n                    send(chat_id, "❌ To‘liq manzilni yozing.")\n                    return\n                state["address"] = text.strip()\n                _smart_shipping_ask_next(chat_id, state)\n                return\n\n            if action == "shipping_smart_missing_books":\n                if not text:\n                    send(chat_id, "❌ Kitob nomi va sonini yozing.")\n                    return\n                # Admin yozgan kitob nomini imkon qadar katalogdagi to‘liq nomga aylantiramiz.\n                parsed_books = _shipping_extract_books([text], text)\n                state["books"] = parsed_books or text.strip()\n                _smart_shipping_ask_next(chat_id, state)\n                return\n\n            if action == "shipping_smart_confirm":\n                send(chat_id, smart_shipping_preview(state), smart_shipping_confirm_keyboard())\n                return\n\n'''
    s = s[:a] + new + s[b:]

# Add save/cancel callbacks for smart intake.
cb_marker = '    if data.startswith("shipdel_"):\n'
if 'if data == "shipsmart_save":' not in s:
    cb = '''    if data == "shipsmart_save":\n        if not is_admin(chat_id):\n            return\n        state = states.get(chat_id, {})\n        if state.get("action") != "shipping_smart_confirm":\n            send(chat_id, "ℹ️ Saqlanadigan zakas topilmadi.", shipping_queue_menu())\n            return\n        try:\n            entry = save_manual_shipping_order(state)\n        except Exception as exc:\n            send(chat_id, f"❌ Zakas saqlanmadi: {exc}", shipping_queue_menu())\n            return\n        states.pop(chat_id, None)\n        _send_saved_shipping_entry(chat_id, entry)\n        return\n\n    if data == "shipsmart_cancel":\n        if is_admin(chat_id):\n            states.pop(chat_id, None)\n            send(chat_id, "❎ Zakas kiritish bekor qilindi.", shipping_queue_menu())\n        return\n\n'''
    s = s.replace(cb_marker, cb + cb_marker, 1)

# Keep old keyboard messages accepted, and allow the new button in admin whitelist.
if '            "➕ SMS / rasm",\n' not in s:
    s = s.replace('            "➕ Qo‘lda zakas",\n', '            "➕ Qo‘lda zakas",\n            "➕ SMS / rasm",\n', 1)

p.write_text(s, encoding='utf-8')
print('smart shipping intake patch applied')
