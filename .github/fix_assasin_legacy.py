from pathlib import Path

p = Path('bot.py')
s = p.read_text(encoding='utf-8')

start = '    # GitHub orqali qo‘shilgan kitob: mavjud bo‘lmasa bir marta omborga qo‘shiladi.\n'
end = '    for b in books:\n'

if start not in s:
    if 'ASSASIN_LEGACY_CLEANUP_20260908' in s:
        raise SystemExit(0)
    raise SystemExit('legacy Assasin block start not found')

pos1 = s.index(start)
pos2 = s.index(end, pos1)
replacement = '''    # ASSASIN_LEGACY_CLEANUP_20260908
    # Eski versiyada Assasin hardcoded tarzda har load_books() da qayta qo‘shilardi.
    # Endi bu avtomatik qo‘shish butunlay olib tashlangan. Bir martalik migratsiya
    # Railway volume ichida qolgan eski Assasin nusxasini ham tozalaydi.
    assasin_cleanup_marker = os.path.join(DATA_DIR, "assasin_cleanup_20260908_v1.done")
    if not os.path.exists(assasin_cleanup_marker):
        before_count = len(books)
        books[:] = [
            b for b in books
            if str(b.get("name", "")).strip().casefold() != "assasin"
        ]
        removed_count = before_count - len(books)
        if removed_count:
            changed = True
        marker_tmp = assasin_cleanup_marker + ".tmp"
        with open(marker_tmp, "w", encoding="utf-8") as f:
            f.write(f"removed={removed_count};at={datetime.now().isoformat()}\\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(marker_tmp, assasin_cleanup_marker)
        print(f"ASSASIN_LEGACY_CLEANUP_20260908: removed={removed_count}")

'''
s = s[:pos1] + replacement + s[pos2:]
p.write_text(s, encoding='utf-8')
