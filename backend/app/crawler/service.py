from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from app.core.settings import get_settings
from app.crawler.adapters import SITE_BASE, build_board_url
from app.crawler.client import fetch_html
from app.crawler.parsers import contains_block_page, parse_category_links, parse_product_detail, parse_ranking_page


def _mock_rows(site: str, board_type: str) -> list[dict]:
    snapshot = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict] = []
    for cat_idx in range(1, 3):
        category_key = f"mock-{board_type}-cat-{cat_idx}"
        category_name = f"Mock Category {cat_idx}"
        for rank in range(1, 6):
            asin = f"{cat_idx}{rank:09d}"[-10:]
            rows.append(
                {
                    "site": site,
                    "board_type": board_type,
                    "category_key": category_key,
                    "category_name": category_name,
                    "category_level": 2,
                    "parent_category_key": f"mock-{board_type}-parent",
                    "snapshot_date": snapshot,
                    "asin": asin,
                    "title": f"Mock Product {cat_idx}-{rank}",
                    "brand": "MockBrand",
                    "image_url": "",
                    "detail_url": f"{SITE_BASE[site]}/dp/{asin}",
                    "rank": rank,
                    "price_text": "$9.99",
                    "rating": 4.5,
                    "review_count": 100 + rank,
                }
            )
    return rows


def _category_key_from_url(url: str) -> str:
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"cat-{digest[:12]}"


def _needs_detail_enrichment(row: dict) -> bool:
    title = str(row.get("title") or "")
    asin = str(row.get("asin") or "")
    return (
        not title
        or title == asin
        or not row.get("price_text")
        or row.get("rating") is None
        or row.get("review_count") is None
    )


def _enrich_rows_with_detail(rows: list[dict], site: str) -> None:
    settings = get_settings()
    if settings.detail_enrich_limit <= 0:
        return

    enriched: dict[str, dict] = {}
    candidates: list[str] = []
    seen: set[str] = set()
    for row in rows:
        asin = row["asin"]
        if asin in seen:
            continue
        seen.add(asin)
        if _needs_detail_enrichment(row):
            candidates.append(asin)

    for asin in candidates[: settings.detail_enrich_limit]:
        detail_url = f"{SITE_BASE[site]}/dp/{asin}"
        try:
            html_text = fetch_html(detail_url, site=site)
            if contains_block_page(html_text):
                continue
            enriched[asin] = parse_product_detail(html_text, asin)
        except Exception:  # noqa: BLE001
            continue

    if not enriched:
        return

    for row in rows:
        detail = enriched.get(row["asin"])
        if not detail:
            continue

        if not row.get("title") or row.get("title") == row["asin"]:
            if detail.get("title"):
                row["title"] = detail["title"]
        if not row.get("price_text") and detail.get("price_text"):
            row["price_text"] = detail["price_text"]
        if row.get("rating") is None and detail.get("rating") is not None:
            row["rating"] = detail["rating"]
        if row.get("review_count") is None and detail.get("review_count") is not None:
            row["review_count"] = detail["review_count"]
        if not row.get("brand") and detail.get("brand"):
            row["brand"] = detail["brand"]
        if not row.get("image_url") and detail.get("image_url"):
            row["image_url"] = detail["image_url"]


def crawl_site_board(site: str, board_type: str) -> list[dict]:
    settings = get_settings()
    if settings.mock_crawl:
        return _mock_rows(site, board_type)

    board_url = build_board_url(site, board_type)
    html_text = fetch_html(board_url, site=site)
    if contains_block_page(html_text):
        raise RuntimeError(f"site blocked for {site} {board_type}")

    category_links = parse_category_links(html_text)
    if not category_links:
        category_links = [(board_url, "root")]

    rows: list[dict] = []
    snapshot = datetime.now(timezone.utc).date().isoformat()
    for href, category_name in category_links[:20]:
        url = href if href.startswith("http") else f"{SITE_BASE[site]}{href}"
        category_html = fetch_html(url, site=site)
        if contains_block_page(category_html):
            continue

        category_key = _category_key_from_url(url)
        items = parse_ranking_page(category_html)[:100]
        for item in items:
            detail_url = item.get("detail_url") or f"/dp/{item['asin']}"
            if not str(detail_url).startswith("http"):
                detail_url = f"{SITE_BASE[site]}{detail_url}"
            rows.append(
                {
                    "site": site,
                    "board_type": board_type,
                    "category_key": category_key,
                    "category_name": category_name,
                    "category_level": 2,
                    "parent_category_key": _category_key_from_url(board_url),
                    "snapshot_date": snapshot,
                    "asin": item["asin"],
                    "title": item.get("title") or item["asin"],
                    "brand": None,
                    "image_url": item.get("image_url"),
                    "detail_url": detail_url,
                    "rank": int(item["rank"]),
                    "price_text": item.get("price_text"),
                    "rating": item.get("rating"),
                    "review_count": item.get("review_count"),
                }
            )

    _enrich_rows_with_detail(rows, site)
    return rows
