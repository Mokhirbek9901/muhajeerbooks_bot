from pathlib import Path
import re

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

old = '''def _instagram_fuzzy_matches(query):
    """Return one confident book, or several near-equal candidates if ambiguous."""
    q = _search_key(query)
    if not q:
        return []

    # First preserve useful partial-name behavior.
    contains = []
    for b in books:
        name_key = _search_key(b.get("name", ""))
        if q and (q in name_key or (len(name_key) >= 4 and name_key in q)):
            contains.append(b)
    if len(contains) == 1:
        return contains
    if len(contains) > 1:
        return contains[:4]

    scored = []
    for b in books:
        score = _fuzzy_ratio(q, b.get("name", ""))
        scored.append((score, b))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return []

    threshold = _fuzzy_threshold(q)
    best = scored[0][0]
    if best < threshold:
        return []

    # If two names are almost equally likely, don't silently choose the wrong stock item.
    close = [b for score, b in scored if score >= threshold and score >= best - 0.045]
    return close[:4]
'''
new = '''def _instagram_fuzzy_matches(query):
    """Instagram savdoda qisqa yoki biroz xato nomdan eng yaqin bitta kitobni tanlaydi."""
    q = _search_key(query)
    if not q:
        return []

    scored = []
    for b in books:
        name_key = _search_key(b.get("name", ""))
        if not name_key:
            continue

        # Qisqa nomlar uchun boshidan mos kelish eng kuchli signal.
        # Masalan: "Yusuf" -> "Yusufning qizi".
        if name_key == q:
            score = 2.0
        elif name_key.startswith(q):
            score = 1.40 - min(0.20, max(0, len(name_key) - len(q)) * 0.004)
        elif q in name_key.split():
            score = 1.25 - min(0.15, max(0, len(name_key) - len(q)) * 0.003)
        elif q in name_key:
            score = 1.15 - min(0.20, max(0, len(name_key) - len(q)) * 0.003)
        elif len(name_key) >= 4 and name_key in q:
            score = 1.05
        else:
            score = _fuzzy_ratio(q, name_key)

        # Bir xil/yaqin nomli dublikatlarda omborda borini afzal ko‘ramiz.
        stock = int(b.get("stock", 0) or 0)
        stock_bonus = min(stock, 20) * 0.0005
        scored.append((score + stock_bonus, b))

    if not scored:
        return []

    scored.sort(key=lambda x: (x[0], int(x[1].get("stock", 0) or 0), -int(x[1].get("id", 0) or 0)), reverse=True)
    best_score, best_book = scored[0]

    # Juda qisqa yoki umuman aloqasiz matnni tasodifiy kitobga bog‘lamaymiz.
    if best_score < _fuzzy_threshold(q):
        return []

    return [best_book]
'''
if old not in t:
    raise RuntimeError('instagram fuzzy helper anchor not found')
t = t.replace(old, new, 1)

old2 = '''        matches = exact.get(qkey, [])
        if not matches:
            matches = _instagram_fuzzy_matches(query)

        if len(matches) != 1:
            if not matches:
                errors.append(f"• {query} — topilmadi")
            else:
                names = ", ".join(str(b.get("name", "")) for b in matches[:4])
                errors.append(f"• {query} — aniq emas: {names}")
            continue
'''
new2 = '''        matches = exact.get(qkey, [])
        if len(matches) > 1:
            # Bir xil nomli dublikat bo‘lsa, omborda ko‘proq qolgani olinadi.
            matches = [max(matches, key=lambda b: (int(b.get("stock", 0) or 0), -int(b.get("id", 0) or 0)))]
        if not matches:
            matches = _instagram_fuzzy_matches(query)

        if not matches:
            errors.append(f"• {query} — topilmadi")
            continue
'''
if old2 not in t:
    raise RuntimeError('instagram parser ambiguity anchor not found')
t = t.replace(old2, new2, 1)

# Error text should not imply the full name is required.
t = t.replace('Qaytadan yozing. Masalan:\\nDafina 1 10000', 'Qaytadan yozing. Masalan:\\nDafina 1', 1)

p.write_text(t, encoding='utf-8')
print('patched instagram short-name matching')
