from __future__ import annotations

from pathlib import Path
import unittest


WEB_DIR = Path(__file__).resolve().parents[1] / "app" / "web"


class WebStaticUiContractTests(unittest.TestCase):
    def test_index_contains_status_source_quick_dates_compare_and_trend_controls(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="dataSource"', html)
        self.assertIn('id="recentDateButtons"', html)
        self.assertIn('id="compareYesterday"', html)
        self.assertIn("较昨日", html)
        self.assertIn("当日销量(估)", html)
        self.assertIn("近30天销量(估)", html)
        self.assertIn("近1年销量(估)", html)
        self.assertIn("销量趋势", html)
        self.assertIn('id="trendModal"', html)
        self.assertIn('id="trendClose"', html)
        self.assertIn('id="trendTitle"', html)
        self.assertIn('id="trendChart"', html)
        self.assertIn('id="trendTable"', html)
        self.assertIn('id="runInsights"', html)
        self.assertIn('id="analysisAsin"', html)
        self.assertIn('id="reviewInsights"', html)
        self.assertIn('id="trafficKeywords"', html)
        self.assertIn('id="conversionKeywords"', html)
        self.assertIn('id="monthlySalesInsights"', html)
        self.assertIn('id="styleTrendInsights"', html)

    def test_app_contains_compare_and_trend_logic_entrypoints(self) -> None:
        js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("function compareWithPreviousDay", js)
        self.assertIn("function showSalesTrendForItem", js)
        self.assertIn("function collectSalesTrendWithinOneYear", js)
        self.assertIn("function closeTrendModal", js)
        self.assertIn("function runCompetitiveInsights", js)
        self.assertIn("function collectScopeHistoryWithinOneYear", js)
        self.assertIn("function buildKeywordInsightRows", js)
        self.assertIn("function buildStyleTrendLines", js)
        self.assertIn("function populateAnalysisAsinOptions", js)
        self.assertIn("recentDateButtons", js)
        self.assertIn("dataSource", js)
        self.assertIn("sales_month", js)
        self.assertIn("trendModal", js)


if __name__ == "__main__":
    unittest.main()
