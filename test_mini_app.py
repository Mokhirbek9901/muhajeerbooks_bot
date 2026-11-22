import base64
from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import mini_app


TOKEN = "demo:synthetic-test"
BOOK_ID = "0923e74c-18ce-4cc2-9724-5ac5464970c0"
ORDER_ID = "b9d240f0-48c4-48a3-8b00-ba203f9de407"


def signed(user=4211, when=None):
    fields = {
        "auth_date": str(int(time.time() if when is None else when)),
        "user": json.dumps({"id": user}, separators=(",", ":")),
    }
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    encoded = "\n".join(key + "=" + fields[key] for key in sorted(fields))
    fields["hash"] = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def order_payload():
    return {
        "id": ORDER_ID, "total": 16000,
        "name": "Sinov", "phone": "01012340000",
        "address": "Sinov manzili 123", "delivery": "택배",
        "items": [{"book_id": BOOK_ID, "quantity": 1, "price": 1}],
        "receipt_type": "image/png",
        "receipt_image": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode(),
    }


@contextmanager
def http_app():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if not mini_app.serve(self, TOKEN):
                self.send_error(404)

        do_POST = do_GET

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


class MiniAppTest(unittest.TestCase):
    def test_signed_identity_and_time_boundaries(self):
        self.assertEqual(mini_app.telegram_user(signed(), TOKEN), 4211)
        for data in (signed().replace("4211", "6552"), signed(when=time.time() - 90000),
                     signed(when=time.time() + 60), signed() + "&auth_date=9", ""):
            with self.subTest(data=data), self.assertRaises(mini_app.MiniAppError) as err:
                mini_app.telegram_user(data, TOKEN)
            self.assertEqual(err.exception.status, 401)

    def test_http_shell_and_private_orders(self):
        with http_app() as http, patch.object(mini_app, "_rpc", return_value={"orders": [], "more": False}) as rpc:
            with urlopen(http + "/mini/") as response:
                self.assertIn(b"Muhajeer Books", response.read())
                self.assertIn("frame-ancestors", response.headers["Content-Security-Policy"])
            for init_data, status in (("", 401), (signed(), 200)):
                request = Request(http + "/mini/api/orders", data=b'{"user_id": 5001}',
                    headers={"X-Telegram-Init-Data": init_data, "Content-Type": "application/json"})
                if status == 401:
                    with self.assertRaises(HTTPError) as err:
                        urlopen(request)
                    self.assertEqual(err.exception.code, status)
                    rpc.assert_not_called()
                else:
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response), {"orders": [], "more": False})
                    rpc.assert_called_once_with(4211, "orders", {"offset": 0})

    def test_checkout_only_passes_validated_fields(self):
        result = {"id": ORDER_ID, "total": 16000, "status": "new", "items": []}
        with patch.object(mini_app, "_rpc", side_effect=[None, {"total": 16000}, result]) as rpc, \
                patch.object(mini_app, "_backend", return_value={"path": "receipts/example.png"}) as storage:
            self.assertEqual(mini_app._checkout(4212, order_payload()), result)
            storage.assert_called_once()
        self.assertEqual(rpc.call_args.args[:2], (4212, "order"))
        self.assertEqual(rpc.call_args.args[2]["items"], [{"book_id": BOOK_ID, "quantity": 1}])
        self.assertEqual(rpc.call_args.args[2]["receipt"], "receipts/example.png")

    def test_retry_does_not_upload_receipt_again(self):
        with patch.object(mini_app, "_rpc", return_value={"id": ORDER_ID}) as rpc, \
                patch.object(mini_app, "_backend") as storage:
            self.assertEqual(mini_app._checkout(4213, {"id": ORDER_ID}), {"id": ORDER_ID})
            rpc.assert_called_once_with(4213, "lookup", {"id": ORDER_ID})
            storage.assert_not_called()

    def test_changed_total_and_bad_file_stop_before_upload(self):
        bad_file = order_payload()
        bad_file["receipt_image"] = "aGVsbG8="
        for payload, quote in ((order_payload(), 18000), (bad_file, 16000)):
            with self.subTest(quote=quote), \
                    patch.object(mini_app, "_rpc", side_effect=[None, {"total": quote}]), \
                    patch.object(mini_app, "_backend") as storage:
                with self.assertRaises(mini_app.MiniAppError):
                    mini_app._checkout(4214, payload)
                storage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
