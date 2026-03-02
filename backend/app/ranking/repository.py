from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_category(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO categories (site, board_type, level, category_key, name, parent_category_key)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(site, board_type, category_key)
        DO UPDATE SET name = excluded.name, level = excluded.level, parent_category_key = excluded.parent_category_key
        """,
        (
            row["site"],
            row["board_type"],
            int(row.get("category_level", 2)),
            row["category_key"],
            row.get("category_name") or row["category_key"],
            row.get("parent_category_key"),
        ),
    )


def insert_category_snapshot(conn: sqlite3.Connection, row: dict, job_id: int, snapshot_date: str) -> None:
    conn.execute(
        """
        INSERT INTO category_snapshots (job_id, site, board_type, category_key, snapshot_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, row["site"], row["board_type"], row["category_key"], snapshot_date),
    )


def upsert_product(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO products (site, asin, title, brand, image_url, detail_url)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(site, asin)
        DO UPDATE SET
          title = excluded.title,
          brand = COALESCE(excluded.brand, products.brand),
          image_url = COALESCE(excluded.image_url, products.image_url),
          detail_url = COALESCE(excluded.detail_url, products.detail_url)
        """,
        (
            row["site"],
            row["asin"],
            row.get("title") or row["asin"],
            row.get("brand"),
            row.get("image_url"),
            row.get("detail_url"),
        ),
    )


def insert_rank_record(conn: sqlite3.Connection, row: dict, job_id: int, snapshot_date: str) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO rank_records (
          job_id,
          snapshot_date,
          site,
          board_type,
          category_key,
          asin,
          rank,
          price_text,
          rating,
          review_count,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            snapshot_date,
            row["site"],
            row["board_type"],
            row["category_key"],
            row["asin"],
            int(row["rank"]),
            row.get("price_text"),
            row.get("rating"),
            row.get("review_count"),
            _utc_now_iso(),
        ),
    )
    return cur.rowcount > 0
