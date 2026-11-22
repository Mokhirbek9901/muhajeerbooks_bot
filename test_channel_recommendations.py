from datetime import datetime
import json
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import channel_recommendations as recommendations


KOREA = ZoneInfo("Asia/Seoul")
TUESDAY = datetime(2026, 11, 24, 19, 0, tzinfo=KOREA)
FRIDAY = datetime(2026, 11, 27, 19, 0, tzinfo=KOREA)
CHANNEL_ID = -1001234567890


def book(identifier, title, stock=5, cover=None):
    return {"id": identifier, "title": title, "stock": stock, "price": 12000, "cover": cover}


def catalog(books, live=None):
    live = books if live is None else live

    def fetch(params):
        search = params["search"]
        source = [entry for entry in live if entry["title"] == search] if search else books
        return {"books": source, "more": False}
    return fetch


class Telegram:
    def __init__(self, allowed=True, kind="channel", failure=None):
        self.allowed = allowed
        self.kind = kind
        self.failure = failure
        self.calls = []

    def __call__(self, method, params):
        if method == "getMe":
            result = {"id": 4211, "username": "muhajeer_test_bot"}
        elif method == "getChat":
            result = {"id": CHANNEL_ID, "type": self.kind}
        elif method == "getChatMember":
            result = {"status": "administrator", "can_post_messages": self.allowed}
        else:
            self.calls.append((method, params))
            if self.failure and method == self.failure[0]:
                raise HTTPError("telegram", self.failure[1], "Test rejection", {}, None)
            result = {"message_id": 1}
        return {"ok": True, "result": result}


class ChannelRecommendationsTest(unittest.TestCase):
    def setUp(self):
        self.settings = recommendations.Settings.from_env({
            "MUHAJEER_RECOMMEND_CHANNEL": "t.me/showcase_books",
        })
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def publish(self, telegram, books, now=TUESDAY, fresh=None):
        return recommendations.publish_slot(
            telegram, catalog(books, fresh), self.settings, self.directory.name, now,
        )

    def test_schedule_and_channel_parsing(self):
        self.assertEqual(self.settings.channel, "@showcase_books")
        self.assertIsNone(recommendations.Settings.from_env({}))
        self.assertIsNone(self.settings.slot(TUESDAY.replace(hour=18)))
        self.assertIsNone(self.settings.slot(TUESDAY.replace(hour=20)))
        self.assertIsNone(self.settings.slot(TUESDAY.replace(day=25)))
        self.assertTrue(self.settings.slot(FRIDAY))

    def test_does_not_publish_without_channel_permission(self):
        for telegram in (Telegram(allowed=False), Telegram(kind="supergroup")):
            with self.subTest(telegram=telegram), self.assertRaises((PermissionError, ValueError)):
                self.publish(telegram, [book("1", "Kitob")])
            self.assertEqual(telegram.calls, [])

    def test_rechecks_stock_and_posts_only_currently_available_books(self):
        first = book("1", "Tugagan kitob")
        second = book("2", "Mavjud kitob", 3)
        telegram = Telegram()
        self.assertEqual(self.publish(telegram, [first, second],
                                      fresh=[book("1", "Tugagan kitob", 0), second]), "posted")
        method, data = telegram.calls[0]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(data["chat_id"], CHANNEL_ID)
        self.assertIn("Mavjud kitob", data["text"])
        self.assertIn("Omborda 3 dona", data["text"])
        self.assertNotIn("Tugagan kitob", data["text"])
        self.assertEqual(json.loads(data["reply_markup"])["inline_keyboard"][0][0]["url"],
                         "https://t.me/muhajeer_test_bot")

    def test_no_posts_outside_schedule_or_without_stock(self):
        telegram = Telegram()
        self.assertEqual(self.publish(telegram, [book("1", "Kitob")], TUESDAY.replace(hour=18)),
                         "outside_schedule")
        self.assertEqual(self.publish(telegram, [book("1", "Kitob", 0)]), "no_stock")
        self.assertEqual(telegram.calls, [])

    def test_later_run_rotates_books_and_same_slot_is_idempotent(self):
        telegram = Telegram()
        books = [book("1", "Inshiroh"), book("2", "Sof aqiyda")]
        self.assertEqual(self.publish(telegram, books), "posted")
        self.assertEqual(self.publish(telegram, books), "already_processed")
        self.assertEqual(self.publish(telegram, books, FRIDAY), "posted")
        self.assertEqual(len(telegram.calls), 2)
        self.assertNotEqual(telegram.calls[0][1]["text"], telegram.calls[1][1]["text"])

    def test_unavailable_photo_falls_back_to_text(self):
        telegram = Telegram(failure=("sendPhoto", 400))
        self.assertEqual(self.publish(telegram, [book("1", "Inshiroh", cover="https://example.com/book.jpg")]),
                         "posted")
        self.assertEqual([method for method, _ in telegram.calls], ["sendPhoto", "sendMessage"])

    def test_explicit_rate_rejection_allows_retry(self):
        telegram = Telegram(failure=("sendMessage", 429))
        books = [book("1", "Inshiroh")]
        with self.assertRaises(HTTPError):
            self.publish(telegram, books)
        telegram.failure = None
        self.assertEqual(self.publish(telegram, books), "posted")

    def test_unknown_send_outcome_is_not_repeated(self):
        original = Telegram()

        def unavailable(method, params):
            if method == "sendMessage":
                raise TimeoutError()
            return original(method, params)

        books = [book("1", "Inshiroh")]
        with self.assertRaises(TimeoutError):
            self.publish(unavailable, books)
        self.assertEqual(self.publish(original, books), "already_processed")
        self.assertEqual(original.calls, [])
