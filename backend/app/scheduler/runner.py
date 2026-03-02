from __future__ import annotations

from datetime import datetime, timezone
import threading
import time

from app.core.settings import get_settings
from app.jobs.service import trigger_daily_full


def build_scheduler_jobs() -> list[dict]:
    settings = get_settings()
    return [
        {
            "id": "daily_full_crawl",
            "cron": f"{settings.cron_minute_utc} {settings.cron_hour_utc} * * *",
            "handler": "trigger_daily_full",
        }
    ]


class DailyScheduler:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_date: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            settings = get_settings()
            today = now.date().isoformat()

            if (
                now.hour == settings.cron_hour_utc
                and now.minute == settings.cron_minute_utc
                and self._last_run_date != today
            ):
                trigger_daily_full()
                self._last_run_date = today

            self._stop_event.wait(30)
