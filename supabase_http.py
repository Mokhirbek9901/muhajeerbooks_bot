import json
import random
import time
import urllib.error
import urllib.request


# Supabase/PostgREST vaqtinchalik deb belgilaydigan statuslar. Gatewayning
# odatiy 502 javobi ham qayta uriniladi; boshqa 4xx xatolar darhol qaytariladi.
TRANSIENT_HTTP_STATUS = frozenset({408, 409, 502, 503, 504})


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
            if exc.code not in TRANSIENT_HTTP_STATUS or attempt + 1 >= max_attempts:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 >= max_attempts:
                raise

        # 0.5s, 1s, 2s (+ kichik jitter). Cheklangan urinishlar Supabase
        # ulanish poolini ortiqcha so'rov bilan bosib yubormaydi.
        delay = 0.5 * (2**attempt) + random.uniform(0.0, 0.25)
        sleeper(delay)

    raise RuntimeError("Supabase so‘rovi bajarilmadi")
