from __future__ import annotations

from collections import Counter
import math
import html
import re
from typing import Any

_STAR_PATTERNS = (
    re.compile(r"([1-5](?:[.,]\d)?)\s*out of\s*5\s*stars?", re.IGNORECASE),
    re.compile(r"([1-5](?:[.,]\d)?)\s*out of\s*5\b", re.IGNORECASE),
    re.compile(r"([1-5](?:[.,]\d)?)\s*/\s*5\b", re.IGNORECASE),
    re.compile(r"([1-5](?:[.,]\d)?)\s*stars?\b", re.IGNORECASE),
)
_STAR_GLYPH_RE = re.compile(r"(?:★|⭐){1,5}☆{0,5}")
_BLOCKED_PATTERNS = (
    re.compile(r"not\s+a\s+robot", re.IGNORECASE),
    re.compile(r"robot\s+check", re.IGNORECASE),
    re.compile(r"automated\s+access\s+to\s+amazon\s+data", re.IGNORECASE),
    re.compile(r"api-services-support@amazon\.com", re.IGNORECASE),
    re.compile(r"enter\s+the\s+characters\s+you\s+see\s+below", re.IGNORECASE),
    re.compile(r"captcha", re.IGNORECASE),
    re.compile(r"access\s+denied", re.IGNORECASE),
)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}")

_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "amazon",
    "arrived",
    "been",
    "before",
    "being",
    "better",
    "bought",
    "could",
    "does",
    "dont",
    "from",
    "good",
    "great",
    "have",
    "holder",
    "just",
    "like",
    "looks",
    "made",
    "more",
    "most",
    "nice",
    "only",
    "over",
    "product",
    "quality",
    "really",
    "review",
    "reviews",
    "stars",
    "still",
    "than",
    "that",
    "them",
    "they",
    "this",
    "very",
    "with",
    "would",
}


def _clean_line(raw: str) -> str:
    text = html.unescape(str(raw or ""))
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_rating(line: str) -> tuple[float | None, int]:
    text = str(line or "")

    for pattern in _STAR_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = str(match.group(1) or "").replace(",", ".")
        try:
            rating = float(raw)
        except ValueError:
            continue
        if 1.0 <= rating <= 5.0:
            return rating, int(match.end())

    glyph_match = _STAR_GLYPH_RE.search(text)
    if glyph_match:
        value = glyph_match.group(0)
        filled = value.count("★") + value.count("⭐")
        if 1 <= filled <= 5:
            return float(filled), int(glyph_match.end())

    return None, -1


