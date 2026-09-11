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


if __name__ == "__main__":
    unittest.main()
