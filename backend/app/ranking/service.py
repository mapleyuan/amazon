from __future__ import annotations

from collections.abc import Iterable

from app.db.connection import get_connection
from app.ranking.repository import insert_category_snapshot, insert_rank_record, upsert_category, upsert_product


def upsert_rank_snapshot(rows: Iterable[dict], *, snapshot_date: str, job_id: int) -> dict:
    conn = get_connection()

    seen: set[tuple[str, str, str, str, str]] = set()
    inserted = 0

    for row in rows:
        dedupe_key = (
            row["site"],
            row["board_type"],
            row["category_key"],
            row["asin"],
            snapshot_date,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        upsert_category(conn, row)
        upsert_product(conn, row)
        insert_category_snapshot(conn, row, job_id, snapshot_date)
        if insert_rank_record(conn, row, job_id, snapshot_date):
            inserted += 1

    conn.commit()
    return {"inserted_records": inserted}
