from __future__ import annotations

import json
from datetime import datetime, timezone
import sqlite3


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def create_job(conn: sqlite3.Connection, *, site: str, board_type: str, trigger_type: str) -> dict:
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO crawl_jobs (site, board_type, trigger_type, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (site, board_type, trigger_type, "pending", now),
    )
    conn.commit()
    return get_job_by_id(conn, cur.lastrowid)


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> dict:
    row = conn.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else {}


def list_jobs(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM crawl_jobs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_job_status(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    status: str,
    snapshot_date: str | None = None,
    error_message: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    now = utc_now_iso()
    updates = ["status = ?"]
    values: list[object] = [status]

    if snapshot_date is not None:
        updates.append("snapshot_date = ?")
        values.append(snapshot_date)
    if error_message is not None:
        updates.append("error_message = ?")
        values.append(error_message)
    if started:
        updates.append("started_at = ?")
        values.append(now)
    if finished:
        updates.append("finished_at = ?")
        values.append(now)

    values.append(job_id)
    conn.execute(f"UPDATE crawl_jobs SET {', '.join(updates)} WHERE id = ?", tuple(values))
    conn.commit()


def count_manual_jobs_today(conn: sqlite3.Connection, site: str) -> int:
    today = utc_today()
    row = conn.execute(
        """
        SELECT COUNT(1) AS cnt
        FROM crawl_jobs
        WHERE trigger_type = 'manual' AND site = ? AND substr(created_at, 1, 10) = ?
        """,
        (site, today),
    ).fetchone()
    return int(row["cnt"] if row else 0)


def log_export(conn: sqlite3.Connection, *, file_type: str, filters: dict, user_id: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO export_logs (user_id, filter_json, file_type, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, json.dumps(filters, ensure_ascii=False), file_type, utc_now_iso()),
    )
    conn.commit()
