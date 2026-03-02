from __future__ import annotations

from datetime import datetime, timezone
import threading

from app.core.settings import get_settings
from app.crawler.service import crawl_site_board
from app.db.connection import get_connection
from app.jobs.repository import count_manual_jobs_today, create_job, list_jobs as repo_list_jobs, update_job_status
from app.jobs.schemas import JobRunRequest
from app.ranking.service import upsert_rank_snapshot

SITES = ["amazon.com", "amazon.co.jp", "amazon.co.uk"]
BOARDS = ["best_sellers", "new_releases", "movers_and_shakers"]


def _run_job(job_id: int, site: str, board_type: str) -> None:
    conn = get_connection()
    snapshot_date = datetime.now(timezone.utc).date().isoformat()

    try:
        update_job_status(conn, job_id=job_id, status="running", snapshot_date=snapshot_date, started=True)
        rows = crawl_site_board(site, board_type)
        upsert_rank_snapshot(rows, snapshot_date=snapshot_date, job_id=job_id)
        update_job_status(conn, job_id=job_id, status="success", finished=True)
    except Exception as exc:  # noqa: BLE001
        update_job_status(conn, job_id=job_id, status="failed", error_message=str(exc), finished=True)


def create_manual_job(payload: JobRunRequest) -> dict:
    conn = get_connection()
    settings = get_settings()

    manual_count = count_manual_jobs_today(conn, payload.site)
    if manual_count >= settings.manual_limit_per_site:
        raise ValueError(f"manual trigger limit reached for site {payload.site}")

    job = create_job(conn, site=payload.site, board_type=payload.board_type, trigger_type="manual")

    if settings.mock_crawl:
        # Keep tests deterministic and avoid background work after env teardown.
        _run_job(int(job["id"]), payload.site, payload.board_type)
    else:
        thread = threading.Thread(
            target=_run_job,
            kwargs={"job_id": int(job["id"]), "site": payload.site, "board_type": payload.board_type},
            daemon=True,
        )
        thread.start()

    return job


def list_jobs(limit: int = 100) -> list[dict]:
    conn = get_connection()
    return repo_list_jobs(conn, limit=limit)


def trigger_daily_full() -> list[dict]:
    conn = get_connection()
    settings = get_settings()
    created: list[dict] = []

    for site in SITES:
        for board_type in BOARDS:
            job = create_job(conn, site=site, board_type=board_type, trigger_type="cron")
            created.append(job)
            if settings.mock_crawl:
                _run_job(int(job["id"]), site, board_type)
            else:
                thread = threading.Thread(
                    target=_run_job,
                    kwargs={"job_id": int(job["id"]), "site": site, "board_type": board_type},
                    daemon=True,
                )
                thread.start()

    return created
