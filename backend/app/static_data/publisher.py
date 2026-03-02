from __future__ import annotations

from collections import defaultdict
from typing import Any

DEFAULT_FILTERS = {
    "site": "amazon.com",
    "board_type": "best_sellers",
    "has_price": "1",
    "top_n": 100,
    "sort_by": "rank",
    "sort_order": "asc",
}


def merge_available_dates(existing: list[str], new_date: str | None, retention_days: int) -> list[str]:
    dates = {date for date in existing if date}
    if new_date:
        dates.add(new_date)

    ordered = sorted(dates, reverse=True)
    limit = max(1, int(retention_days))
    return ordered[:limit]


def _normalize_item(snapshot_date: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_date": row.get("snapshot_date") or snapshot_date,
        "site": row.get("site", ""),
        "board_type": row.get("board_type", ""),
        "category_key": row.get("category_key", ""),
        "category_name": row.get("category_name") or row.get("category_key", ""),
        "rank": int(row.get("rank", 0) or 0),
        "asin": row.get("asin", ""),
        "title": row.get("title", ""),
        "brand": row.get("brand"),
        "price_text": row.get("price_text"),
        "rating": row.get("rating"),
        "review_count": row.get("review_count"),
        "detail_url": row.get("detail_url"),
    }


def build_daily_payload(snapshot_date: str, generated_at: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [_normalize_item(snapshot_date, row) for row in rows]
    categories: dict[tuple[str, str, str, str], int] = defaultdict(int)

    for item in items:
        categories[
            (
                item["site"],
                item["board_type"],
                item["category_key"],
                item["category_name"],
            )
        ] += 1

    category_items = [
        {
            "site": site,
            "board_type": board_type,
            "category_key": category_key,
            "category_name": category_name,
            "item_count": count,
        }
        for (site, board_type, category_key, category_name), count in sorted(categories.items())
    ]

    stats = {
        "total_items": len(items),
        "sites": len({item["site"] for item in items if item["site"]}),
        "boards": len({item["board_type"] for item in items if item["board_type"]}),
        "categories": len(category_items),
    }

    return {
        "snapshot_date": snapshot_date,
        "generated_at": generated_at,
        "stats": stats,
        "categories": category_items,
        "items": items,
    }


def build_manifest(
    *,
    generated_at: str,
    status: str,
    message: str,
    previous: dict[str, Any] | None,
    available_dates: list[str],
    retention_days: int,
    source: str,
) -> dict[str, Any]:
    previous_manifest = previous or {}
    latest_date = available_dates[0] if available_dates else None

    if status == "success" and latest_date:
        last_success_date = latest_date
        last_success_at = generated_at
    else:
        last_success_date = previous_manifest.get("last_success_date")
        last_success_at = previous_manifest.get("last_success_at")

    return {
        "generated_at": generated_at,
        "last_attempt_at": generated_at,
        "last_success_date": last_success_date,
        "last_success_at": last_success_at,
        "status": status,
        "source": source,
        "message": message,
        "retention_days": int(retention_days),
        "available_dates": available_dates,
        "default_filters": DEFAULT_FILTERS,
    }
