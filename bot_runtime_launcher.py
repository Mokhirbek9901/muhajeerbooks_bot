from pathlib import Path

import app_image_sync  # Railway start old behavior: app image sync remains enabled.

# Admin kitoblar ro‘yxati uchun Telegram message-limit fix.

def run_bot_patched():
    source = Path("bot.py").read_text(encoding="utf-8")

    old = '''        if text == "📚 Kitoblar ro‘yxati":
            send(
                chat_id,
                admin_books_text(),
                admin_menu()
            )
            return
'''

    new = '''        if text == "📚 Kitoblar ro‘yxati":
            # Telegram sendMessage matni 4096 belgidan oshmasligi kerak.
            # Katalog kattalashganda ro‘yxatni xavfsiz qismlarga bo‘lib yuboramiz.
            full_text = admin_books_text()
            chunks = []
            current_lines = []
            current_len = 0

            for line in full_text.splitlines():
                line_len = len(line) + 1
                if current_lines and current_len + line_len > 3500:
                    chunks.append("\\n".join(current_lines))
                    current_lines = [line]
                    current_len = line_len
                else:
                    current_lines.append(line)
                    current_len += line_len

            if current_lines:
                chunks.append("\\n".join(current_lines))

            if not chunks:
                chunks = ["📚 Hozircha kitob yo‘q."]

            for index, chunk in enumerate(chunks):
                send(
                    chat_id,
                    chunk,
                    admin_menu() if index == len(chunks) - 1 else None
                )
            return
'''

    if old not in source:
        raise RuntimeError("Admin kitoblar ro‘yxati handleri topilmadi; bot.py o‘zgargan bo‘lishi mumkin.")

    patched = source.replace(old, new, 1)
    namespace = {"__name__": "__main__", "__file__": "bot.py"}
    exec(compile(patched, "bot.py", "exec"), namespace, namespace)


sync_source = Path("sync_wrapper.py").read_text(encoding="utf-8")
sync_target = 'runpy.run_path("bot.py", run_name="__main__")'
if sync_target not in sync_source:
    raise RuntimeError("sync_wrapper.py ichidagi bot start qatori topilmadi.")

sync_source = sync_source.replace(sync_target, "run_bot_patched()", 1)
sync_namespace = {
    "__name__": "__main__",
    "__file__": "sync_wrapper.py",
    "run_bot_patched": run_bot_patched,
}
exec(compile(sync_source, "sync_wrapper.py", "exec"), sync_namespace, sync_namespace)
