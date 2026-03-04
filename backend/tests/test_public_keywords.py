from __future__ import annotations

import unittest

from app.official_insights.public_keywords import (
    build_public_keyword_rows,
    extract_candidate_keywords,
    parse_search_signals,
)


class PublicKeywordInsightsTests(unittest.TestCase):
    def test_parse_search_signals(self) -> None:
        text = """
1-48 of over 12,345 results for "candlestick holder"
Sponsored Sponsored
[Item](https://www.amazon.com/dp/B000000001)
[Item](https://www.amazon.com/dp/B000000002)
"""
        parsed = parse_search_signals(text)
        self.assertEqual(parsed["result_count"], 12345)
        self.assertGreaterEqual(parsed["sponsored_count"], 2)
        self.assertEqual(parsed["top_asins"][:2], ["B000000001", "B000000002"])

    def test_extract_candidate_keywords(self) -> None:
        items = [
            {"title": "Gold Candlestick Holder Set", "rank": 1, "sales_month": 1000},
            {"title": "Black Candle Holder Home Decor", "rank": 2, "sales_month": 800},
        ]
        rows = extract_candidate_keywords(items, max_keywords=8)
        self.assertTrue(rows)
        self.assertIn("candlestick holder", rows)

    def test_build_public_keyword_rows(self) -> None:
        signals = [
            {
                "keyword": "candlestick holder",
                "result_count": 12000,
                "sponsored_count": 4,
                "top_asins": ["B000000001", "B000000002", "B000000003"],
            }
        ]
        sales = {"B000000001": 300, "B000000004": 200}
        rows = build_public_keyword_rows(signals, sales)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["keyword"], "candlestick holder")
        self.assertEqual(rows[0]["impressions"], 12000)
        self.assertEqual(rows[0]["top_asin_overlap"], 1)
        self.assertGreaterEqual(rows[0]["cvr"], 0)


if __name__ == "__main__":
    unittest.main()
