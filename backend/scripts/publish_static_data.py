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
    return crawl_all_rows_for_targets(sites=SITES, boards=BOARDS)


def crawl_all_rows_for_targets(*, sites: list[str], boards: list[str]) -> tuple[str, list[dict[str, Any]]]:
    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for site in sites:
        for board_type in boards:
            board_rows = crawl_site_board(site, board_type)
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


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Publish static daily data for GitHub Pages")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--sites", default="", help="Comma separated sites, e.g. amazon.com,amazon.co.jp")
    parser.add_argument(
        "--boards",
        default="",
        help="Comma separated boards, e.g. best_sellers,new_releases,movers_and_shakers",
    )
    args = parser.parse_args(argv or [])

    generated_at = _utc_now()
    previous_manifest = _read_json(_manifest_path())
    existing_dates = _collect_existing_dates(previous_manifest)
    retention_days = max(1, int(args.retention_days))
    sites = _parse_csv_values(args.sites, SITES, "sites")
    boards = _parse_csv_values(args.boards, BOARDS, "boards")

    status = "success"
    message = ""
    available_dates = existing_dates

    try:
        snapshot_date, rows = crawl_all_rows_for_targets(sites=sites, boards=boards)
        if not rows:
            raise RuntimeError("crawl returned no rows")

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
    )
    _write_json(_manifest_path(), manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
