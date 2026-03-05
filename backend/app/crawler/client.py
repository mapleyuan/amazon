from __future__ import annotations

import random
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.crawler.adapters import ACCEPT_LANG
from app.core.settings import get_settings

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _resolve_fetch_url(raw_url: str, *, source: str, proxy_template: str) -> str:
    normalized_source = (source or "direct").strip().lower()
    if normalized_source == "direct":
        return raw_url

    if normalized_source == "jina_ai":
        upstream = raw_url
        if upstream.startswith("https://"):
            upstream = "http://" + upstream.removeprefix("https://")
        return f"https://r.jina.ai/{upstream}"

    if normalized_source == "proxy_template":
        template = (proxy_template or "").strip()
        if not template or "{url}" not in template:
            raise RuntimeError("AMAZON_CRAWL_PROXY_TEMPLATE must include {url} when source=proxy_template")
        return template.replace("{url}", quote(raw_url, safe=""))

    raise RuntimeError(f"unsupported crawl source: {source}")


def fetch_html(url: str, *, site: str, timeout: int = 15, max_bytes: int = 600_000) -> str:
    # Add tiny jitter to reduce regular request fingerprints.
    time.sleep(random.uniform(0.2, 0.6))
    settings = get_settings()
    fetch_url = _resolve_fetch_url(
        url,
        source=settings.crawl_source,
        proxy_template=settings.crawl_proxy_template,
    )

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": ACCEPT_LANG.get(site, "en-US,en;q=0.9"),
    }
    cookie = str(settings.crawl_cookie or "").strip()
    if cookie:
        headers["Cookie"] = cookie
    referer = str(settings.crawl_referer or "").strip()
    if referer:
        headers["Referer"] = referer

    request = Request(fetch_url, headers=headers)

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
