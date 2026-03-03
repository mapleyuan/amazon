from __future__ import annotations

import html
import math
import re

_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")
_RANK_RE = re.compile(r"#\s*(\d{1,3})")
_PRICE_RE = re.compile(r"(?:[$£¥]\s*\d+[\d,.]*)")
_RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*out of\s*5\s*stars", re.IGNORECASE)
_REVIEW_RE = re.compile(r"(\d[\d,]*)\s*(?:ratings|reviews)", re.IGNORECASE)
_REVIEW_RE_JP = re.compile(r"([\d,]+)\s*個の評価")
_BOUGHT_MONTH_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\+?\s*bought in past month", re.IGNORECASE)
_BOUGHT_MONTH_RE_JP = re.compile(r"過去1か月で\s*([\d,]+)\s*点以上購入", re.IGNORECASE)
_CARD_RE = re.compile(
    r'<li[^>]*>\s*<div[^>]*data-asin="([A-Z0-9]{10})"[^>]*>(.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
_MD_RANK_RE = re.compile(r"^\s*\d+\.\s*#\s*(\d{1,3})", re.IGNORECASE)
_MD_TITLE_RE = re.compile(r"\)\[([^\]]+)\]\([^)]*/dp/[A-Z0-9]{10}[^)]*\)", re.IGNORECASE)
_MD_RATING_RE = re.compile(r"_?(\d(?:\.\d)?)\s*out of 5 stars_?\s*([\d,]+)", re.IGNORECASE)
_MD_DETAIL_RE = re.compile(r"\((https?://[^)]+/dp/[A-Z0-9]{10}[^)]*)\)", re.IGNORECASE)


def _extract_blocks(html_text: str) -> list[str]:
    blocks = re.findall(
        r'(<div[^>]+class="[^"]*zg-grid-general-faceout[^"]*"[^>]*>.*?</div>)',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    return blocks


def _clean_text(raw: str) -> str:
    value = re.sub(r"<[^>]+>", "", raw)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_number(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    return int(digits)


def _extract_title(block: str, asin: str) -> str:
    title_match = re.search(
        rf'<a[^>]+href="[^"]*/dp/{asin}[^"]*"[^>]*>(.*?)</a>',
        block,
        re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return ""

    return _clean_text(title_match.group(1))


def _title_from_href(href: str, asin: str) -> str:
    marker = f"/dp/{asin}"
    idx = href.find(marker)
    if idx <= 0:
        return ""
    prefix = href[:idx].strip("/")
    if not prefix:
        return ""
    slug = prefix.rsplit("/", 1)[-1]
    slug = slug.replace("-", " ")
    title = re.sub(r"\s+", " ", slug).strip()
    return title


def _parse_monthly_sales_signal(text: str) -> int | None:
    match = _BOUGHT_MONTH_RE.search(text)
    if match:
        raw_num = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").lower()
        try:
            value = float(raw_num)
        except ValueError:
            return None

        multiplier = 1
        if suffix == "k":
            multiplier = 1000
        elif suffix == "m":
            multiplier = 1_000_000
        month = int(round(value * multiplier))
        return month if month > 0 else None

    jp_match = _BOUGHT_MONTH_RE_JP.search(text)
    if jp_match:
        parsed = _parse_number(jp_match.group(1))
        return parsed if parsed and parsed > 0 else None

    return None


def _estimate_sales_fields(rank: int, monthly_signal: int | None) -> tuple[int, int, int]:
    if monthly_signal is not None and monthly_signal > 0:
        month = int(monthly_signal)
    else:
        # Fallback model based on bestseller rank when "bought in past month" is absent.
        month = max(1, int(round(2500 / math.pow(max(1, rank), 0.7))))

    day = max(1, int(round(month / 30)))
    year = month * 12
    return day, month, year


def _parse_items_from_cards(html_text: str) -> list[dict]:
    items: list[dict] = []
    cards = _CARD_RE.findall(html_text)
    if not cards:
        return items

    for idx, (asin, block) in enumerate(cards, start=1):
        rank_match = re.search(
            r'class="[^"]*zg-bdg-text[^"]*"[^>]*>\s*#?(\d{1,3})\s*<',
            block,
            re.IGNORECASE,
        )
        rank = int(rank_match.group(1)) if rank_match else idx
        if rank <= 0 or rank > 100:
            rank = idx

        href_match = re.search(
            rf'href="([^"]*/dp/{asin}[^"]*)"',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        href = html.unescape(href_match.group(1)) if href_match else f"/dp/{asin}"

        title_match = re.search(
            r'class="[^"]*p13n-sc-truncate[^"]*"[^>]*>(.*?)</div>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        title = _clean_text(title_match.group(1)) if title_match else ""
        if not title and href:
            title = _title_from_href(href, asin)

        price_match = re.search(
            r'class="[^"]*p13n-sc-price[^"]*"[^>]*>(.*?)</span>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        price_text = _clean_text(price_match.group(1)) if price_match else None
        if not price_text:
            fallback_price = _PRICE_RE.search(block)
            price_text = fallback_price.group(0) if fallback_price else None

        rating = None
        review_count = None
        rating_review_aria = re.search(
            r'aria-label="([0-5](?:\.\d)?)\s*out of 5 stars,\s*([\d,]+)\s*ratings"',
            block,
            re.IGNORECASE,
        )
        if rating_review_aria:
            rating = float(rating_review_aria.group(1))
            review_count = _parse_number(rating_review_aria.group(2))
        else:
            rating_match = _RATING_RE.search(block)
            if rating_match:
                rating = float(rating_match.group(1))
            review_match = _REVIEW_RE.search(block)
            if review_match:
                review_count = _parse_number(review_match.group(1))

        image_match = re.search(
            r'<img[^>]+src="([^"]+)"[^>]+class="[^"]*p13n-product-image[^"]*"',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        image_url = image_match.group(1) if image_match else None
        monthly_signal = _parse_monthly_sales_signal(block)
        sales_day, sales_month, sales_year = _estimate_sales_fields(rank, monthly_signal)

        items.append(
            {
                "rank": rank,
                "asin": asin,
                "title": title,
                "price_text": price_text,
                "rating": rating,
                "review_count": review_count,
                "sales_day": sales_day,
                "sales_month": sales_month,
                "sales_year": sales_year,
                "image_url": image_url,
                "detail_url": href or f"/dp/{asin}",
            }
        )

    return items


def _parse_items_from_markdown(html_text: str) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[int, str]] = set()

    for line in html_text.splitlines():
        if "/dp/" not in line or "#" not in line:
            continue

        rank_match = _MD_RANK_RE.match(line)
        asin_match = _ASIN_RE.search(line)
        if not rank_match or not asin_match:
            continue

        rank = int(rank_match.group(1))
        if rank <= 0 or rank > 100:
            continue

        asin = asin_match.group(1)
        key = (rank, asin)
        if key in seen:
            continue
        seen.add(key)

        title = ""
        title_match = _MD_TITLE_RE.search(line)
        if title_match:
            title = _clean_text(title_match.group(1))
            if title.lower().startswith("!image"):
                title = ""

        rating = None
        review_count = None
        rating_match = _MD_RATING_RE.search(line)
        if rating_match:
            rating = float(rating_match.group(1))
            review_count = _parse_number(rating_match.group(2))
        else:
            fallback_rating = _RATING_RE.search(line)
            if fallback_rating:
                rating = float(fallback_rating.group(1))
            fallback_reviews = _REVIEW_RE.search(line) or _REVIEW_RE_JP.search(line)
            if fallback_reviews:
                review_count = _parse_number(fallback_reviews.group(1))

        detail_url = f"/dp/{asin}"
        detail_match = _MD_DETAIL_RE.search(line)
        if detail_match:
            detail_url = html.unescape(detail_match.group(1))

        price_match = _PRICE_RE.search(line)
        price_text = price_match.group(0) if price_match else None
        monthly_signal = _parse_monthly_sales_signal(line)
        sales_day, sales_month, sales_year = _estimate_sales_fields(rank, monthly_signal)

        items.append(
            {
                "rank": rank,
                "asin": asin,
                "title": title,
                "price_text": price_text,
                "rating": rating,
                "review_count": review_count,
                "sales_day": sales_day,
                "sales_month": sales_month,
                "sales_year": sales_year,
                "detail_url": detail_url,
            }
        )

    return items


def parse_ranking_page(html_text: str) -> list[dict]:
    items = _parse_items_from_cards(html_text)
    if items:
        unique: dict[tuple[int, str], dict] = {}
        for item in items:
            key = (int(item["rank"]), str(item["asin"]))
            unique[key] = item
        return [unique[key] for key in sorted(unique)]

    items = _parse_items_from_markdown(html_text)
    if items:
        unique: dict[tuple[int, str], dict] = {}
        for item in items:
            key = (int(item["rank"]), str(item["asin"]))
            unique[key] = item
        return [unique[key] for key in sorted(unique)]

    blocks = _extract_blocks(html_text)
    items = []

    if blocks:
        for idx, block in enumerate(blocks, start=1):
            asin_match = _ASIN_RE.search(block)
            if not asin_match:
                continue

            rank_match = _RANK_RE.search(block)
            price_match = _PRICE_RE.search(block)
            rating_match = _RATING_RE.search(block)
            review_match = _REVIEW_RE.search(block)

            asin = asin_match.group(1)
            rank = int(rank_match.group(1)) if rank_match else idx
            if rank <= 0 or rank > 100:
                rank = idx
            title = _extract_title(block, asin)
            monthly_signal = _parse_monthly_sales_signal(block)
            sales_day, sales_month, sales_year = _estimate_sales_fields(rank, monthly_signal)

            items.append(
                {
                    "rank": rank,
                    "asin": asin,
                    "title": title,
                    "price_text": price_match.group(0) if price_match else None,
                    "rating": float(rating_match.group(1)) if rating_match else None,
                    "review_count": int(review_match.group(1).replace(",", "")) if review_match else None,
                    "sales_day": sales_day,
                    "sales_month": sales_month,
                    "sales_year": sales_year,
                    "detail_url": f"/dp/{asin}",
                }
            )
    else:
        asins = _ASIN_RE.findall(html_text)
        ranks = _RANK_RE.findall(html_text)
        for idx, asin in enumerate(asins, start=1):
            rank = int(ranks[idx - 1]) if idx - 1 < len(ranks) else idx
            if rank <= 0 or rank > 100:
                rank = idx
            sales_day, sales_month, sales_year = _estimate_sales_fields(rank, None)
            items.append(
                {
                    "rank": rank,
                    "asin": asin,
                    "title": "",
                    "price_text": None,
                    "rating": None,
                    "review_count": None,
                    "sales_day": sales_day,
                    "sales_month": sales_month,
                    "sales_year": sales_year,
                    "detail_url": f"/dp/{asin}",
                }
            )

    unique: dict[tuple[int, str], dict] = {}
    for item in items:
        key = (int(item["rank"]), str(item["asin"]))
        unique[key] = item

    return [unique[key] for key in sorted(unique)]


def parse_category_links(html_text: str) -> list[tuple[str, str]]:
    links = re.findall(
        (
            r'<a[^>]+href="([^"]*/(?:gp/bestsellers|gp/new-releases|gp/movers-and-shakers|'
            r'zgbs|new-releases|movers-and-shakers)[^"]*)"[^>]*>(.*?)</a>'
        ),
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for href, label in links:
        clean_href = html.unescape(href)
        if clean_href in seen:
            continue
        seen.add(clean_href)

        clean_label = _clean_text(label) or clean_href.rsplit("/", 1)[-1]
        results.append((clean_href, clean_label))

    md_links = re.findall(
        (
            r"\[([^\]]+)\]\((https?://[^)]+/(?:gp/bestsellers|gp/new-releases|gp/movers-and-shakers|"
            r"zgbs|new-releases|movers-and-shakers)[^)]+)\)"
        ),
        html_text,
        re.IGNORECASE,
    )
    for label, href in md_links:
        clean_href = html.unescape(href)
        if clean_href in seen:
            continue
        seen.add(clean_href)

        clean_label = _clean_text(label) or clean_href.rsplit("/", 1)[-1]
        results.append((clean_href, clean_label))

    return results


def contains_block_page(html_text: str) -> bool:
    lowered = html_text.lower()
    return (
        "enter the characters you see below" in lowered
        or "robot check" in lowered
        or "captcha" in lowered
        or "max challenge attempts exceeded" in lowered
    )


def parse_product_detail(html_text: str, asin: str) -> dict:
    title = None
    price_text = None
    rating = None
    review_count = None
    brand = None
    image_url = None

    title_match = re.search(
        r'<span[^>]+id="productTitle"[^>]*>(.*?)</span>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if title_match:
        title = _clean_text(title_match.group(1))
    else:
        og_title_match = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            html_text,
            re.IGNORECASE,
        )
        if og_title_match:
            title = _clean_text(og_title_match.group(1))

    price_meta_amount = re.search(
        r'<meta[^>]+property="product:price:amount"[^>]+content="([^"]+)"',
        html_text,
        re.IGNORECASE,
    )
    price_meta_currency = re.search(
        r'<meta[^>]+property="product:price:currency"[^>]+content="([^"]+)"',
        html_text,
        re.IGNORECASE,
    )
    if price_meta_amount:
        amount = price_meta_amount.group(1).strip()
        currency = price_meta_currency.group(1).strip() if price_meta_currency else ""
        price_text = f"{currency} {amount}".strip()

    if not price_text:
        price_id_match = re.search(
            (
                r'<span[^>]+id="(?:priceblock_ourprice|priceblock_dealprice|priceblock_saleprice|'
                r'corePrice_feature_div)"[^>]*>(.*?)</span>'
            ),
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if price_id_match:
            price_text = _clean_text(price_id_match.group(1))

    if not price_text:
        offscreen_match = re.search(
            r'<span[^>]+class="[^"]*a-offscreen[^"]*"[^>]*>(.*?)</span>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if offscreen_match:
            price_text = _clean_text(offscreen_match.group(1))

    rating_match = _RATING_RE.search(html_text)
    if rating_match:
        rating = float(rating_match.group(1))
    else:
        rating_jp = re.search(r"(\d(?:\.\d)?)\s*5つ星のうち", html_text)
        if rating_jp:
            rating = float(rating_jp.group(1))

    review_match = _REVIEW_RE.search(html_text)
    if review_match:
        review_count = _parse_number(review_match.group(1))
    else:
        review_jp = _REVIEW_RE_JP.search(html_text)
        if review_jp:
            review_count = _parse_number(review_jp.group(1))

    brand_match = re.search(
        r'<a[^>]+id="bylineInfo"[^>]*>(.*?)</a>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if brand_match:
        brand = _clean_text(brand_match.group(1))
        brand = re.sub(r"^Visit the\s+", "", brand, flags=re.IGNORECASE)
        brand = re.sub(r"\s+Store$", "", brand, flags=re.IGNORECASE)
        brand = re.sub(r"^ブランド:\s*", "", brand)

    image_match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        html_text,
        re.IGNORECASE,
    )
    if image_match:
        image_url = image_match.group(1).strip()

    return {
        "asin": asin,
        "title": title,
        "price_text": price_text,
        "rating": rating,
        "review_count": review_count,
        "brand": brand,
        "image_url": image_url,
    }
