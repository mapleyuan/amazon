from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import refresh_public_keyword_insights


class RefreshPublicKeywordInsightsScriptTests(unittest.TestCase):
    def test_main_builds_keywords_from_public_search(self) -> None:
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
                            {
                                "asin": "B000000001",
                                "rank": 1,
                                "title": "Gold Candlestick Holder",
                                "sales_month": 300,
                            },
                            {
                                "asin": "B000000002",
                                "rank": 2,
                                "title": "Black Candle Holder",
                                "sales_month": 200,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            mock_text = """
1-48 of over 9,999 results for "candlestick holder"
Sponsored Sponsored
[Item](https://www.amazon.com/dp/B000000001)
"""

            with patch.object(refresh_public_keyword_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_keyword_insights, "fetch_html", return_value=mock_text):
                    code = refresh_public_keyword_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--keyword-limit",
                            "3",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "public_search_keywords")
            self.assertGreater(payload["stats"]["keyword_rows"], 0)

    def test_main_keeps_official_keywords_when_present(self) -> None:
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
                            {"asin": "B000000001", "rank": 1, "title": "Gold Candlestick Holder"}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            (insights_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2026-03-03",
                        "source": "official_reports",
                        "keywords": [{"keyword": "official term", "impressions": 123}],
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

            mock_text = "1-48 of over 999 results for candlestick"

            with patch.object(refresh_public_keyword_insights, "WEB_DATA_DIR", web_data):
                with patch.object(refresh_public_keyword_insights, "fetch_html", return_value=mock_text):
                    code = refresh_public_keyword_insights.main(
                        [
                            "--snapshot-date",
                            "2026-03-03",
                            "--keyword-limit",
                            "2",
                            "--insights-output-dir",
                            str(insights_dir),
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads((insights_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["keywords"][0]["keyword"], "official term")
            self.assertIn("official_reports", payload["source"])


if __name__ == "__main__":
    unittest.main()
