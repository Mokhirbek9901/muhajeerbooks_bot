"""Lightweight Telegram storefront over the existing Muhajeer Books checkout."""

import base64
import binascii
from collections import OrderedDict
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from urllib import error, parse
import uuid

import channel_recommendations
import cloud_bridge
from supabase_http import post_json


URL = os.environ.get(
    "MUHAJEER_MINI_APP_URL",
    "https://muhajeerbooksbot-production.up.railway.app/mini/",
).strip()
ENABLE_MENU = os.environ.get("MUHAJEER_MINI_APP_MENU", "0") == "1"
_RECEIPT_LIMIT = 5 * 1024 * 1024
_REQUEST_LIMIT = ((_RECEIPT_LIMIT + 2) // 3) * 4 + 32768
_ASSETS = {
    "/mini/": ("index.html", "text/html; charset=utf-8"),
    "/mini/app.css": ("app.css", "text/css; charset=utf-8"),
    "/mini/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/mini/muhajeer-logo.jpg": ("muhajeer-logo.jpg", "image/jpeg"),
}
_DIRECTORY = Path(__file__).parent / "miniapp"
_READY = threading.Event()
_SLOTS = threading.BoundedSemaphore(8)
_LOCK = threading.Lock()
_COUNTS = OrderedDict()
_CATALOG = OrderedDict()
_BANK = {}
_LOG = logging.getLogger(__name__)
_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
_PHONE = re.compile(r"[+()0-9 -]{7,32}\Z")


class MiniAppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def telegram_user(init_data, token, *, now=None):
    """Authenticate the Telegram account before reading any customer data."""
    denied = MiniAppError("Do‘konni Telegram botidan qayta oching.", 401)
    if not token or not init_data or len(init_data) > 8192:
        raise denied
    try:
        pairs = parse.parse_qsl(init_data, keep_blank_values=True,
                                strict_parsing=True, max_num_fields=24)
        fields = dict(pairs)
        signature = fields.pop("hash", "")
        if len(pairs) != len(fields) + 1 or not re.fullmatch("[0-9a-f]{64}", signature):
            raise denied
        encoded = "\n".join(key + "=" + fields[key] for key in sorted(fields))
        secret = hmac.digest(b"WebAppData", token.encode(), "sha256")
        expected = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise denied
        current = time.time() if now is None else now
        if not -30 <= current - int(fields["auth_date"]) <= 8 * 60 * 60:
            raise denied
        user_id = json.loads(fields["user"])["id"]
        if type(user_id) is not int or not 1 <= user_id < 2 ** 52:
            raise denied
        return user_id
    except (KeyError, ValueError, TypeError) as exc:
        raise denied from exc


def _limit(user, kind, limit, seconds):
    now = time.monotonic()
    key = (user, kind)
    with _LOCK:
        count, expiry = _COUNTS.pop(key, (0, now + seconds))
        if expiry <= now:
            count, expiry = 0, now + seconds
        _COUNTS[key] = (count + 1, expiry)
        if len(_COUNTS) > 4096:
            _COUNTS.popitem(last=False)
        if count >= limit:
            raise MiniAppError("Iltimos, birozdan keyin qayta urinib ko‘ring.", 429)


def _backend(path, payload):
    if not cloud_bridge.configured():
        raise MiniAppError("Do‘kon vaqtincha ishlamayapti.", 503)
    key = cloud_bridge.SUPABASE_ANON_KEY
    try:
        return post_json(
            cloud_bridge.SUPABASE_URL + path,
            payload,
            {"apikey": key, "Content-Type": "application/json",
             "Authorization": "Bearer " + key, "User-Agent": "MuhajeerMiniApp/1"},
            timeout=20,
            max_attempts=2,
        )
    except error.HTTPError as exc:
        try:
            data = json.loads(exc.read(2048))
            message = str(data.get("message") or data.get("error") or "")
        except (ValueError, AttributeError):
            message = ""
        allowed = (
            "Ismni to‘liq kiriting", "Telefon raqam noto‘g‘ri",
            "Manzilni to‘liq kiriting", "To‘liq manzilni kiriting",
            "Kitob topilmadi yoki sotuvda emas", "Kitob narxi noto‘g‘ri",
            "Haqiqiy to‘lov chekini tanlang",
            "Buyurtma summasi o‘zgardi. Jami summani qayta tekshiring.",
            "Buyurtma raqami noto‘g‘ri",
        )
        if message in allowed:
            raise MiniAppError(message, 409) from exc
        if exc.code == 400 and "omborda yetarli emas" in message:
            raise MiniAppError("Kitob qoldig‘i yetarli emas. Savatchani yangilang.", 409) from exc
        _LOG.warning("Mini App backend HTTP %s", exc.code)
    except (error.URLError, TimeoutError, ConnectionError, RuntimeError, ValueError) as exc:
        _LOG.warning("Mini App backend unavailable: %s", type(exc).__name__)
    raise MiniAppError("Server vaqtincha javob bermayapti. Qayta urinib ko‘ring.", 503)


def _rpc(user, action, data):
    return _backend("/rest/v1/rpc/telegram_miniapp", {
        "p_secret": cloud_bridge.SYNC_SECRET,
        "p_user": user, "p_action": action, "p_data": data,
    })


def _deliver_notice(telegram_api, notice):
    label = ("#" + str(notice["number"]) + " buyurtmangiz"
             if notice.get("number") else "Buyurtmangiz")
    if notice["status"] == "accepted":
        message = "✅ " + label + " qabul qilindi."
    else:
        message = "📦 " + label + " jo‘natildi."
        if notice.get("tracking"):
            message += "\nTrek raqami: " + str(notice["tracking"])
    try:
        result = telegram_api("sendMessage", {
            "chat_id": notice["recipient"],
            "text": message + "\n\nMuhajeer Books",
        })
        return {"result": "sent" if result.get("ok") is True else "failed"}
    except error.HTTPError as exc:
        if exc.code == 429:
            retry_after = (exc.headers or {}).get("Retry-After", "60")
            return {"result": "retry",
                    "retry_after": int(retry_after) if retry_after.isdecimal() else 60}
        if exc.code in (400, 403):
            return {"result": "unavailable"}
        return {"result": "uncertain"}
    except (OSError, ValueError):
        # A response may be lost after Telegram accepts the message.
        return {"result": "uncertain"}


def _process_notices(telegram_api):
    batch = _rpc(0, "notice_claim", {})
    for notice in batch:
        outcome = _deliver_notice(telegram_api, notice)
        _rpc(0, "notice_finish", {"id": notice["id"], "lease": notice["lease"], **outcome})
    return len(batch)


def _notice_loop(telegram_api):
    announced = False
    while True:
        try:
            _process_notices(telegram_api)
            if not announced:
                print("Telegram Mini App: status notification queue ready", flush=True)
                announced = True
        except Exception as exc:
            _LOG.warning("Mini App status notifications unavailable: %s", type(exc).__name__)
        time.sleep(45)


def _offset(value):
    if type(value) is not int or not 0 <= value <= 10000:
        raise MiniAppError("Sahifa raqami noto‘g‘ri.")
    return value


def _catalog(user, data):
    search = _short_text(data.get("search", ""), 80, "Qidiruv")
    offset = _offset(data.get("offset", 0))
    key = (search.casefold(), offset)
    now = time.monotonic()
    with _LOCK:
        cached = _CATALOG.get(key)
        if cached and cached[0] > now:
            return cached[1]
    response = _rpc(user, "catalog", {"search": search, "offset": offset})
    result = {"books": response["books"][:24], "more": response["more"]}
    with _LOCK:
        _CATALOG.pop(key, None)
        _CATALOG[key] = (now + 25, result)
        if len(_CATALOG) > 48:
            _CATALOG.popitem(last=False)
    return result


def _short_text(value, maximum, label):
    if not isinstance(value, str) or len(value) > maximum or "\0" in value:
        raise MiniAppError(label + " noto‘g‘ri.")
    return value.strip()


def _order_fields(data):
    name = _short_text(data.get("name"), 100, "Ism")
    phone = _short_text(data.get("phone"), 32, "Telefon raqami")
    address = _short_text(data.get("address", ""), 500, "Manzil")
    delivery = data.get("delivery")
    if len(name) < 2 or not _PHONE.fullmatch(phone) or len(re.sub(r"\D", "", phone)) < 7:
        raise MiniAppError("Ism va telefon raqamini to‘liq kiriting.")
    if delivery not in ("택배", "경산 직접수령"):
        raise MiniAppError("Yetkazish turini tanlang.")
    if delivery == "택배" and len(address) < 8:
        raise MiniAppError("To‘liq manzilni kiriting.")
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise MiniAppError("Savatchadagi kitoblar soni noto‘g‘ri.")
    line_items = []
    seen = set()
    for row in items:
        if not isinstance(row, dict):
            raise MiniAppError("Kitob ma’lumoti noto‘g‘ri.")
        book_id, quantity = row.get("book_id"), row.get("quantity")
        if (not isinstance(book_id, str) or not _UUID.fullmatch(book_id)
                or book_id in seen or type(quantity) is not int or not 1 <= quantity <= 100):
            raise MiniAppError("Kitob yoki miqdor noto‘g‘ri.")
        seen.add(book_id)
        line_items.append({"book_id": book_id, "quantity": quantity})
    return {"name": name, "phone": phone, "address": address,
            "delivery": delivery, "items": line_items}


def _receipt(value, content_type):
    if not isinstance(value, str) or len(value) > _REQUEST_LIMIT:
        raise MiniAppError("Chek rasmi 5 MB dan kichik bo‘lishi kerak.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise MiniAppError("Chek rasmi o‘qilmadi.") from exc
    if not 0 < len(raw) <= _RECEIPT_LIMIT:
        raise MiniAppError("Chek rasmi 5 MB dan kichik bo‘lishi kerak.")
    valid = (
        (content_type == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (content_type == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (content_type == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    )
    if not valid:
        raise MiniAppError("JPG, PNG yoki WEBP chek rasmini tanlang.")
    data = _backend("/functions/v1/payment-proof", {
        "action": "upload", "file_name": "telegram-receipt",
        "content_type": content_type, "data_base64": value,
    })
    path = data.get("path") if isinstance(data, dict) else None
    if not isinstance(path, str) or not path.startswith("receipts/"):
        raise MiniAppError("Chek saqlanmadi. Qayta urinib ko‘ring.", 503)
    return path


def _checkout(user, data):
    identifier = data.get("id")
    if not isinstance(identifier, str) or not _UUID.fullmatch(identifier):
        raise MiniAppError("Buyurtma raqami noto‘g‘ri.")
    identifier = str(uuid.UUID(identifier))
    previous = _rpc(user, "lookup", {"id": identifier})
    if previous:
        return previous
    _limit(user, "checkout", 6, 10 * 60)
    order = _order_fields(data)
    total = data.get("total")
    if type(total) is not int or total <= 0 or _rpc(user, "quote", order)["total"] != total:
        raise MiniAppError("Buyurtma summasi o‘zgardi. Jami summani qayta tekshiring.", 409)
    receipt = _receipt(data.get("receipt_image"), data.get("receipt_type"))
    return _rpc(user, "order", {**order, "id": identifier, "total": total, "receipt": receipt})


def _request(user, route, payload):
    if route == "catalog":
        return _catalog(user, payload)
    if route == "orders":
        data = _rpc(user, route, {"offset": _offset(payload.get("offset", 0))})
        return {"orders": data["orders"][:20], "more": data["more"]}
    if route == "quote":
        return {**_rpc(user, route, _order_fields(payload)), "bank": _BANK}
    if route == "order":
        return _checkout(user, payload)
    raise MiniAppError("Sahifa topilmadi.", 404)


def _response(handler, code, body, content_type, cache="no-store"):
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self' https://telegram.org; "
        "style-src 'self'; img-src 'self' https: data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors https://web.telegram.org",
    )
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _json(handler, status, data):
    _response(handler, status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
              "application/json; charset=utf-8")


def serve(handler, token):
    """Return False for the pre-existing bot webhook and health endpoint."""
    path = parse.urlsplit(handler.path).path
    if path != "/mini" and not path.startswith("/mini/"):
        return False
    if handler.command in ("GET", "HEAD"):
        if path == "/mini":
            handler.send_response(308)
            handler.send_header("Location", "/mini/")
            handler.end_headers()
            return True
        if path in _ASSETS:
            filename, content_type = _ASSETS[path]
            body = (_DIRECTORY / filename).read_bytes()
            _response(handler, 200, body, content_type, "public, max-age=180" if filename != "index.html" else "no-cache")
            return True
        if path == "/mini/health":
            _json(handler, 200 if _READY.is_set() else 503, {"ready": _READY.is_set()})
            return True
    if handler.command != "POST" or not path.startswith("/mini/api/"):
        _json(handler, 404, {"error": "Sahifa topilmadi."})
        return True
    if not _SLOTS.acquire(blocking=False):
        _json(handler, 503, {"error": "Do‘kon band. Birozdan keyin urinib ko‘ring."})
        return True
    try:
        handler.connection.settimeout(12)
        user = telegram_user(handler.headers.get("X-Telegram-Init-Data", ""), token)
        _limit(user, "api", 100, 60)
        action = path.removeprefix("/mini/api/")
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= (_REQUEST_LIMIT if action == "order" else 24000):
            raise MiniAppError("So‘rov hajmi noto‘g‘ri.", 413)
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict):
            raise MiniAppError("So‘rov noto‘g‘ri.")
        _json(handler, 200, _request(user, action, payload))
    except MiniAppError as exc:
        _json(handler, exc.status, {"error": str(exc)})
    except (ValueError, UnicodeError, TimeoutError):
        _json(handler, 400, {"error": "So‘rovni o‘qib bo‘lmadi."})
    except (BrokenPipeError, ConnectionResetError):
        pass
    except Exception as exc:
        _LOG.error("Mini App request failed: %s", type(exc).__name__)
        _json(handler, 503, {"error": "Qayta urinib ko‘ring."})
    finally:
        _SLOTS.release()
    return True


def menu_button():
    if not (ENABLE_MENU and _READY.is_set()):
        return None
    return {"text": "Do‘konni ochish", "web_app": {"url": URL}}


def start(telegram_api, bank, state_directory):
    """Check the shared checkout gateway before exposing a new bot menu button."""
    _BANK.update(bank)

    def setup():
        for interval in (0, 8, 20):
            if interval:
                time.sleep(interval)
            try:
                catalog = _catalog(1, {})
                if not isinstance(catalog.get("books"), list):
                    raise MiniAppError("Katalog javobi noto‘g‘ri.", 503)
                if ENABLE_MENU:
                    response = telegram_api("setChatMenuButton", {
                        "menu_button": json.dumps({
                            "type": "web_app", "text": "Do‘konni ochish",
                            "web_app": {"url": URL},
                        }),
                    })
                    if response.get("ok") is not True:
                        raise MiniAppError("Telegram menyusi sozlanmadi.", 503)
                _READY.set()
                print("Telegram Mini App: shared catalog ready; menu=" + str(ENABLE_MENU), flush=True)
                threading.Thread(target=_notice_loop, args=(telegram_api,),
                                 daemon=True, name="mini-app-order-notices").start()
                channel_recommendations.start(
                    telegram_api, lambda params: _rpc(1, "catalog", params),
                    os.environ, state_directory,
                )
                return
            except Exception as exc:
                _LOG.warning("Mini App readiness check failed: %s", type(exc).__name__)
    threading.Thread(target=setup, daemon=True, name="mini-app-setup").start()
