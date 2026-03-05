from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import refresh_public_review_insights


class RefreshPublicReviewInsightsScriptTests(unittest.TestCase):
    def test_review_page_url_uses_canonical_path_without_trailing_slash(self) -> None:
        url = refresh_public_review_insights._review_page_url("amazon.com", "B08MLGXSPH", 2)
        self.assertIn("/product-reviews/B08MLGXSPH?", url)
        self.assertNotIn("/product-reviews/B08MLGXSPH/?", url)
        self.assertIn("pageNumber=2", url)

    def test_review_source_candidates_include_playwright_when_enabled(self) -> None:
        with patch.dict(
            refresh_public_review_insights.os.environ,
            {"AMAZON_CRAWL_SOURCE": "direct", "AMAZON_REVIEW_PLAYWRIGHT": "1"},
            clear=False,
        ):
            candidates = refresh_public_review_insights._review_source_candidates()
        self.assertEqual(candidates[0], "direct")
        self.assertIn("playwright", candidates)
        self.assertIn("jina_ai", candidates)

    def test_main_builds_review_topics_from_public_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2026-03-03",
                        "items": [
                            {"asin": "B000000001", "rank": 1},
                            {"asin": "B000000002", "rank": 2},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            mock_text = """
1. [5.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R1) Elegant and sturdy
Looks premium and sturdy metal base.

2. [1.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R2) Broke quickly
Arrived bent and unstable after one week.
"""

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", return_value=mock_text):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "1",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "public_reviews")
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            self.assertEqual(payload["stats"]["review_topic_failed_asins"], 0)
            self.assertEqual(len(payload["review_topics"]), 1)
            self.assertGreaterEqual(payload["review_topics"][0]["sample_reviews"], 2)
            self.assertIn("avg_rating", payload["review_topics"][0])
            self.assertIn("rating_distribution", payload["review_topics"][0])
            self.assertIn("sentiment", payload["review_topics"][0])
            self.assertIn("positive_snippets", payload["review_topics"][0])
            self.assertIn("negative_snippets", payload["review_topics"][0])
            self.assertIn("review_fetch_diagnostics", payload)
            self.assertEqual(len(payload["review_fetch_diagnostics"]), 1)
            self.assertEqual(payload["review_fetch_diagnostics"][0]["asin"], "B000000001")
            self.assertEqual(payload["review_fetch_diagnostics"][0]["status"], "ok")

    def test_main_merges_with_existing_official_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )
            (insights_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2026-03-03",
                        "source": "official_reports",
                        "keywords": [{"keyword": "candlestick", "impressions": 100}],
                        "monthly_sales": [],
                        "review_topics": [],
                        "style_trends": [],
                        "stats": {
                            "keyword_rows": 1,
                            "monthly_sales_rows": 0,
                            "review_topic_asins": 0,
                            "style_trend_rows": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            mock_text = """
1. [5.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R1) Great quality
Sturdy and elegant.
2. [1.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R2) Very fragile
Broke quickly.
"""

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", return_value=mock_text):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "1",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "mixed_reports_public_reviews")
            self.assertEqual(payload["stats"]["keyword_rows"], 1)
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            self.assertEqual(payload["stats"]["review_topic_failed_asins"], 0)

    def test_main_strict_review_topics_allows_external_failures_when_no_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )
            (insights_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2026-03-03",
                        "source": "public_search_keywords",
                        "keywords": [{"keyword": "candlestick", "impressions": 100}],
                        "monthly_sales": [],
                        "review_topics": [],
                        "style_trends": [],
                        "stats": {
                            "keyword_rows": 1,
                            "monthly_sales_rows": 0,
                            "review_topic_asins": 0,
                            "style_trend_rows": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", side_effect=RuntimeError("network down")):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "2",
                            "--strict-review-topics",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["review_topic_asins"], 0)
            self.assertEqual(payload["stats"]["review_topic_failed_asins"], 1)
            self.assertEqual(len(payload["review_fetch_diagnostics"]), 1)
            self.assertEqual(payload["review_fetch_diagnostics"][0]["asin"], "B000000001")
            self.assertEqual(payload["review_fetch_diagnostics"][0]["status"], "failed")
            self.assertEqual(payload["review_fetch_diagnostics"][0]["failure_reason"], "network_error")
            self.assertGreaterEqual(len(payload["review_fetch_diagnostics"][0]["errors"]), 1)

    def test_main_falls_back_to_direct_source_when_primary_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )

            blocked_text = """
Sorry, we just need to make sure you're not a robot.
To discuss automated access to Amazon data please contact api-services-support@amazon.com.
"""
            direct_ok_text = """
1. [5.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R1) Great quality
Sturdy and elegant.
"""

            def _fake_fetch(url: str, **kwargs: object) -> str:
                source = str(refresh_public_review_insights.os.environ.get("AMAZON_CRAWL_SOURCE") or "")
                if source == "jina_ai":
                    return blocked_text
                return direct_ok_text

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.dict(refresh_public_review_insights.os.environ, {"AMAZON_CRAWL_SOURCE": "jina_ai"}, clear=False):
                    with patch.object(refresh_public_review_insights, "fetch_html", side_effect=_fake_fetch):
                        code = refresh_public_review_insights.main(
                            [
                                "--snapshot-date",
                                "2026-03-03",
                                "--asin-limit",
                                "1",
                                "--pages-per-asin",
                                "1",
                                "--insights-output-dir",
                                str(insights_dir),
                            ]
                        )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            diagnostics = payload["review_fetch_diagnostics"][0]
            self.assertEqual(diagnostics["status"], "ok")
            self.assertEqual(diagnostics["entries_parsed"], 1)
            self.assertIn("jina_ai", diagnostics["source_candidates"])
            self.assertIn("direct", diagnostics["source_candidates"])
            self.assertEqual(diagnostics["pages"][0]["source"], "direct")
            self.assertEqual(diagnostics["pages"][0]["sources_tried"][0]["page_issue"], "blocked_page")

    def test_main_reports_blocked_failure_reason_but_does_not_fail_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )

            blocked_text = """
Sorry, we just need to make sure you're not a robot.
To discuss automated access to Amazon data please contact api-services-support@amazon.com.
"""

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", return_value=blocked_text):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "1",
                            "--strict-review-topics",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            diagnostics = payload["review_fetch_diagnostics"][0]
            self.assertEqual(diagnostics["status"], "failed")
            self.assertEqual(diagnostics["failure_reason"], "blocked_page")

    def test_main_strict_review_topics_still_fails_on_parsed_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )

            parsed_zero_text = "Customer reviews content loaded, but without parseable rating rows."

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", return_value=parsed_zero_text):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "1",
                            "--strict-review-topics",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 1)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            diagnostics = payload["review_fetch_diagnostics"][0]
            self.assertEqual(diagnostics["status"], "failed")
            self.assertEqual(diagnostics["failure_reason"], "parsed_zero")

    def test_main_treats_page_two_404_as_non_fatal_when_page_one_has_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )

            page_one = """
1. [5.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R1) Great quality
Sturdy and elegant.
"""

            class _Fake404Error(RuntimeError):
                def __init__(self, url: str) -> None:
                    super().__init__("HTTP Error 404: Not Found")
                    self.code = 404
                    self.url = url

            def _fake_fetch(url: str, **kwargs: object) -> str:
                if "pageNumber=2" in url:
                    raise _Fake404Error(url)
                return page_one

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_review_insights, "fetch_html", side_effect=_fake_fetch):
                    code = refresh_public_review_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--asin-limit",
                            "1",
                            "--pages-per-asin",
                            "2",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            diagnostics = payload["review_fetch_diagnostics"][0]
            self.assertEqual(diagnostics["status"], "ok")
            self.assertEqual(diagnostics["entries_parsed"], 1)
            self.assertEqual(diagnostics["failure_reason"], None)

    def test_main_strict_bypasses_mixed_page_not_found_and_parsed_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            web_data = base / "web-data"
            daily_dir = web_data / "daily"
            insights_dir = web_data / "insights"
            daily_dir.mkdir(parents=True, exist_ok=True)
            insights_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-03.json").write_text(
                json.dumps({"snapshot_date": "2026-03-03", "items": [{"asin": "B000000001", "rank": 1}]}),
                encoding="utf-8",
            )
            (insights_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2026-03-03",
                        "source": "public_search_keywords",
                        "keywords": [{"keyword": "candlestick", "impressions": 100}],
                        "monthly_sales": [],
                        "review_topics": [],
                        "style_trends": [],
                        "stats": {
                            "keyword_rows": 1,
                            "monthly_sales_rows": 0,
                            "review_topic_asins": 0,
                            "style_trend_rows": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            class _Fake404Error(RuntimeError):
                def __init__(self, url: str) -> None:
                    super().__init__("HTTP Error 404: Not Found")
                    self.code = 404
                    self.url = url

            def _fake_fetch(url: str, **kwargs: object) -> str:
                source = str(refresh_public_review_insights.os.environ.get("AMAZON_CRAWL_SOURCE") or "")
                if source == "direct":
                    raise _Fake404Error(url)
                return "customer reviews section loaded but no parseable rating line"

            with patch.object(refresh_public_review_insights, "WEB_DATA_DIR", web_data):
                with patch.dict(
                    refresh_public_review_insights.os.environ,
                    {"AMAZON_CRAWL_SOURCE": "direct", "AMAZON_REVIEW_PLAYWRIGHT": "0"},
                    clear=False,
                ):
                    with patch.object(refresh_public_review_insights, "fetch_html", side_effect=_fake_fetch):
                        code = refresh_public_review_insights.main(
                            [
                                "--snapshot-date",
                                "2026-03-03",
                                "--asin-limit",
                                "1",
                                "--pages-per-asin",
                                "1",
                                "--strict-review-topics",
                                "--insights-output-dir",
                                str(insights_dir),
                            ]
                        )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            diagnostics = payload["review_fetch_diagnostics"][0]
            self.assertEqual(diagnostics["status"], "failed")
            self.assertEqual(diagnostics["failure_reason"], "page_not_found")


if __name__ == "__main__":
    unittest.main()
