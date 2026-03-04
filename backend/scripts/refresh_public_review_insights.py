from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.crawler.adapters import SITE_BASE  # noqa: E402
from app.crawler.client import fetch_html  # noqa: E402
from app.official_insights.builder import build_official_insights_payload, utc_now_iso  # noqa: E402
from app.official_insights.public_reviews import build_review_topic_summary, parse_review_entries  # noqa: E402

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Refresh insights from public Amazon review pages")
    parser.add_argument("--snapshot-date", default="", help="YYYY-MM-DD; default today UTC")
    parser.add_argument("--site", default="amazon.com", choices=sorted(SITE_BASE.keys()))
    parser.add_argument("--asins", default="", help="Comma/space separated ASINs; empty = auto from daily snapshot")
    parser.add_argument("--asin-limit", type=int, default=8)
    parser.add_argument("--pages-per-asin", type=int, default=2)
    parser.add_argument("--top-n-topics", type=int, default=8)
    parser.add_argument("--min-topic-mentions", type=int, default=2)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when no review topics can be generated")
    parser.add_argument("--insights-output-dir", default=str(WEB_DATA_DIR / "insights"))
    return parser.parse_args(argv)


def _snapshot_date(raw: str) -> str:
    text = str(raw or "").strip()
    if text:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    return datetime.now(timezone.utc).date().isoformat()


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


def _review_page_url(site: str, asin: str, page_number: int) -> str:
    base = SITE_BASE[site].rstrip("/")
    return (
        f"{base}/product-reviews/{asin}/"
        f"?reviewerType=all_reviews&sortBy=recent&pageNumber={max(1, int(page_number))}"
    )


def _collect_review_entries_for_asin(site: str, asin: str, pages_per_asin: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max(1, pages_per_asin) + 1):
        url = _review_page_url(site, asin, page)
        try:
            text = fetch_html(url, site=site, timeout=20, max_bytes=800_000)
        except Exception:  # noqa: BLE001
            continue
        parsed = parse_review_entries(text)
        if not parsed and page > 1:
            break
        rows.extend(parsed)
    return rows


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _merge_source(existing_source: str, has_public_reviews: bool) -> str:
    source = str(existing_source or "").strip() or "public_reviews"
    if not has_public_reviews:
        return source
    if source in {"", "public_reviews"}:
        return "public_reviews"
    if source == "official_reports":
        return "mixed_reports_public_reviews"
    if source == "mixed_reports_public_reviews":
        return source
    return f"{source}+public_reviews"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot_date = _snapshot_date(args.snapshot_date)
    output_path = Path(args.insights_output_dir) / f"{snapshot_date}.json"

    asins = _parse_asins(args.asins)
    if not asins:
        asins = _load_asins_from_daily(snapshot_date, int(args.asin_limit))

    existing = _load_json(output_path) or {}
    existing_keywords = existing.get("keywords") if isinstance(existing.get("keywords"), list) else []
    existing_monthly_sales = existing.get("monthly_sales") if isinstance(existing.get("monthly_sales"), list) else []
    existing_style_trends = existing.get("style_trends") if isinstance(existing.get("style_trends"), list) else []
    existing_review_topics = existing.get("review_topics") if isinstance(existing.get("review_topics"), list) else []

    review_topics: list[dict[str, Any]] = []
    for asin in asins:
        entries = _collect_review_entries_for_asin(args.site, asin, int(args.pages_per_asin))
        if not entries:
            continue

        summary = build_review_topic_summary(
            entries,
            top_n=max(1, int(args.top_n_topics)),
            min_mentions=max(1, int(args.min_topic_mentions)),
        )
        if summary["sample_reviews"] <= 0:
            continue

        review_topics.append(
            {
                "asin": asin,
                "sample_reviews": int(summary["sample_reviews"]),
                "total_reviews": int(summary.get("total_reviews") or summary["sample_reviews"]),
                "avg_rating": summary.get("avg_rating"),
                "rating_distribution": summary.get("rating_distribution") or {},
                "sentiment": summary.get("sentiment") or {},
                "positive_topics": summary["positive_topics"],
                "negative_topics": summary["negative_topics"],
                "positive_snippets": summary.get("positive_snippets") or [],
                "negative_snippets": summary.get("negative_snippets") or [],
            }
        )

    has_new_reviews = bool(review_topics)
    final_review_topics = review_topics if has_new_reviews else existing_review_topics

    total_rows = len(existing_keywords) + len(existing_monthly_sales) + len(existing_style_trends) + len(final_review_topics)
    if total_rows == 0:
        return 1 if args.strict else 0

    payload = build_official_insights_payload(
        snapshot_date=snapshot_date,
        generated_at=utc_now_iso(),
        keywords=existing_keywords,
        monthly_sales=existing_monthly_sales,
        review_topics=final_review_topics,
        style_trends=existing_style_trends,
    )
    payload["source"] = _merge_source(str(existing.get("source") or ""), has_new_reviews)

    _write_json(output_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
