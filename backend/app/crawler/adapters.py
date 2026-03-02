from __future__ import annotations

BOARD_PATHS = {
    # Amazon ranking root paths across locales.
    "best_sellers": "gp/bestsellers",
    "new_releases": "gp/new-releases",
    "movers_and_shakers": "gp/movers-and-shakers",
}

SITE_BASE = {
    "amazon.com": "https://www.amazon.com",
    "amazon.co.jp": "https://www.amazon.co.jp",
    "amazon.co.uk": "https://www.amazon.co.uk",
}

ACCEPT_LANG = {
    "amazon.com": "en-US,en;q=0.9",
    "amazon.co.jp": "ja-JP,ja;q=0.9,en;q=0.8",
    "amazon.co.uk": "en-GB,en;q=0.9",
}


def build_board_url(site: str, board_type: str) -> str:
    base = SITE_BASE[site]
    path = BOARD_PATHS[board_type]
    return f"{base}/{path}"
