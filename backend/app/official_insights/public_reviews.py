from __future__ import annotations

from collections import Counter
import math
import html
import re
from typing import Any

_STAR_RE = re.compile(r"([1-5](?:\.\d)?)\s*out of\s*5\s*stars", re.IGNORECASE)
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


def _is_noise_line(raw: str, cleaned: str) -> bool:
    lower = cleaned.lower()
    return (
        not cleaned
        or "global ratings" in lower
        or "with reviews" in lower
        or lower.startswith("top reviews")
        or lower.startswith("sort by")
        or lower.startswith("filter by")
        or lower.startswith("search reviews")
        or ("customer reviews" in lower and "out of 5 stars" not in lower)
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

        star_match = _STAR_RE.search(line)
        if not star_match:
            idx += 1
            continue

        try:
            rating = float(star_match.group(1))
        except ValueError:
            idx += 1
            continue

        title = line[star_match.end() :].strip(" -:|.")
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
            if _STAR_RE.search(next_line):
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