def _extract_last_rating(line: str) -> float | None:
    text = str(line or "")
    candidates: list[tuple[int, float]] = []

    for pattern in _STAR_PATTERNS:
        for match in pattern.finditer(text):
            raw = str(match.group(1) or "").replace(",", ".")
            try:
                rating = float(raw)
            except ValueError:
                continue
            if 1.0 <= rating <= 5.0:
                candidates.append((int(match.end()), rating))

    for match in _STAR_GLYPH_RE.finditer(text):
        value = match.group(0)
        filled = value.count("★") + value.count("⭐")
        if 1 <= filled <= 5:
            candidates.append((int(match.end()), float(filled)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def classify_review_page(text: str) -> str | None:
    normalized = _clean_line(str(text or ""))
    if not normalized:
        return "empty_content"

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return "blocked_page"

    return None


def _is_noise_line(raw: str, cleaned: str) -> bool:
    lower = cleaned.lower()
    has_rating = _extract_rating(cleaned)[0] is not None
    return (
        not cleaned
        or "global ratings" in lower
        or "with reviews" in lower
        or lower.startswith("top reviews")
        or lower.startswith("sort by")
        or lower.startswith("filter by")
        or lower.startswith("search reviews")
        or ("customer reviews" in lower and not has_rating)
        or ("/customer-reviews/" not in raw and "out of 5 stars" in lower and len(cleaned) < 14)
    )


def parse_review_entries(text: str) -> list[dict[str, Any]]:
    raw_lines = str(text or "").splitlines()
    cleaned_lines = [_clean_line(line) for line in raw_lines]

    entries: list[dict[str, Any]] = []
    idx = 0
    while idx < len(cleaned_lines):
        raw_line = raw_lines[idx]
        line = cleaned_lines[idx]
        if _is_noise_line(raw_line, line):
            idx += 1
            continue

        rating, rating_end = _extract_rating(line)
        if rating is None:
            idx += 1
            continue

        title = line[rating_end:].strip(" -:|.")
        text_parts: list[str] = [title] if title else []

        next_idx = idx + 1
        while next_idx < len(cleaned_lines):
            next_raw = raw_lines[next_idx]
            next_line = cleaned_lines[next_idx]
            if _is_noise_line(next_raw, next_line):
                if text_parts:
                    break
                next_idx += 1
                continue
            if _extract_rating(next_line)[0] is not None:
                break
            text_parts.append(next_line)
            # Keep parser bounded when upstream returns long markdown pages.
            if sum(len(part) for part in text_parts) > 900:
                break
            next_idx += 1

        full_text = " ".join(part for part in text_parts if part).strip()
        if full_text:
            entries.append(
                {
                    "rating": rating,
                    "title": title,
                    "text": full_text,
                }
            )
        idx = max(next_idx, idx + 1)

    return entries


def parse_review_entries_from_product_html(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """
    Parse embedded review snippets from product detail HTML.
    This is a fallback when dedicated review pages are blocked.
    """
    html_text = str(text or "")
    if not html_text:
        return []

    entries: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    body_pattern = re.compile(
        r'data-hook="review-body"[^>]*>(.*?)</(?:span|div)>',
        re.IGNORECASE | re.DOTALL,
    )
    title_pattern = re.compile(
        r'data-hook="review-title"[^>]*>(.*?)</(?:a|span)>',
        re.IGNORECASE | re.DOTALL,
    )
    rating_pattern = re.compile(
        r'data-hook="(?:review-star-rating|cmps-review-star-rating)"[^>]*>(.*?)</(?:i|span)>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in body_pattern.finditer(html_text):
        body_raw = match.group(1)
        body = _clean_line(body_raw)
        if not body:
            continue

        window_start = max(0, match.start() - 1600)
        window_end = min(len(html_text), match.end() + 400)
        window = html_text[window_start:window_end]
        local_before = html_text[max(0, match.start() - 700):match.start()]

        title = ""
        title_match = title_pattern.search(window)
        if title_match:
            title = _clean_line(title_match.group(1))

        rating = None
        rating_matches = list(rating_pattern.finditer(local_before))
        if rating_matches:
            rating_text = _clean_line(rating_matches[-1].group(1))
            rating = _extract_rating(rating_text)[0]
        if rating is None:
            rating = _extract_last_rating(_clean_line(local_before))
        if rating is None:
            rating = _extract_last_rating(_clean_line(window))

        full_text = " ".join(part for part in [title, body] if part).strip()
        if not full_text:
            continue
        normalized = full_text.lower()
        if normalized in seen_texts:
            continue
        seen_texts.add(normalized)

        entries.append(
            {
                "rating": rating,
                "title": title,
                "text": full_text,
            }
        )
        if len(entries) >= max(1, int(limit)):
            break

    return entries


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(str(text or "").lower()):
        token = match.group(0)
        if token in _STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _counter_to_topics(counter: Counter[str], *, top_n: int, min_mentions: int) -> list[dict[str, Any]]:
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    topics: list[dict[str, Any]] = []
    for token, mentions in ranked:
        if mentions < min_mentions:
            continue
        topics.append({"topic": token, "mentions": int(mentions), "score": None})
        if len(topics) >= max(1, top_n):
            break
    return topics


def _rating_bucket(rating: float | None) -> str | None:
    if rating is None:
        return None
    bucket = int(math.floor(float(rating) + 0.5))
    if bucket < 1:
        bucket = 1
    if bucket > 5:
        bucket = 5
    return str(bucket)


def _clip_snippet(text: str, limit: int = 160) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(20, limit - 1)].rstrip() + "…"


def build_review_topic_summary(
    entries: list[dict[str, Any]],
    *,
    top_n: int = 8,
    min_mentions: int = 2,
) -> dict[str, Any]:
    positive = Counter()
    negative = Counter()
    sample_reviews = 0
    rating_distribution = {str(idx): 0 for idx in range(1, 6)}
    rating_sum = 0.0
    rated_count = 0
    sentiment = {"positive": 0, "negative": 0, "neutral": 0}
    positive_snippets: list[str] = []
    negative_snippets: list[str] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        rating_raw = entry.get("rating")
        try:
            rating = float(rating_raw) if rating_raw is not None else None
        except (TypeError, ValueError):
            rating = None

        text = str(entry.get("text") or entry.get("title") or "").strip()
        tokens = _tokenize(text)
        if not tokens:
            continue

        sample_reviews += 1
        bucket = _rating_bucket(rating)
        if bucket:
            rating_distribution[bucket] += 1
            rating_sum += float(rating or 0.0)
            rated_count += 1

        if rating is not None and rating >= 4.0:
            positive.update(tokens)
            sentiment["positive"] += 1
            snippet = _clip_snippet(text)
            if snippet and snippet not in positive_snippets and len(positive_snippets) < 3:
                positive_snippets.append(snippet)
        elif rating is not None and rating <= 2.0:
            negative.update(tokens)
            sentiment["negative"] += 1
            snippet = _clip_snippet(text)
            if snippet and snippet not in negative_snippets and len(negative_snippets) < 3:
                negative_snippets.append(snippet)
        else:
            sentiment["neutral"] += 1

    avg_rating = round(rating_sum / rated_count, 2) if rated_count > 0 else None

    return {
        "sample_reviews": sample_reviews,
        "total_reviews": sample_reviews,
        "avg_rating": avg_rating,
        "rating_distribution": rating_distribution,
        "sentiment": sentiment,
        "positive_topics": _counter_to_topics(positive, top_n=top_n, min_mentions=min_mentions),
        "negative_topics": _counter_to_topics(negative, top_n=top_n, min_mentions=min_mentions),
        "positive_snippets": positive_snippets,
        "negative_snippets": negative_snippets,
    }
