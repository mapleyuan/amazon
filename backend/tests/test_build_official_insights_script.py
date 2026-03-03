from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_official_insights


class BuildOfficialInsightsScriptTests(unittest.TestCase):
    def test_main_builds_insights_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            keywords_csv = base / "keywords.csv"
            sales_csv = base / "sales.csv"
            review_json = base / "review_topics.json"
            style_csv = base / "style.csv"
            output_dir = base / "out"

            keywords_csv.write_text(
                "search_term,impressions,clicks,purchases,month\n"
                "candlestick holder,1000,150,24,2026-03-01\n",
                encoding="utf-8",
            )
            sales_csv.write_text(
                "asin,month,units_ordered,ordered_product_sales\n"
                "B000000001,2026-03-01,320,9999.9\n",
                encoding="utf-8",
            )
            review_json.write_text(
                json.dumps(
                    [
                        {
                            "asin": "B000000001",
                            "positive_topics": [{"topic": "quality", "mentions": 100}],
                            "negative_topics": [{"topic": "fragile", "mentions": 25}],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            style_csv.write_text(
                "style,month,score\n"
                "gold,2026-03-01,3000\n",
                encoding="utf-8",
            )

            code = build_official_insights.main(
                [
                    "--snapshot-date",
                    "2026-03-03",
                    "--keywords-csv",
                    str(keywords_csv),
                    "--monthly-sales-csv",
                    str(sales_csv),
                    "--review-topics-json",
                    str(review_json),
                    "--style-trends-csv",
                    str(style_csv),
                    "--output-dir",
                    str(output_dir),
                ]
            )
            self.assertEqual(code, 0)

            output_path = output_dir / "2026-03-03.json"
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["snapshot_date"], "2026-03-03")
            self.assertEqual(payload["stats"]["keyword_rows"], 1)
            self.assertEqual(payload["stats"]["monthly_sales_rows"], 1)
            self.assertEqual(payload["stats"]["review_topic_asins"], 1)
            self.assertEqual(payload["stats"]["style_trend_rows"], 1)

    def test_main_strict_returns_non_zero_when_no_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            code = build_official_insights.main(
                [
                    "--snapshot-date",
                    "2026-03-03",
                    "--output-dir",
                    str(output_dir),
                    "--strict",
                ]
            )
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

