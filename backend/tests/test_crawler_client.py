from __future__ import annotations

from unittest.mock import patch
import unittest

from app.core.settings import Settings


class _FakeResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.read_calls: list[int] = []

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        self.read_calls.append(size)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class CrawlerClientTests(unittest.TestCase):
    def test_fetch_html_reads_in_chunks_and_decodes(self) -> None:
        from app.crawler import client

        fake = _FakeResponse([b"<html>", b"ok", b"</html>", b""])
        with patch.object(client, "urlopen", return_value=fake):
            with patch.object(client.random, "uniform", return_value=0.0):
                with patch.object(client.time, "sleep", return_value=None):
                    with patch.object(client, "get_settings", return_value=_settings(source="direct")):
                        html = client.fetch_html("https://example.com", site="amazon.com", timeout=1)

        self.assertIn("<html>ok</html>", html)
        self.assertGreaterEqual(len(fake.read_calls), 2)

    def test_fetch_html_respects_max_bytes(self) -> None:
        from app.crawler import client

        class EndlessResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size: int = -1) -> bytes:
                if size <= 0:
                    size = 1
                return b"a" * size

        with patch.object(client, "urlopen", return_value=EndlessResponse()):
            with patch.object(client.random, "uniform", return_value=0.0):
                with patch.object(client.time, "sleep", return_value=None):
                    with patch.object(client, "get_settings", return_value=_settings(source="direct")):
                        html = client.fetch_html(
                            "https://example.com",
                            site="amazon.com",
                            timeout=1,
                            max_bytes=1024,
                        )

        self.assertEqual(len(html), 1024)

    def test_fetch_html_jina_source_rewrites_url(self) -> None:
        from app.crawler import client

        fake = _FakeResponse([b"ok"])
        with patch.object(client, "urlopen", return_value=fake) as mocked_open:
            with patch.object(client.random, "uniform", return_value=0.0):
                with patch.object(client.time, "sleep", return_value=None):
                    with patch.object(client, "get_settings", return_value=_settings(source="jina_ai")):
                        client.fetch_html("https://www.amazon.com/gp/bestsellers", site="amazon.com", timeout=1)

        request = mocked_open.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://r.jina.ai/http://www.amazon.com/gp/bestsellers",
        )

    def test_fetch_html_proxy_template_requires_placeholder(self) -> None:
        from app.crawler import client

        with self.assertRaises(RuntimeError):
            client._resolve_fetch_url(
                "https://example.com",
                source="proxy_template",
                proxy_template="https://proxy.invalid/fetch",
            )


def _settings(*, source: str, proxy_template: str = "") -> Settings:
    return Settings(
        db_path=":memory:",
        host="127.0.0.1",
        port=8000,
        cron_hour_utc=2,
        cron_minute_utc=0,
        mock_crawl=False,
        manual_limit_per_site=3,
        detail_enrich_limit=0,
        crawl_category_limit=20,
        crawl_source=source,
        crawl_proxy_template=proxy_template,
        crawl_cookie="",
        crawl_referer="",
    )


if __name__ == "__main__":
    unittest.main()
