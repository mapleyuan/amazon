from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import refresh_public_review_insights


class RefreshPublicReviewInsightsScriptTests(unittest.TestCase):
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
            self.assertEqual(len(payload["review_topics"]), 1)
            self.assertGreaterEqual(payload["review_topics"][0]["sample_reviews"], 2)
            self.assertIn("avg_rating", payload["review_topics"][0])
            self.assertIn("rating_distribution", payload["review_topics"][0])
            self.assertIn("sentiment", payload["review_topics"][0])
            self.assertIn("positive_snippets", payload["review_topics"][0])
            self.assertIn("negative_snippets", payload["review_topics"][0])

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


if __name__ == "__main__":
    unittest.main()
