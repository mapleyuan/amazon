from __future__ import annotations

from collections import Counter
import html
import re
from typing import Any

_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")
_RESULT_PATTERNS = [
    re.compile(r"of\s+(?:over\s+)?([\d,]+)\s+results?", re.IGNORECASE),
    re.compile(r"([\d,]+)\s+results?\s+for", re.IGNORECASE),
]
_SPONSORED_RE = re.compile(r"\bsponsored\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}")

_STOPWORDS = {
    "about",
    "amazon",
    "best",
    "candle",
    "decor",
    "for",
    "from",
    "home",
    "kitchen",
    "pack",
    "set",
    "the",
    "with",
}


def _clean_text(raw: str) -> str:
    value = html.unescape(str(raw or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_title_tokens(title: str) -> list[str]:
    tokens = []
    for match in _TOKEN_RE.finditer(str(title or "").lower()):
        token = match.group(0)
        if token in _STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def extract_candidate_keywords(items: list[dict[str, Any]], *, max_keywords: int = 20) -> list[str]:
    uni = Counter()
    bi = Counter()

    for item in items:
        if not isinstance(item, dict):
            continue

        title = _clean_text(str(item.get("title") or ""))
        if not title:
            continue

        tokens = _extract_title_tokens(title)
        if not tokens:
            continue

        rank_raw = item.get("rank")
        sales_raw = item.get("sales_month")
        try:
            rank = int(rank_raw)
        except (TypeError, ValueError):
            rank = 100
        try:
            sales = int(float(sales_raw))
        except (TypeError, ValueError):
            sales = 0

        weight = max(1.0, (max(0, sales) ** 0.3) + (25.0 / max(1, rank)))

        unique_tokens = list(dict.fromkeys(tokens))
        for token in unique_tokens:
            uni[token] += weight

        for idx in range(len(unique_tokens) - 1):
            phrase = f"{unique_tokens[idx]} {unique_tokens[idx + 1]}"
            bi[phrase] += weight * 1.2

    ranked = sorted(
        [*uni.items(), *bi.items()],
        key=lambda pair: (-pair[1], pair[0]),
    )

    results: list[str] = []
    seen: set[str] = set()
    for keyword, _ in ranked:
        cleaned = keyword.strip()
        if len(cleaned) < 3:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        results.append(cleaned)
        if len(results) >= max(1, max_keywords):
            break
    return results


def _parse_result_count(text: str) -> int | None:
    matches: list[int] = []
    for pattern in _RESULT_PATTERNS:
        for match in pattern.finditer(text):
            raw = re.sub(r"[^\d]", "", match.group(1) or "")
            if not raw:
                continue
            matches.append(int(raw))
    if not matches:
        return None
    return max(matches)


def parse_search_signals(text: str, *, top_asin_limit: int = 16) -> dict[str, Any]:
    raw = str(text or "")
    result_count = _parse_result_count(raw)
    sponsored_count = len(_SPONSORED_RE.findall(raw))

    top_asins: list[str] = []
    for asin in _ASIN_RE.findall(raw):
        if asin in top_asins:
            continue
        top_asins.append(asin)
        if len(top_asins) >= max(1, top_asin_limit):
            break

    return {
        "result_count": result_count,
        "sponsored_count": sponsored_count,
        "top_asins": top_asins,
    }


def build_public_keyword_rows(
    keyword_signals: list[dict[str, Any]],
    asin_month_sales: dict[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for signal in keyword_signals:
        if not isinstance(signal, dict):
            continue
        keyword = str(signal.get("keyword") or "").strip()
        if not keyword:
            continue

        result_count_raw = signal.get("result_count")
        try:
            result_count = int(result_count_raw) if result_count_raw is not None else 0
        except (TypeError, ValueError):
            result_count = 0

        sponsored_raw = signal.get("sponsored_count")
        try:
            sponsored_count = int(sponsored_raw) if sponsored_raw is not None else 0
        except (TypeError, ValueError):
            sponsored_count = 0

        top_asins = signal.get("top_asins") if isinstance(signal.get("top_asins"), list) else []
        normalized_asins: list[str] = []
        for asin in top_asins:
            value = str(asin or "").strip().upper()
            if len(value) != 10 or not value.isalnum() or value in normalized_asins:
                continue
            normalized_asins.append(value)

        top_count = len(normalized_asins)
        overlap_asins = [asin for asin in normalized_asins if asin in asin_month_sales]
        overlap_count = len(overlap_asins)
        overlap_sales_month = sum(max(0, int(asin_month_sales.get(asin, 0))) for asin in overlap_asins)

        # Public-search conversion proxy: tracked-ASIN overlap ratio on first result page.
        cvr = round(overlap_count / max(1, top_count), 4)

        rows.append(
            {
                "keyword": keyword,
                "impressions": max(1, result_count),
                "clicks": max(1, top_count),
                "purchases": max(0, overlap_count),
                "cvr": cvr,
                "result_count": max(1, result_count),
                "top_asin_count": top_count,
                "top_asin_overlap": overlap_count,
                "overlap_sales_month": overlap_sales_month,
                "sponsored_count": max(0, sponsored_count),
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row.get("impressions") or 0),
            -float(row.get("cvr") or 0),
            str(row.get("keyword") or ""),
        )
    )
    return rows
