from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core.settings import get_settings
from app.export.service import export_ranks_csv, export_ranks_xlsx
from app.jobs.schemas import ValidationError, parse_job_run_payload
from app.jobs.service import create_manual_job, list_jobs
from app.ranking.query_service import (
    cleanup_invalid_history,
    list_known_categories,
    query_product_trend,
    query_rank_changes,
    query_ranks,
)
from app.scheduler.runner import DailyScheduler

WEB_DIR = Path(__file__).resolve().parent / "web"
SCHEDULER: DailyScheduler | None = None


def _single(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _json_response(status: HTTPStatus, payload: dict) -> tuple[int, dict[str, str], bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return int(status), {"Content-Type": "application/json; charset=utf-8"}, data


def _text_response(
    status: HTTPStatus,
    text: str,
    *,
    content_type: str,
    attachment: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Content-Type": content_type}
    if attachment:
        headers["Content-Disposition"] = f'attachment; filename="{attachment}"'
    return int(status), headers, text.encode("utf-8")


def _bytes_response(
    status: HTTPStatus,
    payload: bytes,
    *,
    content_type: str,
    attachment: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Content-Type": content_type}
    if attachment:
        headers["Content-Disposition"] = f'attachment; filename="{attachment}"'
    return int(status), headers, payload


def _serve_static(file_name: str, content_type: str) -> tuple[int, dict[str, str], bytes]:
    path = WEB_DIR / file_name
    if not path.exists():
        return _json_response(HTTPStatus.NOT_FOUND, {"error": "static not found"})
    return _bytes_response(HTTPStatus.OK, path.read_bytes(), content_type=content_type)


def dispatch_request(method: str, path: str, body: bytes | None = None) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)

    try:
        if method == "GET":
            if parsed.path == "/api/health":
                return _json_response(HTTPStatus.OK, {"status": "ok"})

            if parsed.path == "/api/jobs":
                limit = int(_single(query, "limit", "100") or "100")
                return _json_response(HTTPStatus.OK, {"items": list_jobs(limit=limit)})

            if parsed.path == "/api/ranks":
                payload = query_ranks(
                    {
                        "site": _single(query, "site"),
                        "board_type": _single(query, "board_type"),
                        "category_key": _single(query, "category_key"),
                        "snapshot_date": _single(query, "snapshot_date"),
                        "keyword": _single(query, "keyword"),
                        "top_n": _single(query, "top_n"),
                        "min_rank": _single(query, "min_rank"),
                        "max_rank": _single(query, "max_rank"),
                        "sort_by": _single(query, "sort_by"),
                        "sort_order": _single(query, "sort_order"),
                        "has_price": _single(query, "has_price", "1"),
                        "job_id": _single(query, "job_id"),
                        "page": _single(query, "page", "1"),
                        "page_size": _single(query, "page_size", "50"),
                    }
                )
                return _json_response(HTTPStatus.OK, payload)

            if parsed.path == "/api/categories":
                payload = list_known_categories(
                    {
                        "site": _single(query, "site"),
                        "board_type": _single(query, "board_type"),
                        "snapshot_date": _single(query, "snapshot_date"),
                        "job_id": _single(query, "job_id"),
                    }
                )
                return _json_response(HTTPStatus.OK, payload)

            if parsed.path == "/api/ranks/changes":
                payload = query_rank_changes(
                    {
                        "site": _single(query, "site"),
                        "board_type": _single(query, "board_type"),
                        "category_key": _single(query, "category_key"),
                        "snapshot_date": _single(query, "snapshot_date"),
                    }
                )
                return _json_response(HTTPStatus.OK, payload)

            if parsed.path.startswith("/api/products/") and parsed.path.endswith("/trend"):
                asin = parsed.path.replace("/api/products/", "").replace("/trend", "")
                payload = query_product_trend(asin=asin, site=_single(query, "site") or None)
                return _json_response(HTTPStatus.OK, payload)

            if parsed.path == "/api/export/ranks.csv":
                filters = {
                    "site": _single(query, "site"),
                    "board_type": _single(query, "board_type"),
                    "category_key": _single(query, "category_key"),
                    "snapshot_date": _single(query, "snapshot_date"),
                    "keyword": _single(query, "keyword"),
                    "top_n": _single(query, "top_n"),
                    "min_rank": _single(query, "min_rank"),
                    "max_rank": _single(query, "max_rank"),
                    "sort_by": _single(query, "sort_by"),
                    "sort_order": _single(query, "sort_order"),
                    "has_price": _single(query, "has_price", "1"),
                    "job_id": _single(query, "job_id"),
                }
                csv_data = export_ranks_csv(filters)
                return _text_response(
                    HTTPStatus.OK,
                    csv_data,
                    content_type="text/csv; charset=utf-8",
                    attachment="ranks.csv",
                )

            if parsed.path == "/api/export/ranks.xlsx":
                filters = {
                    "site": _single(query, "site"),
                    "board_type": _single(query, "board_type"),
                    "category_key": _single(query, "category_key"),
                    "snapshot_date": _single(query, "snapshot_date"),
                    "keyword": _single(query, "keyword"),
                    "top_n": _single(query, "top_n"),
                    "min_rank": _single(query, "min_rank"),
                    "max_rank": _single(query, "max_rank"),
                    "sort_by": _single(query, "sort_by"),
                    "sort_order": _single(query, "sort_order"),
                    "has_price": _single(query, "has_price", "1"),
                    "job_id": _single(query, "job_id"),
                }
                xlsx_data = export_ranks_xlsx(filters)
                return _bytes_response(
                    HTTPStatus.OK,
                    xlsx_data,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    attachment="ranks.xlsx",
                )

            if parsed.path in {"/", "/index.html"}:
                return _serve_static("index.html", "text/html; charset=utf-8")
            if parsed.path == "/styles.css":
                return _serve_static("styles.css", "text/css; charset=utf-8")
            if parsed.path == "/app.js":
                return _serve_static("app.js", "application/javascript; charset=utf-8")

            return _json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

        if method == "POST":
            if parsed.path == "/api/jobs/run":
                raw = body or b"{}"
                req = parse_job_run_payload(json.loads(raw.decode("utf-8")))
                job = create_manual_job(req)
                return _json_response(HTTPStatus.ACCEPTED, job)

            if parsed.path == "/api/maintenance/cleanup-invalid":
                raw = body or b"{}"
                payload = json.loads(raw.decode("utf-8"))
                result = cleanup_invalid_history(payload if isinstance(payload, dict) else {})
                return _json_response(HTTPStatus.OK, result)

            return _json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

        return _json_response(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
    except ValidationError as exc:
        return _json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except ValueError as exc:
        return _json_response(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return _json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "AmazonTopCrawler/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle_with_dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle_with_dispatch("POST")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _handle_with_dispatch(self, method: str) -> None:
        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length > 0 else b"{}"

        status, headers, data = dispatch_request(method=method, path=self.path, body=body)

        self.send_response(status)
        self._send_cors()
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")


def create_server(host: str | None = None, port: int | None = None, *, start_scheduler: bool = True) -> ThreadingHTTPServer:
    settings = get_settings()
    bind_host = host or settings.host
    bind_port = int(port if port is not None else settings.port)
    server = ThreadingHTTPServer((bind_host, bind_port), ApiHandler)

    global SCHEDULER
    if start_scheduler:
        if SCHEDULER is None:
            SCHEDULER = DailyScheduler()
        SCHEDULER.start()

    return server


def run() -> None:
    settings = get_settings()
    server = create_server(settings.host, settings.port, start_scheduler=True)
    print(f"server started at http://{settings.host}:{settings.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if SCHEDULER:
            SCHEDULER.stop()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
