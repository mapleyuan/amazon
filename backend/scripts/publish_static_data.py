from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.crawler.service import crawl_site_board
from app.jobs.service import BOARDS, SITES
from app.static_data.publisher import build_daily_payload, build_manifest, merge_available_dates

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"
DEFAULT_RETENTION_DAYS = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _manifest_path() -> Path:
    return WEB_DATA_DIR / "manifest.json"


def _daily_dir() -> Path:
    return WEB_DATA_DIR / "daily"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _collect_existing_dates(previous: dict[str, Any]) -> list[str]:
    dates: set[str] = set()
    previous_dates = previous.get("available_dates")
    if isinstance(previous_dates, list):
        dates.update(str(item) for item in previous_dates if item)

    daily_dir = _daily_dir()
    if daily_dir.exists():
        for file in daily_dir.glob("*.json"):
            dates.add(file.stem)

    return sorted(dates, reverse=True)


def _cleanup_old_daily_files(allowed_dates: list[str]) -> None:
    daily_dir = _daily_dir()
    if not daily_dir.exists():
        return
    allowed = set(allowed_dates)
    for file in daily_dir.glob("*.json"):
        if file.stem not in allowed:
            file.unlink(missing_ok=True)


def crawl_all_rows() -> tuple[str, list[dict[str, Any]]]:
    return crawl_all_rows_for_targets(
        sites=SITES,
        boards=BOARDS,
        category_keywords=[],
        category_urls=[],
    )


def crawl_all_rows_for_targets(
    *,
    sites: list[str],
    boards: list[str],
    category_keywords: list[str],
    category_urls: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for site in sites:
        for board_type in boards:
            board_rows = crawl_site_board(
                site,
                board_type,
                category_keywords=category_keywords,
                category_urls=category_urls,
            )
            for row in board_rows:
                normalized = dict(row)
                normalized["snapshot_date"] = normalized.get("snapshot_date") or snapshot_date
                key = (
                    normalized.get("site", ""),
                    normalized.get("board_type", ""),
                    normalized.get("category_key", ""),
                    normalized.get("asin", ""),
                    normalized.get("snapshot_date", snapshot_date),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(normalized)

    if rows:
        snapshot_date = str(rows[0].get("snapshot_date") or snapshot_date)
    return snapshot_date, rows


def _parse_csv_values(raw: str, choices: list[str], flag_name: str) -> list[str]:
    if not raw:
        return list(choices)

    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        return list(choices)

    invalid = [item for item in values if item not in choices]
    if invalid:
        raise ValueError(f"invalid {flag_name}: {', '.join(invalid)}")

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _parse_freeform_csv(raw: str) -> list[str]:
    if not raw:
        return []
    values = [item.strip() for item in raw.split(",") if item.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _contains_mock_rows(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        category_key = str(row.get("category_key") or "").strip().lower()
        title = str(row.get("title") or "").strip().lower()
        brand = str(row.get("brand") or "").strip().lower()
        if category_key.startswith("mock-"):
            return True
        if title.startswith("mock "):
            return True
        if brand == "mockbrand":
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Publish static daily data for GitHub Pages")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--sites", default="", help="Comma separated sites, e.g. amazon.com,amazon.co.jp")
    parser.add_argument(
        "--boards",
        default="",
        help="Comma separated boards, e.g. best_sellers,new_releases,movers_and_shakers",
    )
    parser.add_argument(
        "--category-keywords",
        default="",
        help="Comma separated category keywords (match in category label/url), e.g. candle,candlestick,home-decor",
    )
    parser.add_argument(
        "--category-urls",
        default="",
        help="Comma separated absolute category URLs for precise targeting",
    )
    parser.add_argument(
        "--source",
        default="manual",
        choices=["manual", "auto"],
        help="Write update source into manifest",
    )
    parser.add_argument(
        "--fail-on-mock",
        action="store_true",
        help="Treat mock rows as failure so CI does not publish synthetic data",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when status is not success",
    )
    args = parser.parse_args(argv)

    generated_at = _utc_now()
    previous_manifest = _read_json(_manifest_path())
    existing_dates = _collect_existing_dates(previous_manifest)
    retention_days = int(args.retention_days)
    sites = _parse_csv_values(args.sites, SITES, "sites")
    boards = _parse_csv_values(args.boards, BOARDS, "boards")
    category_keywords = _parse_freeform_csv(args.category_keywords)
    category_urls = _parse_freeform_csv(args.category_urls)

    status = "success"
    message = ""
    available_dates = existing_dates

    try:
        snapshot_date, rows = crawl_all_rows_for_targets(
            sites=sites,
            boards=boards,
            category_keywords=category_keywords,
            category_urls=category_urls,
        )
        if not rows:
            raise RuntimeError("crawl returned no rows")
        if args.fail_on_mock and _contains_mock_rows(rows):
            raise RuntimeError("mock rows detected; refusing to publish")

        daily_payload = build_daily_payload(snapshot_date=snapshot_date, generated_at=generated_at, rows=rows)
        daily_path = _daily_dir() / f"{snapshot_date}.json"
        _write_json(daily_path, daily_payload)

        available_dates = merge_available_dates(
            existing=existing_dates,
            new_date=snapshot_date,
            retention_days=retention_days,
        )
        _cleanup_old_daily_files(available_dates)
    except Exception as exc:  # noqa: BLE001
        status = "stale"
        message = str(exc)
        available_dates = merge_available_dates(
            existing=existing_dates,
            new_date=None,
            retention_days=retention_days,
        )
        _cleanup_old_daily_files(available_dates)

    manifest = build_manifest(
        generated_at=generated_at,
        status=status,
        message=message,
        previous=previous_manifest,
        available_dates=available_dates,
        retention_days=retention_days,
        source=args.source,
    )
    _write_json(_manifest_path(), manifest)
    if args.strict and status != "success":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
