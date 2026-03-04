from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote_plus
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.crawler.adapters import SITE_BASE  # noqa: E402
from app.crawler.client import fetch_html  # noqa: E402
from app.official_insights.builder import build_official_insights_payload, utc_now_iso  # noqa: E402
from app.official_insights.public_keywords import (  # noqa: E402
    build_public_keyword_rows,
    extract_candidate_keywords,
    parse_search_signals,
)

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Refresh keyword insights from public search pages")
    parser.add_argument("--snapshot-date", default="", help="YYYY-MM-DD; default today UTC")
    parser.add_argument("--site", default="amazon.com", choices=sorted(SITE_BASE.keys()))
    parser.add_argument("--keywords", default="", help="Comma/space separated keywords; empty=auto from daily titles")
    parser.add_argument("--keyword-limit", type=int, default=20)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when no keyword rows can be generated")
    parser.add_argument("--insights-output-dir", default=str(WEB_DATA_DIR / "insights"))
    return parser.parse_args(argv)


def _snapshot_date(raw: str) -> str:
    text = str(raw or "").strip()
    if text:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    return datetime.now(timezone.utc).date().isoformat()


def _parse_keywords(raw: str) -> list[str]:
    values = re.split(r"[,\n]+", str(raw or "").strip())
    results: list[str] = []
    for value in values:
        for maybe in re.split(r"\s{2,}", value):
            keyword = str(maybe or "").strip().lower()
            if not keyword:
                continue
            if keyword in results:
                continue
            results.append(keyword)
    return results


def _load_daily_items(snapshot_date: str) -> list[dict[str, Any]]:
    path = WEB_DATA_DIR / "daily" / f"{snapshot_date}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    return items if isinstance(items, list) else []


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _search_url(site: str, keyword: str) -> str:
    return f"{SITE_BASE[site].rstrip('/')}/s?k={quote_plus(keyword)}"


def _build_asin_sales_map(items: list[dict[str, Any]]) -> dict[str, int]:
    by_asin: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        asin = str(item.get("asin") or "").strip().upper()
        if len(asin) != 10 or not asin.isalnum():
            continue
        sales_raw = item.get("sales_month")
        try:
            sales = int(float(sales_raw))
        except (TypeError, ValueError):
            sales = 0
        current = by_asin.get(asin, 0)
        if sales > current:
            by_asin[asin] = sales
    return by_asin


def _source_components(raw_source: str) -> set[str]:
    source = str(raw_source or "").strip()
    if not source:
        return set()
    if source == "mixed_reports_public_reviews":
        return {"official_reports", "public_reviews"}
    if "+" in source:
        return {part.strip() for part in source.split("+") if part.strip()}
    return {source}


def _compose_source(components: set[str]) -> str:
    if not components:
        return ""
    if components == {"official_reports", "public_reviews"}:
        return "mixed_reports_public_reviews"
    if len(components) == 1:
        return next(iter(components))
    return "+".join(sorted(components))


def _should_keep_existing_keywords(existing: dict[str, Any], source_components: set[str]) -> bool:
    keywords = existing.get("keywords") if isinstance(existing.get("keywords"), list) else []
    return bool(keywords) and "official_reports" in source_components


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot_date = _snapshot_date(args.snapshot_date)
    output_path = Path(args.insights_output_dir) / f"{snapshot_date}.json"

    daily_items = _load_daily_items(snapshot_date)
    input_keywords = _parse_keywords(args.keywords)
    if input_keywords:
        keywords = input_keywords[: max(1, int(args.keyword_limit))]
    else:
        keywords = extract_candidate_keywords(daily_items, max_keywords=max(1, int(args.keyword_limit)))

    asin_sales = _build_asin_sales_map(daily_items)

    keyword_signals: list[dict[str, Any]] = []
    for keyword in keywords:
        url = _search_url(args.site, keyword)
        try:
            text = fetch_html(url, site=args.site, timeout=20, max_bytes=900_000)
        except Exception:  # noqa: BLE001
            continue

        parsed = parse_search_signals(text)
        if parsed.get("result_count") is None and not parsed.get("top_asins"):
            continue
        keyword_signals.append({"keyword": keyword, **parsed})

    public_keyword_rows = build_public_keyword_rows(keyword_signals, asin_sales)

    existing = _load_json(output_path) or {}
    source_components = _source_components(str(existing.get("source") or ""))
    keep_existing = _should_keep_existing_keywords(existing, source_components)

    existing_keywords = existing.get("keywords") if isinstance(existing.get("keywords"), list) else []
    existing_monthly_sales = existing.get("monthly_sales") if isinstance(existing.get("monthly_sales"), list) else []
    existing_review_topics = existing.get("review_topics") if isinstance(existing.get("review_topics"), list) else []
    existing_style_trends = existing.get("style_trends") if isinstance(existing.get("style_trends"), list) else []

    has_public_keywords = bool(public_keyword_rows)
    if keep_existing:
        final_keywords = existing_keywords
    elif has_public_keywords:
        final_keywords = public_keyword_rows
    else:
        final_keywords = existing_keywords

    if has_public_keywords:
        source_components.add("public_search_keywords")

    total_rows = len(final_keywords) + len(existing_monthly_sales) + len(existing_review_topics) + len(existing_style_trends)
    if total_rows == 0:
        return 1 if args.strict else 0

    payload = build_official_insights_payload(
        snapshot_date=snapshot_date,
        generated_at=utc_now_iso(),
        keywords=final_keywords,
        monthly_sales=existing_monthly_sales,
        review_topics=existing_review_topics,
        style_trends=existing_style_trends,
    )
    payload["source"] = _compose_source(source_components)

    _write_json(output_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
