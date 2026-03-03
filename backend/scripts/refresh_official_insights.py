from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.official_insights.builder import (  # noqa: E402
    build_official_insights_payload,
    derive_style_trends_from_keywords,
    parse_keywords_rows_from_csv,
    parse_keywords_rows_from_json,
    parse_monthly_sales_rows_from_csv,
    parse_monthly_sales_rows_from_json,
    parse_review_topics_from_json,
    parse_style_trend_rows_from_csv,
    parse_style_trend_rows_from_json,
    utc_now_iso,
)
from app.official_insights.sp_api import SPAPIClient, SPAPIConfig, fetch_report_to_file  # noqa: E402

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Refresh official report-backed insights")
    parser.add_argument("--snapshot-date", default="", help="YYYY-MM-DD; default today UTC")
    parser.add_argument(
        "--marketplace-ids",
        default="A1PA6795UKMFR9",
        help="Comma separated marketplace ids used for SP-API report requests",
    )
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--poll-interval-seconds", type=int, default=20)
    parser.add_argument("--report-timeout-seconds", type=int, default=900)

    parser.add_argument(
        "--keywords-report-type",
        default="GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT",
        help="SP-API report type for keyword traffic/conversion",
    )
    parser.add_argument(
        "--keywords-report-period",
        default="MONTH",
        help="reportOptions.reportPeriod for search analytics reports",
    )
    parser.add_argument(
        "--keywords-asins",
        default="",
        help="Comma/space separated ASINs for query performance report; empty = auto from daily snapshot",
    )
    parser.add_argument(
        "--keywords-asin-limit",
        type=int,
        default=20,
        help="Auto-collected ASIN max count when keywords-asins is empty",
    )
    parser.add_argument(
        "--sales-report-type",
        default="GET_SALES_AND_TRAFFIC_REPORT",
        help="SP-API report type for monthly sales",
    )
    parser.add_argument("--sales-date-granularity", default="MONTH")
    parser.add_argument("--sales-asin-granularity", default="CHILD")
    parser.add_argument(
        "--style-report-type",
        default="",
        help="Optional SP-API report type for style trends",
    )

    parser.add_argument("--skip-fetch", action="store_true", help="Do not call SP-API; use local report files only")
    parser.add_argument("--skip-keywords", action="store_true")
    parser.add_argument("--skip-sales", action="store_true")
    parser.add_argument("--skip-reviews", action="store_true")
    parser.add_argument("--skip-style", action="store_true")

    parser.add_argument("--keywords-path", default="", help="Local keywords csv/json file path")
    parser.add_argument("--sales-path", default="", help="Local monthly sales csv/json file path")
    parser.add_argument("--review-topics-path", default="", help="Local review topics json file path")
    parser.add_argument("--style-path", default="", help="Local style trends csv/json file path")
    parser.add_argument(
        "--review-asins",
        default="",
        help="Comma/space separated ASINs for Customer Feedback API; empty = auto from daily snapshot",
    )
    parser.add_argument("--review-asin-limit", type=int, default=20)
    parser.add_argument("--review-sort-by", default="MENTIONS")

    parser.add_argument("--raw-output-dir", default=str(PROJECT_ROOT / "data" / "official"))
    parser.add_argument("--insights-output-dir", default=str(WEB_DATA_DIR / "insights"))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when no official rows are generated")
    return parser.parse_args(argv)


def _snapshot_date(raw: str) -> str:
    text = str(raw or "").strip()
    if text:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    return datetime.now(timezone.utc).date().isoformat()


def _parse_marketplace_ids(raw: str) -> list[str]:
    values = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    return values or ["A1PA6795UKMFR9"]


def _parse_asins(raw: str) -> list[str]:
    values = re.split(r"[,\s]+", str(raw or "").strip())
    normalized = [value.strip().upper() for value in values if value and value.strip()]
    result: list[str] = []
    for asin in normalized:
        if len(asin) == 10 and asin.isalnum() and asin not in result:
            result.append(asin)
    return result


