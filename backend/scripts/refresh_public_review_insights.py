from __future__ import annotations

from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.crawler.adapters import ACCEPT_LANG, SITE_BASE  # noqa: E402
from app.crawler.client import DEFAULT_UA, fetch_html  # noqa: E402
from app.official_insights.builder import build_official_insights_payload, utc_now_iso  # noqa: E402
from app.official_insights.public_reviews import (  # noqa: E402
    build_review_topic_summary,
    classify_review_page,
    parse_review_entries,
    parse_review_entries_from_product_html,
)

WEB_DATA_DIR = PROJECT_ROOT / "app" / "web" / "data"


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Refresh insights from public Amazon review pages")
    parser.add_argument("--snapshot-date", default="", help="YYYY-MM-DD; default today UTC")
    parser.add_argument("--site", default="amazon.com", choices=sorted(SITE_BASE.keys()))
    parser.add_argument("--asins", default="", help="Comma/space separated ASINs; empty = auto from daily snapshot")
    parser.add_argument("--asin-limit", type=int, default=8)
    parser.add_argument("--pages-per-asin", type=int, default=2)
    parser.add_argument("--top-n-topics", type=int, default=8)
    parser.add_argument("--min-topic-mentions", type=int, default=2)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when no review topics can be generated")
    parser.add_argument(
        "--strict-review-topics",
        action="store_true",
        help="Exit non-zero when final review_topic_asins is 0 (hard check)",
    )
    parser.add_argument("--insights-output-dir", default=str(WEB_DATA_DIR / "insights"))
    return parser.parse_args(argv)


def _snapshot_date(raw: str) -> str:
    text = str(raw or "").strip()
    if text:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    return datetime.now(timezone.utc).date().isoformat()


def _parse_asins(raw: str) -> list[str]:
    values = re.split(r"[,\s]+", str(raw or "").strip())
    normalized = [value.strip().upper() for value in values if value and value.strip()]
    result: list[str] = []
    for asin in normalized:
        if len(asin) == 10 and asin.isalnum() and asin not in result:
            result.append(asin)
    return result


