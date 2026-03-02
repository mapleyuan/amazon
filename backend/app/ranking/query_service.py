from __future__ import annotations

import sqlite3

from app.db.connection import get_connection


def _build_filters(params: dict) -> tuple[str, list[object]]:
    clauses: list[str] = []
    values: list[object] = []

    for key in ("site", "board_type", "category_key", "snapshot_date"):
        value = params.get(key)
        if value:
            clauses.append(f"rr.{key} = ?")
            values.append(value)

    keyword = str(params.get("keyword", "")).strip()
    if keyword:
        clauses.append("(p.title LIKE ? OR rr.asin LIKE ?)")
        values.append(f"%{keyword}%")
        values.append(f"%{keyword}%")

    min_rank = params.get("min_rank")
    if min_rank:
        try:
            clauses.append("rr.rank >= ?")
            values.append(max(1, int(min_rank)))
        except (TypeError, ValueError):
            pass

    max_rank = params.get("max_rank")
    if max_rank:
        try:
            clauses.append("rr.rank <= ?")
            values.append(max(1, int(max_rank)))
        except (TypeError, ValueError):
            pass

    top_n = params.get("top_n")
    if top_n:
        try:
            clauses.append("rr.rank <= ?")
            values.append(max(1, int(top_n)))
        except (TypeError, ValueError):
            pass

    has_price = str(params.get("has_price", "1")).strip().lower()
    if has_price not in {"0", "false", "no"}:
        clauses.append("rr.price_text IS NOT NULL AND TRIM(rr.price_text) <> ''")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, values


def _append_where(where: str, clause: str) -> str:
    if not where:
        return f" WHERE {clause}"
    return f"{where} AND {clause}"


