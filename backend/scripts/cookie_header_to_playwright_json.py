from __future__ import annotations

from argparse import ArgumentParser, Namespace
import json
from typing import Any


def _parse_args() -> Namespace:
    parser = ArgumentParser(description="Convert Cookie header string to Playwright cookies JSON")
    parser.add_argument("--cookie-header", required=True, help='e.g. "session-id=...; ubid-main=..."')
    parser.add_argument("--domain", default=".amazon.com", help='Cookie domain, default ".amazon.com"')
    parser.add_argument("--path", default="/", help='Cookie path, default "/"')
    parser.add_argument("--secure", action="store_true", help="Mark cookies secure")
    parser.add_argument("--http-only", action="store_true", help="Mark cookies httpOnly")
    return parser.parse_args()


def _parse_cookie_header(raw: str) -> list[tuple[str, str]]:
    parts = [segment.strip() for segment in str(raw or "").split(";") if segment.strip()]
    result: list[tuple[str, str]] = []
    for part in parts:
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        result.append((name, value))
    return result


def _build_playwright_cookies(
    pairs: list[tuple[str, str]],
    *,
    domain: str,
    path: str,
    secure: bool,
    http_only: bool,
) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for name, value in pairs:
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure,
                "httpOnly": http_only,
            }
        )
    return cookies


def main() -> int:
    args = _parse_args()
    pairs = _parse_cookie_header(args.cookie_header)
    if not pairs:
        print("[]")
        return 1

    payload = _build_playwright_cookies(
        pairs,
        domain=str(args.domain),
        path=str(args.path),
        secure=bool(args.secure),
        http_only=bool(args.http_only),
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
