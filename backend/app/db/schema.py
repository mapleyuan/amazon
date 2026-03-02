from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawl_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  board_type TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  status TEXT NOT NULL,
  snapshot_date TEXT,
  started_at TEXT,
  finished_at TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  board_type TEXT NOT NULL,
  level INTEGER NOT NULL,
  category_key TEXT NOT NULL,
  name TEXT NOT NULL,
  parent_category_key TEXT,
  UNIQUE(site, board_type, category_key)
);

CREATE TABLE IF NOT EXISTS category_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  site TEXT NOT NULL,
  board_type TEXT NOT NULL,
  category_key TEXT NOT NULL,
  snapshot_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  asin TEXT NOT NULL,
  title TEXT NOT NULL,
  brand TEXT,
  image_url TEXT,
  detail_url TEXT,
  UNIQUE(site, asin)
);

CREATE TABLE IF NOT EXISTS rank_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  snapshot_date TEXT NOT NULL,
  site TEXT NOT NULL,
  board_type TEXT NOT NULL,
  category_key TEXT NOT NULL,
  asin TEXT NOT NULL,
  rank INTEGER NOT NULL,
  price_text TEXT,
  rating REAL,
  review_count INTEGER,
  created_at TEXT NOT NULL,
  UNIQUE(job_id, site, board_type, category_key, asin, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_rank_records_query
  ON rank_records(site, board_type, category_key, snapshot_date, rank);

CREATE INDEX IF NOT EXISTS idx_rank_records_asin
  ON rank_records(site, asin, snapshot_date);

CREATE TABLE IF NOT EXISTS export_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  filter_json TEXT NOT NULL,
  file_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
