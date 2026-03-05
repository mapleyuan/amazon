from __future__ import annotations

import unittest

from app.official_insights.public_reviews import (
    build_review_topic_summary,
    classify_review_page,
    parse_review_entries,
    parse_review_entries_from_product_html,
)


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

    def test_parse_review_entries_supports_multiple_rating_formats(self) -> None:
        markdown = """
1. ★★★★☆ Elegant and sturdy
Looks premium and sturdy metal base.

2. [4.5/5](https://www.amazon.com/gp/customer-reviews/R2) Great value
Worth the money for home decor.

3. Rating: 3.0 out of 5 Fair
Average finish but acceptable.
"""
        rows = parse_review_entries(markdown)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["rating"], 4.0)
        self.assertEqual(rows[1]["rating"], 4.5)
        self.assertEqual(rows[2]["rating"], 3.0)

    def test_classify_review_page_detects_robot_block(self) -> None:
        blocked = """
Sorry, we just need to make sure you're not a robot.
To discuss automated access to Amazon data please contact api-services-support@amazon.com.
"""
        self.assertEqual(classify_review_page(blocked), "blocked_page")
        self.assertIsNone(classify_review_page("normal content with ratings and comments"))

    def test_parse_review_entries_from_product_html(self) -> None:
        html = """
<div data-hook="review">
  <a data-hook="review-title"><span>Looks premium</span></a>
  <i data-hook="review-star-rating"><span>5.0 out of 5 stars</span></i>
  <span data-hook="review-body"><span>Beautiful finish and sturdy base.</span></span>
</div>
<div data-hook="review">
  <a data-hook="review-title"><span>Too fragile</span></a>
  <i data-hook="review-star-rating"><span>1.0 out of 5 stars</span></i>
  <span data-hook="review-body"><span>Arrived cracked and broke after one day.</span></span>
</div>
"""
        rows = parse_review_entries_from_product_html(html, limit=5)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["rating"], 5.0)
        self.assertIn("sturdy", rows[0]["text"].lower())
        self.assertEqual(rows[1]["rating"], 1.0)
        self.assertIn("cracked", rows[1]["text"].lower())


if __name__ == "__main__":
    unittest.main()