def _resolve_latest_success_job_id(conn: sqlite3.Connection, params: dict) -> int | None:
    explicit = params.get("job_id")
    if explicit:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return None

    clauses = ["status = 'success'"]
    values: list[object] = []

    site = params.get("site")
    board = params.get("board_type")
    snapshot_date = params.get("snapshot_date")

    if site:
        clauses.append("site = ?")
        values.append(site)
    if board:
        clauses.append("board_type = ?")
        values.append(board)
    if snapshot_date:
        clauses.append("snapshot_date = ?")
        values.append(snapshot_date)

    row = conn.execute(
        f"""
        SELECT id
        FROM crawl_jobs
        WHERE {' AND '.join(clauses)}
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(values),
    ).fetchone()
    return int(row["id"]) if row else None


def query_ranks(params: dict) -> dict:
    conn = get_connection()
    where, values = _build_filters(params)
    latest_job_id = _resolve_latest_success_job_id(conn, params)
    if latest_job_id is not None:
        where = _append_where(where, "rr.job_id = ?")
        values.append(latest_job_id)

    sort_by = str(params.get("sort_by", "rank")).strip().lower()
    sort_order = str(params.get("sort_order", "asc")).strip().lower()
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    sort_field_map = {
        "rank": "rr.rank",
        "rating": "rr.rating",
        "review_count": "rr.review_count",
    }
    sort_field = sort_field_map.get(sort_by, "rr.rank")
    nulls_last = "NULLS LAST" if sort_order == "asc" else "NULLS FIRST"
    order_by = f"{sort_field} {sort_order.upper()} {nulls_last}, rr.rank ASC"

    page = max(1, int(params.get("page", 1) or 1))
    page_size = max(1, min(500, int(params.get("page_size", 50) or 50)))
    offset = (page - 1) * page_size

    total = conn.execute(
        f"""
        SELECT COUNT(1) AS cnt
        FROM rank_records rr
        JOIN products p ON p.site = rr.site AND p.asin = rr.asin
        {where}
        """,
        tuple(values),
    ).fetchone()["cnt"]

    rows = conn.execute(
        f"""
        SELECT rr.snapshot_date, rr.site, rr.board_type, rr.category_key, rr.asin,
               rr.rank, rr.price_text, rr.rating, rr.review_count,
               p.title, p.brand, p.image_url, p.detail_url,
               COALESCE(c.name, rr.category_key) AS category_name,
               rr.job_id
        FROM rank_records rr
        JOIN products p ON p.site = rr.site AND p.asin = rr.asin
        LEFT JOIN categories c
          ON c.site = rr.site
         AND c.board_type = rr.board_type
         AND c.category_key = rr.category_key
        {where}
        ORDER BY rr.snapshot_date DESC, rr.job_id DESC, {order_by}
        LIMIT ? OFFSET ?
        """,
        tuple(values + [page_size, offset]),
    ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "job_id": latest_job_id,
    }


def list_known_categories(params: dict) -> dict:
    conn = get_connection()
    where_clauses: list[str] = []
    values: list[object] = []

    site = params.get("site")
    board_type = params.get("board_type")
    snapshot_date = params.get("snapshot_date")

    if site:
        where_clauses.append("rr.site = ?")
        values.append(site)
    if board_type:
        where_clauses.append("rr.board_type = ?")
        values.append(board_type)
    if snapshot_date:
        where_clauses.append("rr.snapshot_date = ?")
        values.append(snapshot_date)

    latest_job_id = _resolve_latest_success_job_id(conn, params)
    if latest_job_id is not None:
        where_clauses.append("rr.job_id = ?")
        values.append(latest_job_id)

    where = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows = conn.execute(
        f"""
        SELECT
          rr.category_key,
          COALESCE(c.name, rr.category_key) AS category_name,
          COUNT(1) AS item_count,
          MIN(rr.rank) AS best_rank
        FROM rank_records rr
        LEFT JOIN categories c
          ON c.site = rr.site
         AND c.board_type = rr.board_type
         AND c.category_key = rr.category_key
        {where}
        GROUP BY rr.category_key, category_name
        ORDER BY category_name ASC
        """,
        tuple(values),
    ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "job_id": latest_job_id,
    }


def cleanup_invalid_history(params: dict) -> dict:
    conn = get_connection()
    clauses = ["(price_text IS NULL OR TRIM(price_text) = '')"]
    values: list[object] = []

    site = params.get("site")
    board_type = params.get("board_type")
    snapshot_date = params.get("snapshot_date")
    category_key = params.get("category_key")
    job_id = params.get("job_id")

    if site:
        clauses.append("site = ?")
        values.append(site)
    if board_type:
        clauses.append("board_type = ?")
        values.append(board_type)
    if snapshot_date:
        clauses.append("snapshot_date = ?")
        values.append(snapshot_date)
    if category_key:
        clauses.append("category_key = ?")
        values.append(category_key)
    if job_id:
        try:
            clauses.append("job_id = ?")
            values.append(int(job_id))
        except (TypeError, ValueError):
            pass

    where = " WHERE " + " AND ".join(clauses)
    deleted_rank_records = conn.execute(
        f"DELETE FROM rank_records{where}",
        tuple(values),
    ).rowcount

    deleted_products = conn.execute(
        """
        DELETE FROM products
        WHERE NOT EXISTS (
          SELECT 1
          FROM rank_records rr
          WHERE rr.site = products.site
            AND rr.asin = products.asin
        )
        """
    ).rowcount

    deleted_categories = conn.execute(
        """
        DELETE FROM categories
        WHERE NOT EXISTS (
          SELECT 1
          FROM rank_records rr
          WHERE rr.site = categories.site
            AND rr.board_type = categories.board_type
            AND rr.category_key = categories.category_key
        )
        """
    ).rowcount

    remaining_invalid = conn.execute(
        """
        SELECT COUNT(1) AS cnt
        FROM rank_records
        WHERE price_text IS NULL OR TRIM(price_text) = ''
        """
    ).fetchone()["cnt"]

    conn.commit()
    return {
        "deleted_rank_records": int(deleted_rank_records),
        "deleted_products": int(deleted_products),
        "deleted_categories": int(deleted_categories),
        "remaining_invalid_rank_records": int(remaining_invalid),
    }


def query_rank_changes(params: dict) -> dict:
    site = params.get("site")
    board = params.get("board_type")
    category = params.get("category_key")
    target_date = params.get("snapshot_date")

    if not (site and board and category):
        return {"items": []}

    conn = get_connection()
    if not target_date:
        row = conn.execute(
            """
            SELECT MAX(snapshot_date) AS snapshot_date
            FROM rank_records
            WHERE site = ? AND board_type = ? AND category_key = ?
            """,
            (site, board, category),
        ).fetchone()
        target_date = row["snapshot_date"] if row else None

    if not target_date:
        return {"items": []}

    prev = conn.execute(
        """
        SELECT MAX(snapshot_date) AS snapshot_date
        FROM rank_records
        WHERE site = ? AND board_type = ? AND category_key = ? AND snapshot_date < ?
        """,
        (site, board, category, target_date),
    ).fetchone()["snapshot_date"]

    current_rows = conn.execute(
        """
        SELECT asin, rank
        FROM rank_records
        WHERE site = ? AND board_type = ? AND category_key = ? AND snapshot_date = ?
        """,
        (site, board, category, target_date),
    ).fetchall()
    current_map = {row["asin"]: int(row["rank"]) for row in current_rows}

    prev_map: dict[str, int] = {}
    if prev:
        prev_rows = conn.execute(
            """
            SELECT asin, rank
            FROM rank_records
            WHERE site = ? AND board_type = ? AND category_key = ? AND snapshot_date = ?
            """,
            (site, board, category, prev),
        ).fetchall()
        prev_map = {row["asin"]: int(row["rank"]) for row in prev_rows}

    items = []
    for asin, rank in sorted(current_map.items(), key=lambda kv: kv[1]):
        previous_rank = prev_map.get(asin)
        delta = None if previous_rank is None else previous_rank - rank
        items.append({"asin": asin, "rank": rank, "previous_rank": previous_rank, "delta": delta})

    return {"items": items, "snapshot_date": target_date, "previous_snapshot_date": prev}


def query_product_trend(asin: str, site: str | None = None) -> dict:
    conn = get_connection()

    if site:
        rows = conn.execute(
            """
            SELECT snapshot_date, site, board_type, category_key, rank
            FROM rank_records
            WHERE asin = ? AND site = ?
            ORDER BY snapshot_date ASC
            """,
            (asin, site),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT snapshot_date, site, board_type, category_key, rank
            FROM rank_records
            WHERE asin = ?
            ORDER BY snapshot_date ASC
            """,
            (asin,),
        ).fetchall()

    return {"items": [dict(row) for row in rows]}
