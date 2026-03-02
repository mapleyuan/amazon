from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    db_path: str
    host: str
    port: int
    cron_hour_utc: int
    cron_minute_utc: int
    mock_crawl: bool
    manual_limit_per_site: int
    detail_enrich_limit: int
    crawl_category_limit: int


def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("AMAZON_DB_PATH", "data/amazon.db"),
        host=os.environ.get("AMAZON_HOST", "127.0.0.1"),
        port=int(os.environ.get("AMAZON_PORT", "8000")),
        cron_hour_utc=int(os.environ.get("AMAZON_CRON_HOUR_UTC", "2")),
        cron_minute_utc=int(os.environ.get("AMAZON_CRON_MINUTE_UTC", "0")),
        mock_crawl=os.environ.get("AMAZON_MOCK_CRAWL", "0") == "1",
        manual_limit_per_site=int(os.environ.get("AMAZON_MANUAL_LIMIT_PER_SITE", "3")),
        detail_enrich_limit=int(os.environ.get("AMAZON_DETAIL_ENRICH_LIMIT", "0")),
        crawl_category_limit=int(os.environ.get("AMAZON_CRAWL_CATEGORY_LIMIT", "20")),
    )
