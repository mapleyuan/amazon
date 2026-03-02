from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PublishStaticDataScriptTests(unittest.TestCase):
    def test_publish_writes_manifest_and_daily_file(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "cat-1",
                                "category_name": "Electronics",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Product 1",
                                "brand": "Brand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main([])

                self.assertEqual(code, 0)
                self.assertTrue((base / "data" / "manifest.json").exists())
                self.assertTrue((base / "data" / "daily" / "2026-03-02.json").exists())

    def test_manifest_contains_frontend_contract_keys(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "cat-1",
                                "category_name": "Electronics",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Product 1",
                                "brand": "Brand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main([])

                self.assertEqual(code, 0)
                manifest_text = (base / "data" / "manifest.json").read_text(encoding="utf-8")

                self.assertIn('"available_dates"', manifest_text)
                self.assertIn('"last_success_date"', manifest_text)
                self.assertIn('"status"', manifest_text)
                self.assertIn('"default_filters"', manifest_text)


if __name__ == "__main__":
    unittest.main()
