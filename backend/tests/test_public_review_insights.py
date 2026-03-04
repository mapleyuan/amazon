from __future__ import annotations

import unittest

from app.official_insights.public_reviews import build_review_topic_summary, parse_review_entries


class PublicReviewInsightsTests(unittest.TestCase):
    def test_parse_review_entries_from_markdown(self) -> None:
        markdown = """
1. [5.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R1) Elegant and sturdy
Looks premium and sturdy metal base.

2. [1.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R2) Broke quickly
Arrived bent and unstable after one week.

3. [4.0 out of 5 stars](https://www.amazon.com/gp/customer-reviews/R3) Nice for home decor
Beautiful finish and easy setup.
"""
        rows = parse_review_entries(markdown)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["rating"], 5.0)
        self.assertIn("sturdy", rows[0]["text"].lower())
        self.assertEqual(rows[1]["rating"], 1.0)
        self.assertIn("unstable", rows[1]["text"].lower())

    def test_build_review_topic_summary(self) -> None:
        entries = [
            {"rating": 5.0, "text": "sturdy elegant quality finish"},
            {"rating": 4.0, "text": "elegant quality design"},
            {"rating": 1.0, "text": "broke unstable bent fragile"},
            {"rating": 2.0, "text": "unstable poor quality control"},
        ]

        summary = build_review_topic_summary(entries, top_n=3, min_mentions=1)
        self.assertGreaterEqual(summary["sample_reviews"], 4)
        positive = [item["topic"] for item in summary["positive_topics"]]
        negative = [item["topic"] for item in summary["negative_topics"]]
        self.assertIn("elegant", positive)
        self.assertIn("unstable", negative)
        self.assertAlmostEqual(summary["avg_rating"], 3.0)
        self.assertEqual(summary["rating_distribution"]["5"], 1)
        self.assertEqual(summary["rating_distribution"]["1"], 1)
        self.assertEqual(summary["sentiment"]["positive"], 2)
        self.assertEqual(summary["sentiment"]["negative"], 2)
        self.assertTrue(summary["positive_snippets"])
        self.assertTrue(summary["negative_snippets"])


if __name__ == "__main__":
    unittest.main()
