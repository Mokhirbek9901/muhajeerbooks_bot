from pathlib import Path
import re

p = Path('bot.py')
t = p.read_text(encoding='utf-8')

# Standard-library fuzzy matcher only; no new dependency.
if 'from difflib import SequenceMatcher' not in t:
    anchor = 'from datetime import datetime, timedelta\n'
    if anchor not in t:
        raise RuntimeError('datetime import anchor not found')
    t = t.replace(anchor, anchor + 'from difflib import SequenceMatcher\n', 1)

# Shared normalization + fuzzy helpers. Replaces only the Instagram name normalizer.
pat = r'def _instagram_name_key\(value\):\n.*?(?=\ndef _instagram_qty_token\(token\):)'
helpers = '''def _search_key(value):
    """Search text: lowercase, emoji/punctuation ignored, Uzbek apostrophes ignored."""
    value = str(value or "").casefold()
    apostrophes = {"'", "’", "‘", "ʻ", "ʼ", "`", "´"}
    out = []
    for ch in value:
        if ch.isalnum():
            out.append(ch)
        elif ch in apostrophes:
            # o‘g‘irlangan -> ogirlangan, kambag‘al -> kambagal
            continue
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _fuzzy_threshold(value):
    n = len(str(value or "").replace(" ", ""))
    if n <= 3:
        return 0.86
    if n <= 5:
        return 0.74
    return 0.68


def _fuzzy_ratio(a, b):
    a = _search_key(a)
    b = _search_key(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 3 and a in b:
        return 0.98
    if len(b) >= 4 and b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def _instagram_name_key(value):
    return _search_key(value)


def _instagram_fuzzy_matches(query):
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
t2, n = re.subn(pat, lambda m: helpers, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f'Instagram normalizer block not found: {n}')
t = t2

# Customer/admin book search: exact/partial first, then typo-tolerant name/author matches.
pat = r'def search_books\(query\):\n.*?(?=\ndef search_books_keyboard\(items\):)'
search_fn = '''def search_books(query):
    refresh_books()
    q = _search_key(query)
    if not q:
        return []

    ranked = []
    threshold = _fuzzy_threshold(q)

    for b in books:
        name = _search_key(b.get("name", ""))
        author = _search_key(b.get("author", ""))
        category = _search_key(b.get("category", ""))

        # Exact/partial results always rank first.
        exact_score = 0.0
        for field in (name, author, category):
            if not field:
                continue
            if q == field:
                exact_score = max(exact_score, 1.0)
            elif len(q) >= 2 and q in field:
                exact_score = max(exact_score, 0.97)

        fuzzy_score = max(
            _fuzzy_ratio(q, name),
            _fuzzy_ratio(q, author) if author else 0.0,
        )
        score = max(exact_score, fuzzy_score)

        if exact_score > 0 or score >= threshold:
            ranked.append((score, b))

    ranked.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("name", "")).casefold()
        )
    )
    return [b for _, b in ranked[:30]]


'''
t2, n = re.subn(pat, lambda m: search_fn, t, count=1, flags=re.S)
if n != 1:
    raise RuntimeError(f'search_books block not found: {n}')
t = t2

# Instagram manual sale: after normalized exact lookup, use typo-tolerant book-name matching.
old = '''        query = " ".join(query_parts).strip()\n        qkey = _instagram_name_key(query)\n        matches = exact.get(qkey, [])\n        if not matches:\n            matches = [\n                b for b in books\n                if qkey and (\n                    qkey in _instagram_name_key(b.get("name", ""))\n                    or _instagram_name_key(b.get("name", "")) in qkey\n                )\n            ]\n\n        if len(matches) != 1:\n'''
new = '''        query = " ".join(query_parts).strip()\n        qkey = _instagram_name_key(query)\n        matches = exact.get(qkey, [])\n        if not matches:\n            matches = _instagram_fuzzy_matches(query)\n\n        if len(matches) != 1:\n'''
if old not in t:
    raise RuntimeError('Instagram match block not found')
t = t.replace(old, new, 1)

# Make customer search prompt mention typo tolerance without changing flow.
old_prompt = '"🔎 Kitob nomini yozing.\\nMasalan: Yovuz daho"'
new_prompt = '"🔎 Kitob nomini yozing.\\nMasalan: Yovuz daho\\n\\nBir-ikki harf xato bo‘lsa ham topishga harakat qilaman."'
if old_prompt in t:
    t = t.replace(old_prompt, new_prompt, 1)

p.write_text(t, encoding='utf-8')
print('Fuzzy book search enabled')
