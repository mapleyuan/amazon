from __future__ import annotations

import random
import time
from urllib.request import Request, urlopen

from app.crawler.adapters import ACCEPT_LANG

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def fetch_html(url: str, *, site: str, timeout: int = 15, max_bytes: int = 600_000) -> str:
    # Add tiny jitter to reduce regular request fingerprints.
    time.sleep(random.uniform(0.2, 0.6))

    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept-Language": ACCEPT_LANG.get(site, "en-US,en;q=0.9"),
        },
    )

    chunk_size = 64 * 1024
    remaining = max(1, int(max_bytes))
    chunks: list[bytes] = []

    with urlopen(request, timeout=timeout) as resp:
        while remaining > 0:
            to_read = min(chunk_size, remaining)
            chunk = resp.read(to_read)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)

    return b"".join(chunks).decode("utf-8", errors="ignore")