def _load_asins_from_daily(snapshot_date: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    path = WEB_DATA_DIR / "daily" / f"{snapshot_date}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    ranked: list[tuple[int, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        asin = str(item.get("asin") or "").strip().upper()
        if len(asin) != 10 or not asin.isalnum():
            continue
        rank = item.get("rank")
        try:
            rank_value = int(rank)
        except (TypeError, ValueError):
            rank_value = 10_000_000
        ranked.append((rank_value, asin))

    ranked.sort(key=lambda pair: pair[0])
    unique: list[str] = []
    for _, asin in ranked:
        if asin in unique:
            continue
        unique.append(asin)
        if len(unique) >= limit:
            break
    return unique


def _build_keywords_report_options(args: Namespace, snapshot_date: str) -> dict[str, Any] | None:
    report_type = str(args.keywords_report_type or "").upper()
    options: dict[str, Any] = {}
    if "SEARCH_QUERY_PERFORMANCE" in report_type or "SEARCH_CATALOG_PERFORMANCE" in report_type:
        options["reportPeriod"] = str(args.keywords_report_period or "MONTH").upper()

    if "SEARCH_QUERY_PERFORMANCE" in report_type:
        asins = _parse_asins(args.keywords_asins)
        if not asins:
            asins = _load_asins_from_daily(snapshot_date, int(args.keywords_asin_limit))
        if asins:
            # SP-API supports multiple ASINs in reportOptions.asin (space separated, size-limited).
            options["asin"] = " ".join(asins)

    return options or None


def _build_sales_report_options(args: Namespace) -> dict[str, Any] | None:
    options: dict[str, Any] = {}
    if args.sales_date_granularity:
        options["dateGranularity"] = str(args.sales_date_granularity).upper()
    if args.sales_asin_granularity:
        options["asinGranularity"] = str(args.sales_asin_granularity).upper()
    return options or None


def _fetch_review_topics_to_file(
    *,
    client: SPAPIClient,
    marketplace_id: str,
    asins: list[str],
    sort_by: str,
    output_path: Path,
) -> None:
    if not asins:
        return

    items: list[dict[str, Any]] = []
    for asin in asins:
        try:
            payload = client.get_item_review_topics(
                asin=asin,
                marketplace_id=marketplace_id,
                sort_by=sort_by,
            )
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        review_topics = payload.get("reviewTopics")
        if not isinstance(review_topics, list):
            continue
        items.append({"asin": asin, "reviewTopics": review_topics})

    if not items:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iso_window(snapshot_date: str, lookback_days: int) -> tuple[str, str]:
    day = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
    start_day = day - timedelta(days=max(1, lookback_days) - 1)
    start = datetime.combine(start_day, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    end = datetime.combine(day, time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return start, end


def _looks_like_json(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lstrip()
    except OSError:
        return False
    return text.startswith("{") or text.startswith("[")


def _load_keywords(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    if _looks_like_json(path):
        return parse_keywords_rows_from_json(path)
    return parse_keywords_rows_from_csv(path)


def _load_monthly_sales(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    if _looks_like_json(path):
        return parse_monthly_sales_rows_from_json(path)
    return parse_monthly_sales_rows_from_csv(path)


def _load_style_trends(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    if _looks_like_json(path):
        return parse_style_trend_rows_from_json(path)
    return parse_style_trend_rows_from_csv(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fetch_reports_if_needed(
    args: Namespace,
    snapshot_date: str,
) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    keywords_path = Path(args.keywords_path).resolve() if args.keywords_path else None
    sales_path = Path(args.sales_path).resolve() if args.sales_path else None
    review_topics_path = Path(args.review_topics_path).resolve() if args.review_topics_path else None
    style_path = Path(args.style_path).resolve() if args.style_path else None

    if args.skip_fetch:
        return keywords_path, sales_path, review_topics_path, style_path

    need_keywords = not args.skip_keywords and (keywords_path is None or not keywords_path.exists())
    need_sales = not args.skip_sales and (sales_path is None or not sales_path.exists())
    need_reviews = not args.skip_reviews and (review_topics_path is None or not review_topics_path.exists())
    need_style = bool(args.style_report_type) and not args.skip_style and (style_path is None or not style_path.exists())
    if not any([need_keywords, need_sales, need_reviews, need_style]):
        return keywords_path, sales_path, review_topics_path, style_path

    config = SPAPIConfig.from_env()
    config.validate()
    client = SPAPIClient(config)

    market_ids = _parse_marketplace_ids(args.marketplace_ids)
    start_time, end_time = _iso_window(snapshot_date, args.lookback_days)
    raw_dir = Path(args.raw_output_dir) / snapshot_date
    raw_dir.mkdir(parents=True, exist_ok=True)

    if need_keywords:
        keywords_path = raw_dir / "keywords_report.json"
        fetch_report_to_file(
            client=client,
            report_type=args.keywords_report_type,
            marketplace_ids=market_ids,
            output_path=keywords_path,
            data_start_time=start_time,
            data_end_time=end_time,
            report_options=_build_keywords_report_options(args, snapshot_date),
            timeout_seconds=args.report_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

    if need_sales:
        sales_path = raw_dir / "monthly_sales_report.json"
        fetch_report_to_file(
            client=client,
            report_type=args.sales_report_type,
            marketplace_ids=market_ids,
            output_path=sales_path,
            data_start_time=start_time,
            data_end_time=end_time,
            report_options=_build_sales_report_options(args),
            timeout_seconds=args.report_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

    if need_reviews:
        review_topics_path = raw_dir / "review_topics.json"
        review_asins = _parse_asins(args.review_asins)
        if not review_asins:
            review_asins = _load_asins_from_daily(snapshot_date, int(args.review_asin_limit))
        if review_asins:
            _fetch_review_topics_to_file(
                client=client,
                marketplace_id=market_ids[0],
                asins=review_asins,
                sort_by=str(args.review_sort_by or "MENTIONS").upper(),
                output_path=review_topics_path,
            )

    if need_style:
        style_path = raw_dir / "style_trends_report.csv"
        fetch_report_to_file(
            client=client,
            report_type=args.style_report_type,
            marketplace_ids=market_ids,
            output_path=style_path,
            data_start_time=start_time,
            data_end_time=end_time,
            timeout_seconds=args.report_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

    return keywords_path, sales_path, review_topics_path, style_path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot_date = _snapshot_date(args.snapshot_date)

    try:
        keywords_path, sales_path, review_topics_path, style_path = _fetch_reports_if_needed(args, snapshot_date)
    except Exception:  # noqa: BLE001
        if args.strict:
            return 1
        keywords_path = Path(args.keywords_path).resolve() if args.keywords_path else None
        sales_path = Path(args.sales_path).resolve() if args.sales_path else None
        review_topics_path = Path(args.review_topics_path).resolve() if args.review_topics_path else None
        style_path = Path(args.style_path).resolve() if args.style_path else None

    keywords = [] if args.skip_keywords else _load_keywords(keywords_path)
    monthly_sales = [] if args.skip_sales else _load_monthly_sales(sales_path)
    review_topics = [] if args.skip_reviews else (parse_review_topics_from_json(review_topics_path) if review_topics_path else [])
    style_trends = [] if args.skip_style else _load_style_trends(style_path)
    if not style_trends and keywords:
        style_trends = derive_style_trends_from_keywords(keywords)

    total_rows = len(keywords) + len(monthly_sales) + len(review_topics) + len(style_trends)
    if args.strict and total_rows == 0:
        return 1

    payload = build_official_insights_payload(
        snapshot_date=snapshot_date,
        generated_at=utc_now_iso(),
        keywords=keywords,
        monthly_sales=monthly_sales,
        review_topics=review_topics,
        style_trends=style_trends,
    )
    output_path = Path(args.insights_output_dir) / f"{snapshot_date}.json"
    _write_json(output_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
