import io
import json
import random
import time
import urllib.error
import urllib.request


# Supabase/PostgREST yoki gateway vaqtinchalik deb belgilaydigan statuslar.
# 520 Cloudflare/gateway uzilishi sifatida ham qayta uriniladi.
# Oddiy 500 xatolar retry qilinmaydi: faqat Supabase'ning aniq
# "Failed to get project config" javobi serverga so'rov yetib bormagan
# vaqtinchalik platform xatosi sifatida alohida qayta uriniladi.
TRANSIENT_HTTP_STATUS = frozenset({408, 409, 502, 503, 504, 520})
TRANSIENT_500_MARKERS = (
    "failed to get project config",
)


def _retryable_http_error(code, raw_body):
    if code in TRANSIENT_HTTP_STATUS:
        return True
    if code != 500:
        return False
    text = raw_body.decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in TRANSIENT_500_MARKERS)


def post_json(url, payload, headers, timeout, max_attempts=4, sleeper=time.sleep):
    """POST JSON with bounded exponential backoff for transient failures."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(max_attempts):
        request_headers = dict(headers)
        if attempt:
            request_headers["X-Retry-Count"] = str(attempt)
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read()
            except Exception:
                error_body = b""

            retryable = _retryable_http_error(exc.code, error_body)
            if not retryable or attempt + 1 >= max_attempts:
                # Caller logida asl Supabase javobi yo'qolib ketmasligi uchun
                # o'qilgan body bilan HTTPError'ni qayta tiklaymiz.
                raise urllib.error.HTTPError(
                    exc.url,
                    exc.code,
                    exc.msg,
                    exc.hdrs,
                    io.BytesIO(error_body),
                ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 >= max_attempts:
                raise

        # 0.5s, 1s, 2s (+ kichik jitter). Cheklangan urinishlar Supabase
        # ulanish poolini ortiqcha so'rov bilan bosib yubormaydi.
        delay = 0.5 * (2**attempt) + random.uniform(0.0, 0.25)
        sleeper(delay)

    raise RuntimeError("Supabase so‘rovi bajarilmadi")

# Railway watchPatterns ushbu modulni ham kuzatadi; bu retry siyosati
# o'zgarsa keyingi commit avtomatik production buildni ishga tushiradi.
