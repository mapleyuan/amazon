from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.official_insights.builder import (  # noqa: E402
    build_official_insights_payload,
    parse_keywords_rows_from_csv,
    parse_monthly_sales_rows_from_csv,
    parse_review_topics_from_json,
    parse_style_trend_rows_from_csv,
    utc_now_iso,
)

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _detect_snapshot_date(explicit: str, daily_path: str) -> str:
    if explicit:
        return explicit
    if daily_path:
        return Path(daily_path).stem
    return datetime.now(timezone.utc).date().isoformat()


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Build official insights payload for static web data")
    parser.add_argument("--snapshot-date", default="", help="YYYY-MM-DD")
    parser.add_argument(
        "--daily-path",
        default="",
        help="Optional path to daily snapshot json, snapshot date inferred from filename when omitted",
    )
    parser.add_argument("--keywords-csv", default="", help="Official keyword report csv path")
    parser.add_argument("--monthly-sales-csv", default="", help="Official monthly sales report csv path")
    parser.add_argument("--review-topics-json", default="", help="Official review topics json path")
    parser.add_argument("--style-trends-csv", default="", help="Official style trend csv path")
    parser.add_argument(
        "--output-dir",
        default=str(WEB_DATA_DIR / "insights"),
        help="Output directory for insights json files",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when all inputs are empty or missing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot_date = _detect_snapshot_date(args.snapshot_date, args.daily_path)

    keywords = parse_keywords_rows_from_csv(Path(args.keywords_csv)) if args.keywords_csv else []
    monthly_sales = parse_monthly_sales_rows_from_csv(Path(args.monthly_sales_csv)) if args.monthly_sales_csv else []
    review_topics = parse_review_topics_from_json(Path(args.review_topics_json)) if args.review_topics_json else []
    style_trends = parse_style_trend_rows_from_csv(Path(args.style_trends_csv)) if args.style_trends_csv else []

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

    out_dir = Path(args.output_dir)
    output_path = out_dir / f"{snapshot_date}.json"
    _write_json(output_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
