"""Welcome new Muhajeer Books channel subscribers without unsolicited bulk DMs.

Telegram permits a first private message for a pending chat_join_request (using
user_chat_id, within five minutes). A normal chat_member join can only be
welcomed if the user has already granted the bot private-chat access.
"""

import json
import os
from pathlib import Path
import time

_CHANNEL_ID = None
_CHANNEL_RAW = ""
_WELCOME_FILE = "telegram_channel_welcomes.json"
_SHOP = "https://t.me/muhajeerbooks_bot"


def _result(api, method, params):
    response = api(method, params)
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError("Telegram " + method + " failed")
    return response.get("result")


def configure(api):
    """Resolve exactly the channel configured for Muhajeer Books."""
    global _CHANNEL_ID, _CHANNEL_RAW
    _CHANNEL_RAW = os.environ.get("MUHAJEER_RECOMMEND_CHANNEL", "").strip()
    if not _CHANNEL_RAW:
        print("Telegram channel welcome: no channel configured", flush=True)
        return
    try:
        chat = _result(api, "getChat", {"chat_id": _CHANNEL_RAW})
        if chat.get("type") != "channel":
            raise RuntimeError("not a channel")
        _CHANNEL_ID = chat["id"]
        me = _result(api, "getMe", {})
        member = _result(api, "getChatMember",
                         {"chat_id": _CHANNEL_ID, "user_id": me["id"]})
        is_admin = member.get("status") in ("administrator", "creator")
        invite = member.get("status") == "creator" or member.get("can_invite_users") is True
        print("Telegram channel welcome: channel connected; bot admin=" +
              str(is_admin) + "; invite permission=" + str(invite), flush=True)
        if not invite:
            print("Telegram channel welcome: grant bot Invite Users permission to "
                  "receive joining requests", flush=True)
        if invite:
            try:
                _announce_request_link(api)
            except Exception as exc:
                print("Telegram channel welcome: request-link setup failed (" +
                      type(exc).__name__ + ")", flush=True)
    except Exception as exc:
        print("Telegram channel welcome: channel setup unavailable (" +
              type(exc).__name__ + ")", flush=True)


def _same_channel(chat):
    if not isinstance(chat, dict) or chat.get("type") != "channel":
        return False
    if _CHANNEL_ID is not None:
        return chat.get("id") == _CHANNEL_ID
    raw = _CHANNEL_RAW
    if raw.startswith("@"):
        return str(chat.get("username", "")).lower() == raw[1:].lower()
    if raw.lstrip("-").isdecimal():
        return str(chat.get("id")) == raw
    return False


def _joined(member):
    if not isinstance(member, dict):
        return False
    status = member.get("status")
    return status in ("member", "administrator", "creator") or (
        status == "restricted" and member.get("is_member") is True)


def _seen(path, key, now):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
    except (FileNotFoundError, OSError, ValueError):
        return {}
    # Keeping only 30 days of user IDs prevents unbounded personal data storage.
    return {k: v for k, v in data.items()
            if isinstance(v, (int, float)) and 0 <= now - v < 30 * 86400}


