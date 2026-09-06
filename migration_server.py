import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot


MIGRATION_SECRET = os.environ.get("MIGRATION_SECRET", "")
PORT = int(os.environ.get("PORT", "8080"))


class MigrationHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(200, {"ok": True})
            return

        if parsed.path != "/migration/books":
            self._send_json(404, {"error": "not_found"})
            return

        supplied = query.get("key", [""])[0]
        if not MIGRATION_SECRET or supplied != MIGRATION_SECRET:
            self._send_json(403, {"error": "forbidden"})
            return

        try:
            current_books = bot.refresh_books()
            self._send_json(200, {"books": current_books})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})


def start_http_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), MigrationHandler)
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=start_http_server, daemon=True).start()
    bot.main()

# migration trigger
