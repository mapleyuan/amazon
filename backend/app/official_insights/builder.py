from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


_STYLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "for",
    "with",
    "in",
    "on",
    "of",
    "to",
    "new",
    "best",
    "seller",
    "sellers",
    "amazon",
    "set",
    "pack",
    "piece",
    "pieces",
    "home",
    "kitchen",
    "holder",
}
_STYLE_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,}|[\u4e00-\u9fff]{2,}", re.IGNORECASE)

_KEYWORD_KEYS = [
    "keyword",
    "search_term",
    "search term",
    "search_query",
    "search query",
    "searchQuery",
    "query",
    "customer_search_term",
    "searchQueryData.searchQuery",
    "searchQueryData.searchTerm",
    "searchTerm",
]
_KEYWORD_MONTH_KEYS = [
    "month",
    "year_month",
    "yearMonth",
    "date",
    "start_date",
    "startDate",
    "dataStartTime",
    "reportingPeriod.startDate",
]
_KEYWORD_ASIN_KEYS = [
    "asin",
    "child_asin",
    "childAsin",
    "parent_asin",
    "parentAsin",
    "item_asin",
    "itemAsin",
]
_KEYWORD_IMPRESSION_KEYS = [
    "impressions",
    "search_query_volume",
    "search term impression rank",
    "view_count",
    "impressionData.asinImpressionCount",
    "impressionData.totalQueryImpressionCount",
    "asinImpressionCount",
    "totalQueryImpressionCount",
]
_KEYWORD_CLICK_KEYS = [
    "clicks",
    "click_count",
    "click-throughs",
    "clickData.asinClickCount",
    "clickData.totalClickCount",
    "asinClickCount",
    "totalClickCount",
]
_KEYWORD_CART_ADD_KEYS = [
    "cart_adds",
    "add_to_cart",
    "cart_add_count",
    "cartAddData.asinCartAddCount",
    "cartAddData.totalCartAddCount",
    "asinCartAddCount",
    "totalCartAddCount",
]
_KEYWORD_PURCHASE_KEYS = [
    "purchases",
    "purchase_count",
    "orders",
    "ordered_units",
    "purchaseData.asinPurchaseCount",
    "purchaseData.totalPurchaseCount",
    "asinPurchaseCount",
    "totalPurchaseCount",
]
_KEYWORD_CTR_KEYS = ["ctr", "clickThroughRate", "clickData.asinClickThroughRate", "clickData.totalClickThroughRate"]
_KEYWORD_CVR_KEYS = ["cvr", "conversionRate", "purchaseData.asinConversionRate", "purchaseData.totalConversionRate"]

_SALES_ASIN_KEYS = [
    "asin",
    "child_asin",
    "childAsin",
    "parent_asin",
    "parentAsin",
    "item_asin",
    "itemAsin",
]
_SALES_MONTH_KEYS = ["month", "year_month", "yearMonth", "date", "start_date", "startDate"]
_SALES_UNITS_KEYS = [
    "units",
    "units_ordered",
    "unitsOrdered",
    "orderedUnits",
    "ordered_units",
    "purchases",
    "order_items",
    "quantity",
    "salesByDate.unitsOrdered",
    "salesByAsin.unitsOrdered",
]
_SALES_REVENUE_KEYS = [
    "revenue",
    "sales",
    "ordered_product_sales",
    "ordered_product_sales_amount",
    "orderedProductSales.amount",
    "salesByDate.orderedProductSales.amount",
    "salesByAsin.orderedProductSales.amount",
]


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
    if text.endswith("%"):
        text = text[:-1]
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
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


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def _dict_get_ci(payload: dict[str, Any], key: str) -> Any:
    if key in payload:
        return payload[key]
    target = _normalize_key(key)
    for candidate, value in payload.items():
        if _normalize_key(candidate) == target:
            return value
    return None


