"""Scheduled Telegram channel posts sourced from the shared storefront catalog."""

from dataclasses import dataclass
from datetime import date, datetime, time as wall_time, timedelta
import fcntl
from html import escape
import json
import logging
import os
from pathlib import Path
import random
import re
import threading
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


_LOG = logging.getLogger(__name__)
_KOREA = ZoneInfo("Asia/Seoul")
_WEEKDAYS = dict(zip(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"), range(7)))
_USERNAME = re.compile(r"[A-Za-z0-9_]{5,32}\Z")
_PAGE_SIZE = 24
_RECENT_LIMIT = 48


@dataclass(frozen=True)
class Settings:
    channel: str
    days: frozenset
    publish_at: wall_time
    interval_days: int = 0
    first_day: date | None = None

    @classmethod
    def from_env(cls, environment):
        channel = environment.get("MUHAJEER_RECOMMEND_CHANNEL", "").strip()
        if not channel:
            return None
        if channel.startswith(("t.me/", "telegram.me/")):
            channel = "https://" + channel
        if channel.startswith("https://"):
            url = urlsplit(channel)
            if url.hostname not in ("t.me", "telegram.me"):
                raise ValueError("Telegram kanal havolasi noto‘g‘ri")
            channel = "@" + url.path.strip("/").removeprefix("s/")
        if not (re.fullmatch(r"-100[0-9]{6,13}", channel)
                or channel.startswith("@") and _USERNAME.fullmatch(channel[1:])):
            raise ValueError("Kanalning @nomi yoki raqamli ID kerak")
        day_text = environment.get("MUHAJEER_RECOMMEND_DAYS", "TUE,FRI")
        days = frozenset(_WEEKDAYS[day.strip().upper()] for day in day_text.split(","))
        clock = environment.get("MUHAJEER_RECOMMEND_TIME", "19:00").strip()
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock):
            raise ValueError("Post vaqti HH:MM formatida bo‘lishi kerak")
        interval = int(environment.get("MUHAJEER_RECOMMEND_INTERVAL_DAYS", "0"))
        if interval not in (0, 1, 2):
            raise ValueError("Post oralig‘i noto‘g‘ri")
        first = date.fromisoformat(environment["MUHAJEER_RECOMMEND_FIRST_DAY"]) if interval else None
        return cls(channel, days, wall_time.fromisoformat(clock), interval, first)

    def slot(self, now):
        now = now.astimezone(_KOREA)
        start = now.replace(hour=self.publish_at.hour, minute=self.publish_at.minute,
                            second=0, microsecond=0)
        if self.interval_days:
            elapsed = (now.date() - self.first_day).days
            scheduled = elapsed >= 0 and elapsed % self.interval_days == 0
        else:
            scheduled = now.weekday() in self.days
        if scheduled and start <= now < start + timedelta(minutes=60):
            return start.isoformat()
        return None


def _result(api, method, params):
    result = api(method, params)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Telegram " + method + " failed")
    return result["result"]


def _bot_link(bot):
    username = bot.get("username", "")
    if not _USERNAME.fullmatch(username):
        raise ValueError("Bot manzili topilmadi")
    endpoint = "https://t.me/" + username
    return endpoint + "?startapp" if bot.get("has_main_web_app") is True else endpoint


def _destination(api, channel, bot=None):
    bot = bot or _result(api, "getMe", {})
    chat = _result(api, "getChat", {"chat_id": channel})
    if chat.get("type") != "channel":
        raise ValueError("Tavsiyalar uchun Telegram kanali kerak")
    account = _result(api, "getChatMember", {"chat_id": chat["id"], "user_id": bot["id"]})
    can_post = account["status"] == "creator" or (
        account["status"] == "administrator" and account.get("can_post_messages") is True
    )
    if not can_post:
        raise PermissionError("Botga kanalga post yuborish huquqi kerak")
    return chat["id"], _bot_link(bot)


def _eligible(book):
    return (
        isinstance(book.get("id"), str)
        and bool(str(book.get("title") or "").strip())
        and type(book.get("price")) is int and book["price"] > 0
        and type(book.get("stock")) is int and book["stock"] > 0
    )


def _candidates(catalog):
    books = {}
    for offset in range(0, 480, _PAGE_SIZE):
        page = catalog({"search": "", "offset": offset})
        books.update((book["id"], book) for book in page["books"][:_PAGE_SIZE] if _eligible(book))
        if not page["more"]:
            break
    return list(books.values())


def _fresh_book(catalog, book):
    search = book["title"][:80].strip()
    page = catalog({"search": search, "offset": 0})
    return next((current for current in page["books"]
                 if current.get("id") == book["id"] and _eligible(current)), None)


def _pick_book(catalog, recent, slot):
    candidates = _candidates(catalog)
    last_seen = {book_id: index for index, book_id in enumerate(recent)}
    random.Random(slot).shuffle(candidates)
    candidates.sort(key=lambda book: last_seen.get(book["id"], -1))
    for book in candidates:
        current = _fresh_book(catalog, book)
        if current:
            return current
    return None


def _caption(book):
    title = " ".join(book["title"].split())[:180]
    author = " ".join(str(book.get("author") or "").split())[:100]
    description = " ".join(str(book.get("description") or "").split())
    if len(description) > 280:
        description = (description[:280].rsplit(" ", 1)[0] or description[:280]) + "…"
    lines = ["📚 Muhajeer Books tavsiyasi", "", title]
    if author:
        lines.append(author)
    if description:
        lines.extend(("", description))
    lines.extend(("", f"Narxi ₩{book['price']:,}", f"Omborda {book['stock']} dona"))
    return "\n".join(lines)


def _post_options(channel, shop_link):
    return {
        "chat_id": channel,
        "reply_markup": json.dumps({"inline_keyboard": [[
            {"text": "Do‘konni ochish", "url": shop_link}
        ]]}, ensure_ascii=False),
    }


def _post(api, channel, shop_link, book, caption=None):
    params = _post_options(channel, shop_link)
    if caption is None:
        caption = _caption(book)
    else:
        params["parse_mode"] = "HTML"
    cover = book.get("cover")
    if isinstance(cover, str) and urlsplit(cover).scheme == "https":
        try:
            return _result(api, "sendPhoto", {**params, "photo": cover, "caption": caption})
        except HTTPError as exc:
            if exc.code != 400:
                raise
    return _result(api, "sendMessage", {**params, "text": caption})


def _save(path, data):
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def publish_launch(api, catalog, settings, state_directory, launch):
    """Publish the approved announcement and recommendation in that order."""
    channel, shop_link = _destination(api, settings.channel)
    path = Path(state_directory) / "telegram_recommendations.json"
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            history = {}
        record = history.setdefault(str(channel), {})
        messages = record.setdefault("launches", {}).setdefault(launch["date"], {})

        def send_once(kind, send):
            if kind not in messages:
                messages[kind] = None
                _save(path, history)
                try:
                    messages[kind] = send()["message_id"]
                except HTTPError as exc:
                    if 400 <= exc.code < 500 and exc.code != 408:
                        del messages[kind]
                        _save(path, history)
                    raise
                _save(path, history)
            if messages[kind] is None:
                raise RuntimeError("Telegram launch delivery unconfirmed: " + kind)

        send_once("announcement", lambda: _result(api, "sendMessage", {
            **_post_options(channel, shop_link),
            "text": launch["announcement"],
            "parse_mode": "HTML",
        }))
        if "recommendation" not in messages:
            title = launch["title"]
            page = catalog({"search": title[:80], "offset": 0})
            book = next((row for row in page["books"]
                         if row.get("title") == title and _eligible(row)), None)
            if not book:
                return {"announcement": messages["announcement"], "recommendation": "out_of_stock"}
            author = escape(book.get("author") or "")
            caption = (
                "📚 <b>Muhajeer Books tavsiyasi</b>\n\n"
                f"<b>{escape(title)}</b>" + (f" — {author}" if author else "") +
                f"\n\n{escape(launch['description'])}\n\n"
                f"<b>Narxi ₩{book['price']:,} · Omborda {book['stock']} dona</b>"
            )
            send_once("recommendation", lambda: _post(api, channel, shop_link, book, caption))
            recent = [key for key in record.get("recent", []) if key != book["id"]]
            record["recent"] = (recent + [book["id"]])[-_RECENT_LIMIT:]
            _save(path, history)
        else:
            send_once("recommendation", None)
        return messages.copy()


def publish_slot(api, catalog, settings, state_directory, now):
    slot = settings.slot(now)
    if slot is None:
        return "outside_schedule"
    path = Path(state_directory) / "telegram_recommendations.json"
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            history = {}
        channel, shop_link = _destination(api, settings.channel)
        previous = history.get(str(channel), {})
        if previous.get("slot") == slot:
            return "already_processed"
        recent = previous.get("recent", [])
        book = _pick_book(catalog, recent, slot)
        # Reserve the slot before Telegram is called so a lost response does not
        # cause a second public post.
        history[str(channel)] = {**previous, "slot": slot, "recent": recent}
        _save(path, history)
        if not book:
            return "no_stock"
        try:
            _post(api, channel, shop_link, book)
        except HTTPError as exc:
            if exc.code == 429:
                history[str(channel)] = previous
                _save(path, history)
            raise
        history[str(channel)]["recent"] = (
            [book_id for book_id in recent if book_id != book["id"]] + [book["id"]]
        )[-_RECENT_LIMIT:]
        _save(path, history)
        return "posted"


def start(api, catalog, environment, state_directory):
    try:
        settings = Settings.from_env(environment)
        launch = json.loads(environment.get("MUHAJEER_RECOMMEND_LAUNCH", "null"))
    except (ValueError, KeyError):
        _LOG.warning("Telegram channel recommendations: invalid channel or schedule")
        return
    if settings is None:
        print("Telegram channel recommendations: awaiting channel configuration", flush=True)
        return

    def loop():
        try:
            bot = _result(api, "getMe", {})
            print("Telegram channel recommendations: shop link " + _bot_link(bot), flush=True)
            _destination(api, settings.channel, bot)
            print("Telegram channel recommendations: channel permissions verified", flush=True)
        except (OSError, ValueError, RuntimeError):
            _LOG.warning("Telegram channel recommendations: channel or posting permission unavailable")

        checked_slot = None
        launch_done = False
        while True:
            now = datetime.now(_KOREA)
            slot = settings.slot(now)
            delay = 55
            if launch and not launch_done and now.date().isoformat() == launch["date"]:
                try:
                    published = publish_launch(api, catalog, settings, state_directory, launch)
                    print("Telegram recommendation launch: " + json.dumps(published), flush=True)
                    launch_done = True
                except HTTPError as exc:
                    _LOG.warning("Telegram recommendation launch HTTP %s", exc.code)
                    retry = (exc.headers or {}).get("Retry-After", "")
                    if exc.code == 429 and retry.isdecimal():
                        delay = max(delay, min(3600, int(retry)))
                except (OSError, ValueError, RuntimeError) as exc:
                    _LOG.warning("Telegram recommendation launch pending: %s", type(exc).__name__)
            if slot is not None and slot != checked_slot:
                try:
                    outcome = publish_slot(api, catalog, settings, state_directory, now)
                    print("Telegram channel recommendations: " + outcome, flush=True)
                    checked_slot = slot
                except HTTPError as exc:
                    _LOG.warning("Telegram channel recommendations HTTP %s", exc.code)
                    retry = (exc.headers or {}).get("Retry-After", "")
                    if exc.code == 429 and retry.isdecimal():
                        delay = max(delay, min(3600, int(retry)))
                except (OSError, ValueError, RuntimeError) as exc:
                    _LOG.warning("Telegram channel recommendations pending: %s", type(exc).__name__)
            sleep(delay)

    threading.Thread(target=loop, daemon=True, name="telegram-channel-recommendations").start()
