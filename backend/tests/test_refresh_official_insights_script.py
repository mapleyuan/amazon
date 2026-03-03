from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_main_derives_style_trends_from_keywords_when_style_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            keywords_csv = base / "keywords.csv"
            out_dir = base / "insights"
            keywords_csv.write_text(
                "search_term,impressions,month\n"
                "gold candlestick holder,1000,2026-03-01\n"
                "black candle holder,600,2026-03-01\n",
                encoding="utf-8",
            )

            code = refresh_official_insights.main(
                [
                    "--snapshot-date",
                    "2026-03-03",
                    "--skip-fetch",
                    "--keywords-path",
                    str(keywords_csv),
                    "--skip-sales",
                    "--skip-reviews",
                    "--insights-output-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads((out_dir / "2026-03-03.json").read_text(encoding="utf-8"))
            self.assertGreater(payload["stats"]["style_trend_rows"], 0)

    def test_build_keywords_report_options_uses_asins(self) -> None:
        args = refresh_official_insights._parse_args(
            [
                "--keywords-report-type",
                "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT",
                "--keywords-asins",
                "B000000001, B000000002",
            ]
        )
        options = refresh_official_insights._build_keywords_report_options(args, "2026-03-03")
        self.assertEqual(options["reportPeriod"], "MONTH")
        self.assertEqual(options["asin"], "B000000001 B000000002")

    def test_load_asins_from_daily_uses_rank_order_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_data = Path(temp_dir) / "web-data"
            daily_dir = temp_data / "daily"
            daily_dir.mkdir(parents=True, exist_ok=True)
            (daily_dir / "2026-03-03.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"asin": "B000000002", "rank": 2},
                            {"asin": "B000000001", "rank": 1},
                            {"asin": "B000000001", "rank": 3},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(refresh_official_insights, "WEB_DATA_DIR", temp_data):
                asins = refresh_official_insights._load_asins_from_daily("2026-03-03", 10)
            self.assertEqual(asins, ["B000000001", "B000000002"])


if __name__ == "__main__":
    unittest.main()
