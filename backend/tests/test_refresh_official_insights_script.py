from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts import refresh_official_insights


class RefreshOfficialInsightsScriptTests(unittest.TestCase):
    def test_main_builds_insights_from_local_files_without_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            keywords_csv = base / "keywords.csv"
            sales_json = base / "sales.json"
            review_json = base / "reviews.json"
            style_csv = base / "style.csv"
            out_dir = base / "insights"

            keywords_csv.write_text(
                "search_term,impressions,clicks,purchases,month\n"
                "candlestick holder,1000,100,20,2026-03-01\n",
                encoding="utf-8",
            )
            sales_json.write_text(
                json.dumps(
                    {
                        "salesByDate": [
                            {
                                "date": "2026-03-01",
                                "unitsOrdered": 300,
                                "orderedProductSales": {"amount": "5999.99", "currencyCode": "USD"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            review_json.write_text(
                json.dumps(
                    [
                        {
                            "asin": "B000000001",
                            "positive_topics": [{"topic": "quality", "mentions": 100}],
                            "negative_topics": [{"topic": "fragile", "mentions": 22}],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            style_csv.write_text("style,month,score\ngold,2026-03-01,1200\n", encoding="utf-8")

            code = refresh_official_insights.main(
                [
                    "--snapshot-date",
                    "2026-03-03",
                    "--skip-fetch",
                    "--keywords-path",
                    str(keywords_csv),
                    "--sales-path",
                    str(sales_json),
                    "--review-topics-path",
                    str(review_json),
                    "--style-path",
                    str(style_csv),
                    "--insights-output-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(code, 0)

            output = out_dir / "2026-03-03.json"
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["keyword_rows"], 1)
            self.assertEqual(payload["stats"]["monthly_sales_rows"], 1)
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            self.assertEqual(payload["stats"]["style_trend_rows"], 1)

    def test_main_strict_fails_when_no_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "insights"
            code = refresh_official_insights.main(
                [
                    "--snapshot-date",
                    "2026-03-03",
                    "--skip-fetch",
                    "--strict",
                    "--insights-output-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