def _remember(path, data, key, now):
    data[key] = now
    if len(data) > 4000:
        data = dict(sorted(data.items(), key=lambda row: row[1])[-3000:])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def handle(update, api, state_directory):
    """Consume a join event; return True if it was for this channel."""
    joining = update.get("chat_join_request")
    membership = update.get("chat_member")
    event = joining if isinstance(joining, dict) else membership
    if not isinstance(event, dict) or not _same_channel(event.get("chat")):
        return False

    now = int(time.time())
    timestamp = event.get("date")
    if type(timestamp) is not int or not -60 <= now - timestamp <= 270:
        return True  # Do not send stale welcome messages after downtime.

    if joining:
        person = joining.get("from") or {}
        recipient = joining.get("user_chat_id")
        label = "request"
    else:
        old = (membership.get("old_chat_member") or {})
        new = (membership.get("new_chat_member") or {})
        if _joined(old) or not _joined(new):
            return True
        person = new.get("user") or {}
        recipient = person.get("id")  # Only works if the person started the bot.
        label = "joined"

    user_id = person.get("id")
    if (type(user_id) is not int or user_id <= 0 or person.get("is_bot") is True
            or type(recipient) is not int or recipient <= 0):
        return True

    path = Path(state_directory) / _WELCOME_FILE
    key = f"{event['chat']['id']}:{user_id}"
    history = _seen(path, key, now)
    if key in history:
        if joining:
            _approve_our_link(joining, api)
        return True

    message = (
        "📚 Muhajeer Books’ga xush kelibsiz!\n\n"
        "Endi sevimli kitoblaringizni Telegram orqali ham osonlikcha "
        "buyurtma qilishingiz mumkin.\n\n"
        "📖 Kitoblarni ko‘ring va tanlang.\n"
        "🛒 Telegram Mini App orqali buyurtma bering.\n"
        "📦 Buyurtmangiz holatini kuzating.\n"
        "🚚 4 ta va undan ko‘p kitobga pochta bepul!\n\n"
        "👇 Kitob buyurtma qilish uchun bosing:"
    )
    markup = json.dumps({"inline_keyboard": [[
        {"text": "📚 Kitob buyurtma qilish", "url": _SHOP}
    ]]}, ensure_ascii=False)
    try:
        _result(api, "sendMessage", {
            "chat_id": recipient, "text": message, "reply_markup": markup,
        })
    except Exception as exc:
        # Direct joins often have no private messaging permission. This is
        # expected and must never block processing other bot updates.
        print("Telegram channel welcome: " + label + " message not delivered (" +
              type(exc).__name__ + ")", flush=True)
        if joining:
            _approve_our_link(joining, api)
        return True

    try:
        _remember(path, history, key, now)
    except OSError:
        print("Telegram channel welcome: dedup state not persisted", flush=True)
    print("Telegram channel welcome: " + label + " message delivered", flush=True)
    if joining:
        _approve_our_link(joining, api)
    return True



_LINK_NAME = "Muhajeer Books Mini App"
_LINK_FILE = "telegram_welcome_join_link.txt"
_NOTICE_FILE = "telegram_welcome_join_link_notified"


def _data_dir():
    root = Path("/data")
    return root if root.is_dir() else Path(".")


def _our_link():
    try:
        return (_data_dir() / _LINK_FILE).read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return ""


def _announce_request_link(api):
    """Create one welcome link and privately tell the bot administrator."""
    admin_id = os.environ.get("ADMIN_ID", "").strip()
    if not admin_id.isdecimal():
        return
    link = _our_link()
    if not link:
        link = create_request_link(api)
        (_data_dir() / _LINK_FILE).write_text(link + "\n", encoding="utf-8")
        print("Telegram channel welcome: request-to-join link created", flush=True)
    marker = _data_dir() / _NOTICE_FILE
    if marker.exists():
        return
    _result(api, "sendMessage", {
        "chat_id": admin_id,
        "text": (
            "✅ Muhajeer Books kanali uchun avtomatik kutib olish havolasi:\n\n"
            + link +
            "\n\nShu havolani yangi mijozlarga yuboring. Mijoz kirish so‘rovi "
            "yuborganda bot avval Mini App haqidagi xabarni yuboradi, keyin "
            "shu maxsus havola orqali kelgan so‘rovni avtomatik tasdiqlaydi.\n\n"
            "Eslatma: eski ommaviy kanal havolasidan to‘g‘ridan-to‘g‘ri "
            "qo‘shilgan begona mijozga Telegram shaxsiy xabar yuborishga "
            "ruxsat bermasligi mumkin."
        ),
    })
    marker.write_text("1\n", encoding="utf-8")
    print("Telegram channel welcome: request link sent to administrator", flush=True)


def _approve_our_link(joining, api):
    """Only approve joins made via this bot's own dedicated welcome link."""
    own_link = _our_link()
    supplied = (joining.get("invite_link") or {}).get("invite_link", "")
    if not own_link or supplied != own_link:
        return
    try:
        _result(api, "approveChatJoinRequest", {
            "chat_id": joining["chat"]["id"],
            "user_id": joining["from"]["id"],
        })
        print("Telegram channel welcome: dedicated join request approved", flush=True)
    except Exception as exc:
        print("Telegram channel welcome: dedicated approval unavailable (" +
              type(exc).__name__ + ")", flush=True)


def create_request_link(api):
    """An admin can use /welcome_link to create an opt-in joining link."""
    if _CHANNEL_ID is None:
        raise RuntimeError("Telegram channel is not configured")
    result = _result(api, "createChatInviteLink", {
        "chat_id": _CHANNEL_ID,
        "name": "Muhajeer Books Mini App",
        "creates_join_request": "true",
    })
    return result["invite_link"]