def _path_get(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in str(path or "").split("."):
        if not isinstance(current, dict):
            return None
        current = _dict_get_ci(current, part)
    return current


def _first_value(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if "." in key:
            value = _path_get(payload, key)
        else:
            value = _dict_get_ci(payload, key)

        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _iter_dict_nodes(payload: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            nodes.append(node)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(payload)
    return nodes


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
    if len(text) >= 7:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return f"{parsed.year:04d}-{parsed.month:02d}"
        except ValueError:
            pass
    if len(text) >= 7 and text[0:4].isdigit() and text[4] == "-" and text[5:7].isdigit():
        return text[:7]
    return ""


def _keyword_row_from_mapping(payload: dict[str, Any]) -> dict[str, Any] | None:
    keyword = str(_first_value(payload, _KEYWORD_KEYS) or "").strip()
    if not keyword:
        return None

    impressions = _to_int(_first_value(payload, _KEYWORD_IMPRESSION_KEYS))
    clicks = _to_int(_first_value(payload, _KEYWORD_CLICK_KEYS))
    purchases = _to_int(_first_value(payload, _KEYWORD_PURCHASE_KEYS))
    cart_adds = _to_int(_first_value(payload, _KEYWORD_CART_ADD_KEYS))
    month = _to_month_key(str(_first_value(payload, _KEYWORD_MONTH_KEYS) or ""))
    asin = str(_first_value(payload, _KEYWORD_ASIN_KEYS) or "").strip()

    ctr = _to_float(_first_value(payload, _KEYWORD_CTR_KEYS))
    cvr = _to_float(_first_value(payload, _KEYWORD_CVR_KEYS))
    if ctr is None and impressions and impressions > 0 and clicks is not None:
        ctr = clicks / impressions
    if cvr is None and clicks and clicks > 0 and purchases is not None:
        cvr = purchases / clicks
    if all(metric is None for metric in [impressions, clicks, purchases, cart_adds, ctr, cvr]):
        return None

    row = {
        "keyword": keyword,
        "impressions": impressions,
        "clicks": clicks,
        "cart_adds": cart_adds,
        "purchases": purchases,
        "ctr": ctr,
        "cvr": cvr,
        "month": month or None,
    }
    if asin:
        row["asin"] = asin
    return row


def parse_keywords_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(path)
    parsed: list[dict[str, Any]] = []

    for row in rows:
        item = parse_keywords_rows_from_csv_row(row)
        if item:
            parsed.append(item)
    return parsed


def parse_keywords_rows_from_json(path: Path) -> list[dict[str, Any]]:
    raw = _read_json_payload(path)
    if raw is None:
        return []

    if isinstance(raw, dict):
        candidates: list[dict[str, Any]] = [raw]
        for key in ("items", "rows", "keywords", "dataByAsin", "records"):
            value = _dict_get_ci(raw, key)
            if isinstance(value, list):
                candidates.extend([item for item in value if isinstance(item, dict)])
    elif isinstance(raw, list):
        candidates = [item for item in raw if isinstance(item, dict)]
    else:
        candidates = []

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for entry in candidates:
        for node in _iter_dict_nodes(entry):
            parsed = _keyword_row_from_mapping(node)
            if not parsed:
                continue

            dedupe_key = (
                parsed.get("keyword"),
                parsed.get("month"),
                parsed.get("asin", ""),
                parsed.get("impressions"),
                parsed.get("clicks"),
                parsed.get("purchases"),
                parsed.get("cart_adds"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(parsed)
    return rows


def parse_keywords_rows_from_csv_row(row: dict[str, str]) -> dict[str, Any] | None:
    payload = {str(k): "" if v is None else str(v) for k, v in row.items()}
    return _keyword_row_from_mapping(payload)


def _monthly_sales_row_from_mapping(payload: dict[str, Any]) -> dict[str, Any] | None:
    month = _to_month_key(str(_first_value(payload, _SALES_MONTH_KEYS) or ""))
    if not month:
        return None

    asin = str(_first_value(payload, _SALES_ASIN_KEYS) or "").strip()
    units = _to_int(_first_value(payload, _SALES_UNITS_KEYS))
    revenue = _to_float(_first_value(payload, _SALES_REVENUE_KEYS))
    return {
        "asin": asin,
        "month": month,
        "units": units,
        "revenue": revenue,
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

    if isinstance(raw, dict):
        candidates: list[dict[str, Any]] = [raw]
        for key in ("items", "rows", "salesByDate", "salesAndTrafficByDate", "salesAndTrafficByAsin"):
            value = _dict_get_ci(raw, key)
            if isinstance(value, list):
                candidates.extend([item for item in value if isinstance(item, dict)])
    elif isinstance(raw, list):
        candidates = [item for item in raw if isinstance(item, dict)]
    else:
        candidates = []

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for entry in candidates:
        for node in [entry]:
            item = _monthly_sales_row_from_mapping(node)
            if not item:
                continue
            dedupe_key = (item.get("asin"), item.get("month"), item.get("units"), item.get("revenue"))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(item)
    return rows


def parse_monthly_sales_row(row: dict[str, str]) -> dict[str, Any] | None:
    payload = {str(k): "" if v is None else str(v) for k, v in row.items()}
    return _monthly_sales_row_from_mapping(payload)


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
        candidates = _dict_get_ci(raw, "items") or _dict_get_ci(raw, "rows") or _dict_get_ci(raw, "style_trends") or []
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


def _normalize_topic(item: dict[str, Any], *, mentions_override: Any = None) -> dict[str, Any] | None:
    topic = str(item.get("topic") or item.get("name") or item.get("topicName") or "").strip()
    if not topic:
        return None
    mentions = _to_int(
        mentions_override
        if mentions_override is not None
        else item.get("mentions") or item.get("count") or item.get("mentionCount")
    )
    score = _to_float(item.get("score") or item.get("sentimentScore") or item.get("starRatingImpact"))
    return {"topic": topic, "score": score, "mentions": mentions}


def parse_review_topics_from_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        payload = raw.get("items", [])
    elif isinstance(raw, dict) and isinstance(raw.get("reviewTopics"), list):
        payload = [raw]
    elif isinstance(raw, list):
        payload = raw
    else:
        payload = []

    parsed: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue

        asin = str(
            entry.get("asin")
            or entry.get("child_asin")
            or entry.get("childAsin")
            or entry.get("itemAsin")
            or ""
        ).strip()
        if not asin:
            continue

        positive: list[dict[str, Any]] = []
        negative: list[dict[str, Any]] = []

        explicit_positive = entry.get("positive_topics") or entry.get("positiveTopics") or []
        explicit_negative = entry.get("negative_topics") or entry.get("negativeTopics") or []

        if isinstance(explicit_positive, list):
            for item in explicit_positive:
                if isinstance(item, str):
                    positive.append({"topic": item, "score": None, "mentions": None})
                elif isinstance(item, dict):
                    normalized = _normalize_topic(item)
                    if normalized:
                        positive.append(normalized)

        if isinstance(explicit_negative, list):
            for item in explicit_negative:
                if isinstance(item, str):
                    negative.append({"topic": item, "score": None, "mentions": None})
                elif isinstance(item, dict):
                    normalized = _normalize_topic(item)
                    if normalized:
                        negative.append(normalized)

        if not positive and not negative:
            review_topics = entry.get("reviewTopics")
            if isinstance(review_topics, list):
                for topic_item in review_topics:
                    if not isinstance(topic_item, dict):
                        continue
                    mentions_obj = topic_item.get("topicMentions") if isinstance(topic_item.get("topicMentions"), dict) else {}
                    positive_mentions = _to_int(
                        topic_item.get("positiveMentions")
                        or topic_item.get("positiveCount")
                        or mentions_obj.get("positive")
                    )
                    negative_mentions = _to_int(
                        topic_item.get("negativeMentions")
                        or topic_item.get("negativeCount")
                        or mentions_obj.get("negative")
                    )

                    if positive_mentions and positive_mentions > 0:
                        normalized = _normalize_topic(topic_item, mentions_override=positive_mentions)
                        if normalized:
                            positive.append(normalized)
                    if negative_mentions and negative_mentions > 0:
                        normalized = _normalize_topic(topic_item, mentions_override=negative_mentions)
                        if normalized:
                            negative.append(normalized)

        parsed.append(
            {
                "asin": asin,
                "positive_topics": positive,
                "negative_topics": negative,
            }
        )
    return parsed


def _extract_style_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _STYLE_TOKEN_RE.finditer(str(text or "").lower()):
        token = match.group(0).strip("-")
        if not token or token in _STYLE_STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def derive_style_trends_from_keywords(
    keywords: list[dict[str, Any]],
    *,
    top_n_per_month: int = 20,
) -> list[dict[str, Any]]:
    month_token_scores: dict[str, dict[str, float]] = {}
    for row in keywords:
        if not isinstance(row, dict):
            continue
        month = _to_month_key(str(row.get("month") or row.get("startDate") or row.get("date") or ""))
        keyword = str(row.get("keyword") or "").strip()
        if not month or not keyword:
            continue

        weight = (
            _to_float(row.get("impressions"))
            or _to_float(row.get("clicks"))
            or _to_float(row.get("purchases"))
            or 1.0
        )
        token_scores = month_token_scores.setdefault(month, {})
        for token in _extract_style_tokens(keyword):
            token_scores[token] = token_scores.get(token, 0.0) + float(weight)

    trends: list[dict[str, Any]] = []
    for month in sorted(month_token_scores.keys()):
        token_scores = month_token_scores[month]
        ranked = sorted(token_scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_n_per_month)]
        for token, score in ranked:
            trends.append({"style": token, "month": month, "score": round(score, 2)})
    return trends


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
