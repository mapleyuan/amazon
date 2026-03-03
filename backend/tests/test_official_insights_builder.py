from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.official_insights.builder import (
    build_official_insights_payload,
    derive_style_trends_from_keywords,
    parse_keywords_rows_from_csv,
    parse_keywords_rows_from_json,
    parse_monthly_sales_rows_from_csv,
    parse_monthly_sales_rows_from_json,
    parse_review_topics_from_json,
    parse_style_trend_rows_from_csv,
    parse_style_trend_rows_from_json,
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

    def test_parse_keywords_rows_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keywords.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "search_term": "candle holder",
                                "impressions": 1200,
                                "clicks": 130,
                                "purchases": 26,
                                "month": "2026-03-01",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = parse_keywords_rows_from_json(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["keyword"], "candle holder")
            self.assertEqual(rows[0]["month"], "2026-03")

    def test_parse_keywords_rows_from_sqp_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sqp.json"
            path.write_text(
                json.dumps(
                    {
                        "dataByAsin": [
                            {
                                "asin": "B000000001",
                                "startDate": "2026-02-01",
                                "searchQueryData": {"searchQuery": "gold candlestick holder"},
                                "impressionData": {"asinImpressionCount": 1234},
                                "clickData": {"asinClickCount": 234},
                                "cartAddData": {"asinCartAddCount": 56},
                                "purchaseData": {"asinPurchaseCount": 44},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = parse_keywords_rows_from_json(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["keyword"], "gold candlestick holder")
            self.assertEqual(rows[0]["asin"], "B000000001")
            self.assertEqual(rows[0]["impressions"], 1234)
            self.assertEqual(rows[0]["clicks"], 234)
            self.assertEqual(rows[0]["purchases"], 44)
            self.assertEqual(rows[0]["month"], "2026-02")

    def test_parse_monthly_sales_rows_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.json"
            path.write_text(
                json.dumps(
                    {
                        "salesByDate": [
                            {
                                "date": "2026-03-21",
                                "unitsOrdered": 123,
                                "orderedProductSales": {"amount": "4567.89"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = parse_monthly_sales_rows_from_json(path)
            self.assertEqual(rows, [{"asin": "", "month": "2026-03", "units": 123, "revenue": 4567.89}])

    def test_parse_monthly_sales_rows_from_sales_and_traffic_by_asin_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales_asin.json"
            path.write_text(
                json.dumps(
                    {
                        "salesAndTrafficByAsin": [
                            {
                                "childAsin": "B000000001",
                                "startDate": "2026-03-01",
                                "salesByAsin": {
                                    "unitsOrdered": 321,
                                    "orderedProductSales": {"amount": "8765.40"},
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = parse_monthly_sales_rows_from_json(path)
            self.assertEqual(rows, [{"asin": "B000000001", "month": "2026-03", "units": 321, "revenue": 8765.4}])

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

    def test_parse_review_topics_from_customer_feedback_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review_topics_cf.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "asin": "B000000001",
                                "reviewTopics": [
                                    {
                                        "topicName": "quality",
                                        "starRatingImpact": 0.7,
                                        "topicMentions": {"positive": 28, "negative": 3},
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = parse_review_topics_from_json(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["asin"], "B000000001")
            self.assertEqual(rows[0]["positive_topics"][0]["topic"], "quality")
            self.assertEqual(rows[0]["positive_topics"][0]["mentions"], 28)
            self.assertEqual(rows[0]["negative_topics"][0]["mentions"], 3)

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

    def test_parse_style_trend_rows_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "style.json"
            path.write_text(
                json.dumps({"items": [{"style": "minimal", "month": "2026-03-01", "score": 998}]}),
                encoding="utf-8",
            )
            rows = parse_style_trend_rows_from_json(path)
            self.assertEqual(rows, [{"style": "minimal", "month": "2026-03", "score": 998.0}])

    def test_derive_style_trends_from_keywords(self) -> None:
        rows = derive_style_trends_from_keywords(
            [
                {"keyword": "gold candlestick holder", "month": "2026-03", "impressions": 1000},
                {"keyword": "black candle holder", "month": "2026-03", "impressions": 600},
            ]
        )
        self.assertTrue(rows)
        self.assertEqual(rows[0]["month"], "2026-03")

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
