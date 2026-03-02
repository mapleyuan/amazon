from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def isolated_env() -> Iterator[None]:
    """Provide isolated test DB and mock crawl mode."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        old_db = os.environ.get("AMAZON_DB_PATH")
        old_mock = os.environ.get("AMAZON_MOCK_CRAWL")
        os.environ["AMAZON_DB_PATH"] = str(db_path)
        os.environ["AMAZON_MOCK_CRAWL"] = "1"

        from app.db.connection import reset_connections

        reset_connections()
        try:
            yield
        finally:
            reset_connections()
            if old_db is None:
                os.environ.pop("AMAZON_DB_PATH", None)
            else:
                os.environ["AMAZON_DB_PATH"] = old_db
            if old_mock is None:
                os.environ.pop("AMAZON_MOCK_CRAWL", None)
            else:
                os.environ["AMAZON_MOCK_CRAWL"] = old_mock


@contextmanager
def running_server() -> Iterator[tuple[str, int]]:
    # Kept for API-test readability. In sandbox we don't open a socket.
    yield "local", 0


def request_json(host: str, port: int, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    from app.main import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    status, headers, data = dispatch_request(method=method, path=path, body=body)

    content_type = headers.get("Content-Type", "")
    if "application/json" not in content_type:
        raise AssertionError(f"Expected JSON response but got {content_type}")

    return status, json.loads(data.decode("utf-8"))


def request_text(host: str, port: int, method: str, path: str) -> tuple[int, str, str]:
    from app.main import dispatch_request

    status, headers, data = dispatch_request(method=method, path=path, body=None)
    content_type = headers.get("Content-Type", "")
    return status, data.decode("utf-8", errors="ignore"), content_type