def _load_asins_from_daily(snapshot_date: str, limit: int) -> list[str]:
    if limit <= 0:
        return []

    path = WEB_DATA_DIR / "daily" / f"{snapshot_date}.json"
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    ranked: list[tuple[int, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        asin = str(item.get("asin") or "").strip().upper()
        if len(asin) != 10 or not asin.isalnum():
            continue

        rank = item.get("rank")
        try:
            rank_value = int(rank)
        except (TypeError, ValueError):
            rank_value = 10_000_000
        ranked.append((rank_value, asin))

    ranked.sort(key=lambda pair: pair[0])
    unique: list[str] = []
    for _, asin in ranked:
        if asin in unique:
            continue
        unique.append(asin)
        if len(unique) >= limit:
            break
    return unique


def _review_page_url(site: str, asin: str, page_number: int) -> str:
    base = SITE_BASE[site].rstrip("/")
    return (
        f"{base}/product-reviews/{asin}"
        f"?reviewerType=all_reviews&sortBy=recent&pageNumber={max(1, int(page_number))}"
    )


def _product_page_url(site: str, asin: str) -> str:
    base = SITE_BASE[site].rstrip("/")
    return f"{base}/dp/{asin}"


def _review_source_candidates() -> list[str]:
    primary = str(os.environ.get("AMAZON_CRAWL_SOURCE", "direct") or "direct").strip().lower() or "direct"
    candidates: list[str] = [primary]

    if primary == "jina_ai":
        candidates.append("direct")
    elif primary == "direct":
        candidates.append("jina_ai")
    else:
        candidates.append("direct")

    deduped: list[str] = []
    for source in candidates:
        if source and source not in deduped:
            deduped.append(source)

    if os.environ.get("AMAZON_REVIEW_PLAYWRIGHT", "0") == "1":
        if "playwright" not in deduped:
            if "direct" in deduped:
                insert_at = deduped.index("direct") + 1
                deduped.insert(insert_at, "playwright")
            else:
                deduped.append("playwright")
    return deduped


@contextmanager
def _temporary_crawl_source(source: str):
    key = "AMAZON_CRAWL_SOURCE"
    had_key = key in os.environ
    previous = os.environ.get(key)
    os.environ[key] = str(source or "").strip()
    try:
        yield
    finally:
        if had_key:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        else:
            os.environ.pop(key, None)


def _classify_failure_reason(
    *,
    has_rows: bool,
    blocked_pages: int,
    page_not_found_pages: int,
    pages_succeeded: int,
    network_errors: int,
) -> str | None:
    if has_rows:
        return None
    if blocked_pages > 0:
        return "blocked_page"
    if page_not_found_pages > 0 and pages_succeeded <= page_not_found_pages:
        return "page_not_found"
    if pages_succeeded <= 0 and network_errors > 0:
        return "network_error"
    if pages_succeeded > 0:
        return "parsed_zero"
    if network_errors > 0:
        return "network_error"
    return "unknown_error"


def _external_review_failures_only(diagnostics: list[dict[str, Any]]) -> bool:
    reasons: set[str] = set()
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("failure_reason") or "").strip()
        if reason:
            reasons.add(reason)

    if not reasons:
        return False
    return reasons.issubset({"blocked_page", "network_error", "page_not_found"})


def _fetch_review_page_with_playwright(
    url: str,
    *,
    site: str,
    timeout: int,
    max_bytes: int,
) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("playwright missing: pip install playwright && playwright install chromium") from exc

    lang = ACCEPT_LANG.get(site, "en-US,en;q=0.9")
    locale = lang.split(",")[0].split(";")[0].strip() or "en-US"
    timeout_ms = max(5, int(timeout)) * 1000
    cookie_header = str(os.environ.get("AMAZON_CRAWL_COOKIE", "") or "").strip()
    referer_header = str(os.environ.get("AMAZON_CRAWL_REFERER", "") or "").strip()
    raw_cookies_json = str(os.environ.get("AMAZON_REVIEW_COOKIES_JSON", "") or "").strip()
    extra_headers = {"Accept-Language": lang}
    if cookie_header:
        extra_headers["Cookie"] = cookie_header
    if referer_header:
        extra_headers["Referer"] = referer_header

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            locale=locale,
            extra_http_headers=extra_headers,
        )
        if raw_cookies_json:
            try:
                cookies = json.loads(raw_cookies_json)
                if isinstance(cookies, list):
                    context.add_cookies(cookies)
            except Exception:  # noqa: BLE001
                pass
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1200)
        content = page.content()
        context.close()
        browser.close()
    return str(content or "")[: max(1, int(max_bytes))]


def _fetch_review_page(url: str, *, site: str, source: str, timeout: int, max_bytes: int) -> str:
    normalized = str(source or "").strip().lower()
    if normalized == "playwright":
        return _fetch_review_page_with_playwright(url, site=site, timeout=timeout, max_bytes=max_bytes)
    with _temporary_crawl_source(normalized):
        return fetch_html(url, site=site, timeout=timeout, max_bytes=max_bytes)


def _is_not_found_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code == 404
    text = str(exc)
    return "HTTP Error 404" in text or "404" in text


