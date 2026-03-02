from __future__ import annotations

from pathlib import Path
import sqlite3

from app.core.settings import get_settings
from app.db.schema import init_db

_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def _resolve_db_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    db_path = _resolve_db_path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    key = str(db_path)
    conn = _CONNECTIONS.get(key)
    if conn is not None:
        return conn

    conn = sqlite3.connect(key, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    _CONNECTIONS[key] = conn
    return conn


def reset_connections() -> None:
    for conn in _CONNECTIONS.values():
        conn.close()
    _CONNECTIONS.clear()
