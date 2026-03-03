from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return []

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.get_dialect("excel")

    lines = text.splitlines()
    reader = csv.DictReader(lines, dialect=dialect)
    return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in reader]


def _to_int(value: Any) -> int | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _pick(row: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        if key in row and row[key].strip():
            return row[key].strip()
    lowered = {k.lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value and value.strip():
            return value.strip()
    return ""


def _read_json_payload(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _to_month_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = None
    if len(text) >= 7:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return f"{parsed.year:04d}-{parsed.month:02d}"
        except ValueError:
            pass
    if len(text) >= 7 and text[0:4].isdigit() and text[4] == "-" and text[5:7].isdigit():
        return text[:7]
    return ""


def parse_keywords_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(path)
    parsed: list[dict[str, Any]] = []

    for row in rows:
        keyword = _pick(
            row,
            [
                "keyword",
                "search_term",
                "search term",
                "search_query",
                "search query",
                "customer_search_term",
                "query",
            ],
        )
        if not keyword:
            continue

        impressions = _to_int(
            _pick(
                row,
                ["impressions", "search_query_volume", "search term impression rank", "view_count"],
            )
        )
        clicks = _to_int(_pick(row, ["clicks", "click_count", "click-throughs"]))
        purchases = _to_int(_pick(row, ["purchases", "purchase_count", "orders", "ordered_units"]))
        cart_adds = _to_int(_pick(row, ["cart_adds", "add_to_cart", "cart_add_count"]))
        month = _to_month_key(_pick(row, ["month", "year_month", "date", "start_date"]))

        ctr = None
        cvr = None
        if impressions and impressions > 0 and clicks is not None:
            ctr = clicks / impressions
        if clicks and clicks > 0 and purchases is not None:
            cvr = purchases / clicks

        parsed.append(
            {
                "keyword": keyword,
                "impressions": impressions,
                "clicks": clicks,
                "cart_adds": cart_adds,
                "purchases": purchases,
                "ctr": ctr,
                "cvr": cvr,
                "month": month or None,
            }
        )
    return parsed


def parse_keywords_rows_from_json(path: Path) -> list[dict[str, Any]]:
    raw = _read_json_payload(path)
    if raw is None:
        return []

    if isinstance(raw, dict):
        candidates = raw.get("items") or raw.get("rows") or raw.get("keywords") or []
    elif isinstance(raw, list):
        candidates = raw
    else:
        candidates = []

    rows: list[dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        row = {str(k): "" if v is None else str(v) for k, v in entry.items()}
        parsed = parse_keywords_rows_from_csv_row(row)
        if parsed:
            rows.append(parsed)
    return rows


def parse_keywords_rows_from_csv_row(row: dict[str, str]) -> dict[str, Any] | None:
    keyword = _pick(
        row,
        [
            "keyword",
            "search_term",
            "search term",
            "search_query",
            "search query",
            "customer_search_term",
            "query",
        ],
    )
    if not keyword:
        return None

    impressions = _to_int(
        _pick(
            row,
            ["impressions", "search_query_volume", "search term impression rank", "view_count"],
        )
    )
    clicks = _to_int(_pick(row, ["clicks", "click_count", "click-throughs"]))
    purchases = _to_int(_pick(row, ["purchases", "purchase_count", "orders", "ordered_units"]))
    cart_adds = _to_int(_pick(row, ["cart_adds", "add_to_cart", "cart_add_count"]))
    month = _to_month_key(_pick(row, ["month", "year_month", "date", "start_date"]))

    ctr = None
    cvr = None
    if impressions and impressions > 0 and clicks is not None:
        ctr = clicks / impressions
    if clicks and clicks > 0 and purchases is not None:
        cvr = purchases / clicks

    return {
        "keyword": keyword,
        "impressions": impressions,
        "clicks": clicks,
        "cart_adds": cart_adds,
        "purchases": purchases,
        "ctr": ctr,
        "cvr": cvr,
        "month": month or None,
    }


def parse_monthly_sales_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(path)
    parsed: list[dict[str, Any]] = []

    for row in rows:
        item = parse_monthly_sales_row(row)
        if item:
            parsed.append(item)
    return parsed


def parse_monthly_sales_rows_from_json(path: Path) -> list[dict[str, Any]]:
    raw = _read_json_payload(path)
    if raw is None:
        return []

    rows: list[dict[str, Any]] = []

    if isinstance(raw, dict):
        if isinstance(raw.get("items"), list):
            candidates = raw["items"]
        elif isinstance(raw.get("rows"), list):
            candidates = raw["rows"]
        elif isinstance(raw.get("salesByDate"), list):
            # Seller Sales and Traffic style payload (date aggregated)
            for entry in raw["salesByDate"]:
                if not isinstance(entry, dict):
                    continue
                month = _to_month_key(str(entry.get("date") or ""))
                units = _to_int(entry.get("unitsOrdered") or entry.get("orderedUnits"))
                revenue_value = None
                sales_obj = entry.get("orderedProductSales")
                if isinstance(sales_obj, dict):
                    revenue_value = _to_float(sales_obj.get("amount"))
                if not month:
                    continue
                rows.append({"asin": "", "month": month, "units": units, "revenue": revenue_value})
            return rows
        else:
            candidates = []
    elif isinstance(raw, list):
        candidates = raw
    else:
        candidates = []

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        row = {str(k): "" if v is None else str(v) for k, v in entry.items()}
        item = parse_monthly_sales_row(row)
        if item:
            rows.append(item)
    return rows


def parse_monthly_sales_row(row: dict[str, str]) -> dict[str, Any] | None:
    asin = _pick(row, ["asin", "child_asin", "parent_asin", "item_asin"])
    month = _to_month_key(_pick(row, ["month", "year_month", "date", "start_date"]))
    units = _to_int(
        _pick(
            row,
            ["units", "units_ordered", "ordered_units", "purchases", "order_items", "quantity"],
        )
    )
    revenue = _to_float(
        _pick(
            row,
            ["revenue", "sales", "ordered_product_sales", "ordered_product_sales_amount"],
        )
    )
    if not month:
        return None

    return {
        "asin": asin,
        "month": month,
        "units": units,
        "revenue": revenue,
    }


def parse_style_trend_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(path)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        style = _pick(row, ["style", "style_keyword", "trend", "token"])
        month = _to_month_key(_pick(row, ["month", "year_month", "date"]))
        score = _to_float(_pick(row, ["score", "value", "traffic", "impressions"]))
        if not style or not month:
            continue
        parsed.append({"style": style, "month": month, "score": score})
    return parsed


def parse_style_trend_rows_from_json(path: Path) -> list[dict[str, Any]]:
    raw = _read_json_payload(path)
    if raw is None:
        return []
    if isinstance(raw, dict):
        candidates = raw.get("items") or raw.get("rows") or raw.get("style_trends") or []
    elif isinstance(raw, list):
        candidates = raw
    else:
        candidates = []

    parsed: list[dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        style = str(entry.get("style") or entry.get("style_keyword") or entry.get("trend") or "").strip()
        month = _to_month_key(str(entry.get("month") or entry.get("year_month") or entry.get("date") or ""))
        score = _to_float(entry.get("score") or entry.get("value") or entry.get("traffic") or entry.get("impressions"))
        if not style or not month:
            continue
        parsed.append({"style": style, "month": month, "score": score})
    return parsed


def parse_review_topics_from_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        payload = raw.get("items", [])
    elif isinstance(raw, list):
        payload = raw
    else:
        payload = []

    parsed: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue

        asin = str(entry.get("asin") or entry.get("child_asin") or "").strip()
        if not asin:
            continue

        positive = entry.get("positive_topics") or entry.get("positiveTopics") or []
        negative = entry.get("negative_topics") or entry.get("negativeTopics") or []

        def normalize_topics(items: Any) -> list[dict[str, Any]]:
            if not isinstance(items, list):
                return []
            result: list[dict[str, Any]] = []
            for item in items:
                if isinstance(item, str):
                    result.append({"topic": item, "score": None, "mentions": None})
                    continue
                if not isinstance(item, dict):
                    continue
                topic = str(item.get("topic") or item.get("name") or "").strip()
                if not topic:
                    continue
                result.append(
                    {
                        "topic": topic,
                        "score": _to_float(item.get("score") or item.get("sentimentScore")),
                        "mentions": _to_int(item.get("mentions") or item.get("count")),
                    }
                )
            return result

        parsed.append(
            {
                "asin": asin,
                "positive_topics": normalize_topics(positive),
                "negative_topics": normalize_topics(negative),
            }
        )
    return parsed


def build_official_insights_payload(
    *,
    snapshot_date: str,
    generated_at: str | None = None,
    keywords: list[dict[str, Any]],
    monthly_sales: list[dict[str, Any]],
    review_topics: list[dict[str, Any]],
    style_trends: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "snapshot_date": snapshot_date,
        "generated_at": generated_at or utc_now_iso(),
        "source": "official_reports",
        "keywords": keywords,
        "monthly_sales": monthly_sales,
        "review_topics": review_topics,
        "style_trends": style_trends,
        "stats": {
            "keyword_rows": len(keywords),
            "monthly_sales_rows": len(monthly_sales),
            "review_topic_asins": len(review_topics),
            "style_trend_rows": len(style_trends),
        },
    }
