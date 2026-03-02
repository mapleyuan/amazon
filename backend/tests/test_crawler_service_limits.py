from __future__ import annotations

from unittest.mock import patch
import unittest


class CrawlerServiceLimitTests(unittest.TestCase):
    def test_crawl_site_board_respects_category_limit(self) -> None:
        from app.core.settings import Settings
        from app.crawler import service

        fake_settings = Settings(
            db_path=":memory:",
            host="127.0.0.1",
            port=8000,
            cron_hour_utc=2,
            cron_minute_utc=0,
            mock_crawl=False,
            manual_limit_per_site=3,
            detail_enrich_limit=0,
            crawl_category_limit=2,
        )

        parsed_items = [
            {
                "asin": "B000000001",
                "rank": 1,
                "title": "Product 1",
                "price_text": "$9.99",
                "rating": 4.5,
                "review_count": 100,
                "detail_url": "/dp/B000000001",
            }
        ]

        with patch.object(service, "get_settings", return_value=fake_settings):
            with patch.object(service, "fetch_html", side_effect=["board", "cat1", "cat2"]):
                with patch.object(service, "contains_block_page", return_value=False):
                    with patch.object(
                        service,
                        "parse_category_links",
                        return_value=[
                            ("/c1", "Category 1"),
                            ("/c2", "Category 2"),
                            ("/c3", "Category 3"),
                        ],
                    ):
                        with patch.object(service, "parse_ranking_page", return_value=parsed_items):
                            rows = service.crawl_site_board("amazon.com", "best_sellers")

        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["category_name"] for row in rows}), 2)


if __name__ == "__main__":
    unittest.main()
