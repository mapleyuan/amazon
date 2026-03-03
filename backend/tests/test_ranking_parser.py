from __future__ import annotations

from pathlib import Path
import unittest


class RankingParserTests(unittest.TestCase):
    def test_parse_top_ranking_items_from_fixture(self) -> None:
        from app.crawler.parsers import parse_ranking_page

        html = Path("tests/fixtures/amazon_best_sellers_sample.html").read_text(encoding="utf-8")
        items = parse_ranking_page(html)

        self.assertGreater(len(items), 0)
        self.assertEqual(items[0]["rank"], 1)
        self.assertIsNotNone(items[0]["asin"])

    def test_parse_card_layout_with_title_price_and_rating(self) -> None:
        from app.crawler.parsers import parse_ranking_page

        html = """
        <li aria-roledescription="slide" class="a-carousel-card">
          <div data-asin="B08JHCVHTY">
            <span class="zg-bdg-text">#1</span>
            <a href="/Blink-Plus-Plan-monthly-auto-renewal/dp/B08JHCVHTY/ref=abc">
              <div class="p13n-sc-truncate">blink plus plan with monthly auto-renewal</div>
            </a>
            <a aria-label="4.4 out of 5 stars, 272,288 ratings"></a>
            <span class="_cDEzb_p13n-sc-price_3mJ9Z">$11.99</span>
            <img src="https://images-na.ssl-images-amazon.com/images/I/31YHGbJsldL._AC_UL225_SR225,160_.png"
                 class="p13n-product-image" />
          </div>
        </li>
        """
        items = parse_ranking_page(html)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "B08JHCVHTY")
        self.assertEqual(items[0]["rank"], 1)
        self.assertEqual(items[0]["title"], "blink plus plan with monthly auto-renewal")
        self.assertEqual(items[0]["price_text"], "$11.99")
        self.assertEqual(items[0]["rating"], 4.4)
        self.assertEqual(items[0]["review_count"], 272288)

    def test_parse_markdown_line_from_proxy_source(self) -> None:
        from app.crawler.parsers import parse_ranking_page

        markdown = """
1.   #1   [![Image 3](https://images-na.ssl-images-amazon.com/images/I/71Mcspt-6AL._AC_UL450_SR450,320_.jpg)](http://www.amazon.com/Medicube-Zero-Pore-Pads-Dual-Textured/dp/B09V7Z4TJG/ref=abc)[medicube Toner Pads Zero Pore Pad 2.0](http://www.amazon.com/Medicube-Zero-Pore-Pads-Dual-Textured/dp/B09V7Z4TJG/ref=abc)[_4.6 out of 5 stars_ 18,709](http://www.amazon.com/product-reviews/B09V7Z4TJG/ref=abc)  [$18.90](http://www.amazon.com/Medicube-Zero-Pore-Pads-Dual-Textured/dp/B09V7Z4TJG/ref=abc)
        """

        items = parse_ranking_page(markdown)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["asin"], "B09V7Z4TJG")
        self.assertEqual(items[0]["rank"], 1)
        self.assertEqual(items[0]["title"], "medicube Toner Pads Zero Pore Pad 2.0")
        self.assertEqual(items[0]["price_text"], "$18.90")
        self.assertEqual(items[0]["rating"], 4.6)
        self.assertEqual(items[0]["review_count"], 18709)

    def test_parse_category_links_supports_markdown_links(self) -> None:
        from app.crawler.parsers import parse_category_links

        markdown = """
[Best Sellers in Electronics](http://www.amazon.com/zgbs/electronics/ref=zg_bs_nav_electronics)
        """

        links = parse_category_links(markdown)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], "http://www.amazon.com/zgbs/electronics/ref=zg_bs_nav_electronics")
        self.assertEqual(links[0][1], "Best Sellers in Electronics")


if __name__ == "__main__":
    unittest.main()
