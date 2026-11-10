import io
import json
import unittest
import urllib.error
from unittest import mock

from supabase_http import post_json


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _http_error(code):
    return urllib.error.HTTPError(
        "https://example.supabase.co/rest/v1/rpc/test",
        code,
        "temporary",
        {},
        io.BytesIO(b'{}'),
    )


class SupabaseHttpTest(unittest.TestCase):
    def test_retries_504_then_succeeds(self):
        waits = []
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[_http_error(504), _Response({"ok": True})],
        ) as opened, mock.patch("random.uniform", return_value=0):
            result = post_json(
                "https://example.supabase.co/rest/v1/rpc/test",
                {"p_id": 1},
                {"apikey": "public"},
                timeout=3,
                sleeper=waits.append,
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(waits, [0.5])
        retry_request = opened.call_args_list[1].args[0]
        self.assertEqual(retry_request.get_header("X-retry-count"), "1")

    def test_does_not_retry_permanent_400(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=_http_error(400)
        ) as opened:
            with self.assertRaises(urllib.error.HTTPError):
                post_json(
                    "https://example.supabase.co/rest/v1/rpc/test",
                    {},
                    {},
                    timeout=3,
                    sleeper=lambda _: None,
                )

        self.assertEqual(opened.call_count, 1)

    def test_retries_429_with_retry_after_and_same_order_body(self):
        waits = []
        error = _http_error(429)
        error.hdrs = {"Retry-After": "2"}
        with mock.patch("urllib.request.urlopen", side_effect=[error, _Response({"ok": True})]) as opened, mock.patch("random.uniform", return_value=0):
            result = post_json("https://gateway.test/functions/v1/bot-rpc",
                {"name": "bot_order_create", "params": {"p_order": {"order_id": "stable-id"}}},
                {"apikey": "public"}, timeout=3, sleeper=waits.append)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(waits, [2])
        self.assertEqual(opened.call_args_list[0].args[0].data, opened.call_args_list[1].args[0].data)

    def test_429_exhaustion_is_bounded_and_preserves_error(self):
        waits = []
        with mock.patch("urllib.request.urlopen", side_effect=[_http_error(429) for _ in range(3)]) as opened, mock.patch("random.uniform", return_value=0):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post_json("https://gateway.test/functions/v1/bot-rpc", {}, {}, timeout=3,
                    max_attempts=3, sleeper=waits.append)
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(waits, [0.5, 1.0])
        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(caught.exception.read(), b'{}')


if __name__ == "__main__":
    unittest.main()
