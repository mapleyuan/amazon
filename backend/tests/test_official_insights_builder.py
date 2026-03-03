from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.official_insights.builder import (
    build_official_insights_payload,
    parse_keywords_rows_from_csv,
    parse_monthly_sales_rows_from_csv,
    parse_review_topics_from_json,
    parse_style_trend_rows_from_csv,
)


class OfficialInsightsBuilderTests(unittest.TestCase):
    def test_parse_keywords_rows_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keywords.csv"
            path.write_text(
                "search_term,impressions,clicks,purchases,month\n"
                "candlestick holder,1000,120,18,2026-03-01\n"
                "gold candle holder,500,80,20,2026-03-15\n",
                encoding="utf-8",
            )

            rows = parse_keywords_rows_from_csv(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["keyword"], "candlestick holder")
            self.assertEqual(rows[0]["impressions"], 1000)
            self.assertEqual(rows[0]["clicks"], 120)
            self.assertEqual(rows[0]["purchases"], 18)
            self.assertEqual(rows[0]["month"], "2026-03")
            self.assertAlmostEqual(rows[0]["ctr"], 0.12)
            self.assertAlmostEqual(rows[0]["cvr"], 0.15)

    def test_parse_monthly_sales_rows_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.csv"
            path.write_text(
                "asin,month,units_ordered,ordered_product_sales\n"
                "B000000001,2026-03-01,320,8999.5\n",
                encoding="utf-8",
            )

            rows = parse_monthly_sales_rows_from_csv(path)
            self.assertEqual(rows, [{"asin": "B000000001", "month": "2026-03", "units": 320, "revenue": 8999.5}])

    def test_parse_review_topics_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review_topics.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "asin": "B000000001",
                            "positive_topics": [{"topic": "quality", "score": 0.8, "mentions": 80}],
                            "negative_topics": [{"topic": "fragile", "score": 0.7, "mentions": 23}],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            rows = parse_review_topics_from_json(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["asin"], "B000000001")
            self.assertEqual(rows[0]["positive_topics"][0]["topic"], "quality")
            self.assertEqual(rows[0]["negative_topics"][0]["topic"], "fragile")

    def test_parse_style_trend_rows_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "style.csv"
            path.write_text(
                "style,month,score\n"
                "gold,2026-03-01,3120\n"
                "black,2026-03-01,2810\n",
                encoding="utf-8",
            )
            rows = parse_style_trend_rows_from_csv(path)
            self.assertEqual(rows[0], {"style": "gold", "month": "2026-03", "score": 3120.0})

    def test_build_official_insights_payload(self) -> None:
        payload = build_official_insights_payload(
            snapshot_date="2026-03-03",
            generated_at="2026-03-03T12:00:00Z",
            keywords=[{"keyword": "candlestick", "impressions": 100}],
            monthly_sales=[{"asin": "B0001", "month": "2026-03", "units": 123}],
            review_topics=[{"asin": "B0001", "positive_topics": [], "negative_topics": []}],
            style_trends=[{"style": "gold", "month": "2026-03", "score": 1000}],
        )

        self.assertEqual(payload["snapshot_date"], "2026-03-03")
        self.assertEqual(payload["source"], "official_reports")
        self.assertEqual(payload["stats"]["keyword_rows"], 1)
        self.assertEqual(payload["stats"]["monthly_sales_rows"], 1)
        self.assertEqual(payload["stats"]["review_topic_asins"], 1)
        self.assertEqual(payload["stats"]["style_trend_rows"], 1)


if __name__ == "__main__":
    unittest.main()