def _collect_review_entries_for_asin(site: str, asin: str, pages_per_asin: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pages_attempted = 0
    pages_succeeded = 0
    blocked_pages = 0
    page_not_found_pages = 0
    network_errors = 0
    errors: list[str] = []
    page_stats: list[dict[str, Any]] = []
    source_candidates = _review_source_candidates()

    for page in range(1, max(1, pages_per_asin) + 1):
        pages_attempted += 1
        url = _review_page_url(site, asin, page)
        page_parsed: list[dict[str, Any]] = []
        page_fetch_ok = False
        chosen_source = ""
        source_attempts: list[dict[str, Any]] = []

        for source in source_candidates:
            attempt: dict[str, Any] = {
                "source": source,
                "parsed_entries": 0,
                "error": None,
                "page_issue": None,
            }
            try:
                text = _fetch_review_page(url, site=site, source=source, timeout=20, max_bytes=800_000)
                page_fetch_ok = True
            except Exception as exc:  # noqa: BLE001
                error_text = f"{type(exc).__name__}: {exc}"
                if _is_not_found_error(exc):
                    attempt["error"] = error_text
                    attempt["page_issue"] = "page_not_found"
                    source_attempts.append(attempt)
                    if page <= 1:
                        errors.append(f"page={page} source={source}: {error_text}")
                    continue

                attempt["error"] = error_text
                attempt["page_issue"] = "network_error"
                source_attempts.append(attempt)
                errors.append(f"page={page} source={source}: {error_text}")
                network_errors += 1
                continue

            parsed = parse_review_entries(text)
            attempt["parsed_entries"] = len(parsed)
            if parsed:
                chosen_source = source
                page_parsed = parsed
                source_attempts.append(attempt)
                break

            page_issue = classify_review_page(text) or "parsed_zero"
            attempt["page_issue"] = page_issue
            if page_issue == "blocked_page":
                blocked_pages += 1
            source_attempts.append(attempt)

        if page_fetch_ok:
            pages_succeeded += 1

        if page_parsed:
            rows.extend(page_parsed)
            page_stats.append(
                {
                    "page": page,
                    "source": chosen_source,
                    "parsed_entries": len(page_parsed),
                    "error": None,
                    "page_issue": None,
                    "sources_tried": source_attempts,
                }
            )
            continue

        if not source_attempts:
            page_stats.append(
                {
                    "page": page,
                    "source": None,
                    "parsed_entries": 0,
                    "error": "no source attempts",
                    "page_issue": "unknown_error",
                    "sources_tried": [],
                }
            )
            continue

        issues = [str(item.get("page_issue") or "") for item in source_attempts]
        final_issue = "parsed_zero"
        if any(issue == "blocked_page" for issue in issues):
            final_issue = "blocked_page"
        elif any(issue == "page_not_found" for issue in issues):
            final_issue = "page_not_found"
        elif issues and all(issue == "network_error" for issue in issues):
            final_issue = "network_error"

        if final_issue == "page_not_found":
            page_not_found_pages += 1

        page_stats.append(
            {
                "page": page,
                "source": source_attempts[-1].get("source"),
                "parsed_entries": 0,
                "error": None if final_issue != "network_error" else "all sources failed with network errors",
                "page_issue": final_issue,
                "sources_tried": source_attempts,
            }
        )
        if page == 1 and final_issue in {"blocked_page", "page_not_found"}:
            break
        if page > 1:
            break

    detail_fallback_used = False
    if not rows:
        detail_url = _product_page_url(site, asin)
        detail_attempts: list[dict[str, Any]] = []
        detail_source = ""
        detail_page_issue = None

        for source in source_candidates:
            attempt: dict[str, Any] = {
                "source": source,
                "parsed_entries": 0,
                "error": None,
                "page_issue": None,
            }
            try:
                text = _fetch_review_page(detail_url, site=site, source=source, timeout=20, max_bytes=1_000_000)
            except Exception as exc:  # noqa: BLE001
                error_text = f"{type(exc).__name__}: {exc}"
                attempt["error"] = error_text
                if _is_not_found_error(exc):
                    attempt["page_issue"] = "page_not_found"
                else:
                    attempt["page_issue"] = "network_error"
                    network_errors += 1
                detail_attempts.append(attempt)
                continue

            page_issue = classify_review_page(text)
            if page_issue:
                attempt["page_issue"] = page_issue
                if page_issue == "blocked_page":
                    blocked_pages += 1
                detail_attempts.append(attempt)
                detail_page_issue = page_issue
                continue

            parsed = parse_review_entries_from_product_html(text, limit=12)
            attempt["parsed_entries"] = len(parsed)
            detail_attempts.append(attempt)
            if parsed:
                detail_fallback_used = True
                detail_source = source
                rows.extend(parsed)
                break
            detail_page_issue = "parsed_zero"

        if detail_attempts:
            page_stats.append(
                {
                    "page": "product_detail",
                    "source": detail_source or detail_attempts[-1].get("source"),
                    "parsed_entries": len(rows),
                    "error": None,
                    "page_issue": None if rows else (detail_page_issue or "parsed_zero"),
                    "sources_tried": detail_attempts,
                }
            )
            if not rows and not errors:
                if detail_page_issue == "blocked_page":
                    errors.append("product detail blocked or robot check")
                elif detail_page_issue == "page_not_found":
                    errors.append("product detail page not found")
                elif detail_page_issue == "parsed_zero":
                    errors.append("product detail has no parseable review snippets")

    failure_reason = _classify_failure_reason(
        has_rows=bool(rows),
        blocked_pages=blocked_pages,
        page_not_found_pages=page_not_found_pages,
        pages_succeeded=pages_succeeded,
        network_errors=network_errors,
    )

    diagnostics = {
        "asin": asin,
        "site": site,
        "source_candidates": source_candidates,
        "pages_attempted": pages_attempted,
        "pages_succeeded": pages_succeeded,
        "entries_parsed": len(rows),
        "detail_fallback_used": detail_fallback_used,
        "status": "ok" if rows else "failed",
        "failure_reason": failure_reason,
        "errors": errors,
        "pages": page_stats,
    }
    if not rows:
        if failure_reason == "blocked_page":
            diagnostics["errors"] = errors or ["blocked page detected"]
        elif failure_reason == "page_not_found":
            diagnostics["errors"] = errors or ["review page not found"]
        elif failure_reason == "parsed_zero":
            diagnostics["errors"] = errors or ["no review entries parsed"]
        elif not errors:
            diagnostics["errors"] = ["review fetch failed"]
    return rows, diagnostics


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _merge_source(existing_source: str, has_public_reviews: bool) -> str:
    raw = str(existing_source or "").strip()
    tags = [part.strip() for part in raw.split("+") if part.strip()]
    if not tags:
        tags = ["public_reviews"] if has_public_reviews else []

    normalized: list[str] = []
    for tag in tags:
        if tag == "mixed_reports_public_reviews":
            normalized.extend(["official_reports", "public_reviews"])
        else:
            normalized.append(tag)

    deduped: list[str] = []
    for tag in normalized:
        if tag not in deduped:
            deduped.append(tag)

    if has_public_reviews:
        if "public_reviews" not in deduped:
            deduped.append("public_reviews")
    else:
        deduped = [tag for tag in deduped if tag != "public_reviews"]

    if "official_reports" in deduped and "public_reviews" in deduped:
        # Keep backward-compatible aggregate marker for mixed sources.
        deduped = [tag for tag in deduped if tag not in {"official_reports", "public_reviews"}]
        deduped.insert(0, "mixed_reports_public_reviews")

    if not deduped:
        return "public_search_keywords" if "public_search_keywords" in raw else "unknown"
    return "+".join(deduped)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot_date = _snapshot_date(args.snapshot_date)
    output_path = Path(args.insights_output_dir) / f"{snapshot_date}.json"

    asins = _parse_asins(args.asins)
    if not asins:
        asins = _load_asins_from_daily(snapshot_date, int(args.asin_limit))

    existing = _load_json(output_path) or {}
    existing_keywords = existing.get("keywords") if isinstance(existing.get("keywords"), list) else []
    existing_monthly_sales = existing.get("monthly_sales") if isinstance(existing.get("monthly_sales"), list) else []
    existing_style_trends = existing.get("style_trends") if isinstance(existing.get("style_trends"), list) else []
    existing_review_topics = existing.get("review_topics") if isinstance(existing.get("review_topics"), list) else []
    existing_diagnostics = (
        existing.get("review_fetch_diagnostics") if isinstance(existing.get("review_fetch_diagnostics"), list) else []
    )

    review_topics: list[dict[str, Any]] = []
    review_fetch_diagnostics: list[dict[str, Any]] = []
    for asin in asins:
        entries, diagnostics = _collect_review_entries_for_asin(args.site, asin, int(args.pages_per_asin))
        review_fetch_diagnostics.append(diagnostics)
        print(
            f"[review-fetch] asin={asin} status={diagnostics.get('status')} "
            f"entries={diagnostics.get('entries_parsed')} pages_ok={diagnostics.get('pages_succeeded')}/{diagnostics.get('pages_attempted')}"
        )
        if diagnostics.get("failure_reason"):
            print(f"[review-fetch] asin={asin} failure_reason={diagnostics.get('failure_reason')}")
        if diagnostics.get("errors"):
            print(f"[review-fetch] asin={asin} errors={diagnostics.get('errors')}")

        if not entries:
            continue

        summary = build_review_topic_summary(
            entries,
            top_n=max(1, int(args.top_n_topics)),
            min_mentions=max(1, int(args.min_topic_mentions)),
        )
        if summary["sample_reviews"] <= 0:
            diagnostics["status"] = "failed"
            diagnostics.setdefault("errors", []).append("parsed entries but sample_reviews=0 after cleanup")
            continue

        diagnostics["sample_reviews"] = int(summary["sample_reviews"])
        review_topics.append(
            {
                "asin": asin,
                "sample_reviews": int(summary["sample_reviews"]),
                "total_reviews": int(summary.get("total_reviews") or summary["sample_reviews"]),
                "avg_rating": summary.get("avg_rating"),
                "rating_distribution": summary.get("rating_distribution") or {},
                "sentiment": summary.get("sentiment") or {},
                "positive_topics": summary["positive_topics"],
                "negative_topics": summary["negative_topics"],
                "positive_snippets": summary.get("positive_snippets") or [],
                "negative_snippets": summary.get("negative_snippets") or [],
            }
        )

    has_new_reviews = bool(review_topics)
    final_review_topics = review_topics if has_new_reviews else existing_review_topics
    final_diagnostics = review_fetch_diagnostics if review_fetch_diagnostics else existing_diagnostics
    failed_asins = sum(1 for item in final_diagnostics if str(item.get("status") or "") != "ok")

    total_rows = len(existing_keywords) + len(existing_monthly_sales) + len(existing_style_trends) + len(final_review_topics)

    payload = build_official_insights_payload(
        snapshot_date=snapshot_date,
        generated_at=utc_now_iso(),
        keywords=existing_keywords,
        monthly_sales=existing_monthly_sales,
        review_topics=final_review_topics,
        style_trends=existing_style_trends,
    )
    payload["source"] = _merge_source(str(existing.get("source") or ""), has_new_reviews)
    payload["review_fetch_diagnostics"] = final_diagnostics
    payload["stats"]["review_topic_failed_asins"] = int(failed_asins)

    _write_json(output_path, payload)

    if args.strict and total_rows == 0:
        return 1
    if args.strict_review_topics and len(final_review_topics) <= 0:
        allow_external_bypass = str(os.environ.get("AMAZON_REVIEW_ALLOW_EXTERNAL_BYPASS", "1") or "1").strip() == "1"
        if allow_external_bypass and _external_review_failures_only(final_diagnostics):
            print(
                "[review-fetch] strict-review-topics bypassed: only external failures "
                "(blocked/network/page_not_found) detected in this run."
            )
            return 0
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
