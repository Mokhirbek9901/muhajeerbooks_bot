import os
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot

SECRET = os.environ.get('MIGRATION_SECRET', '')
PORT = int(os.environ.get('PORT', '8080'))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        if parsed.path == '/health':
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok'); return
        if not SECRET or q.get('key', [''])[0] != SECRET:
            self.send_response(403); self.end_headers(); return
        if parsed.path != '/migration/photo':
            self.send_response(404); self.end_headers(); return
        try:
            legacy_id = int(q.get('legacy_id', ['0'])[0])
            bot.refresh_books()
            book = next((b for b in bot.books if int(b.get('id', -1)) == legacy_id), None)
            if not book or not book.get('photo_id'):
                self.send_response(404); self.end_headers(); return
            info = bot.api('getFile', {'file_id': book['photo_id']})
            file_path = info.get('result', {}).get('file_path')
            if not file_path:
                self.send_response(404); self.end_headers(); return
            url = f"https://api.telegram.org/file/bot{bot.TOKEN}/{file_path}"
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
                content_type = response.headers.get_content_type() or 'image/jpeg'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500); self.end_headers()

def serve():
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()

if __name__ == '__main__':
    threading.Thread(target=serve, daemon=True).start()
    bot.main()
