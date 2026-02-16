"""RSS feed fetching and parsing service.

Uses feedparser to parse RSS/Atom feeds and extract articles.
"""

import feedparser
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


# Timeout for HTTP requests in seconds
REQUEST_TIMEOUT = 15

# User agent for feed fetching
USER_AGENT = "RSSFeedReader/1.0 (+https://github.com/rssfeedreader)"


def fetch_feed(url: str) -> Optional[dict]:
    """Fetch and parse an RSS/Atom feed from a URL.

    Parameters:
        url: The feed URL to fetch.

    Returns:
        Dict with 'meta' (feed metadata) and 'articles' (list of article dicts),
        or None if the feed cannot be parsed.
    """
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    feed = feedparser.parse(response.content)

    if not feed.feed or feed.bozo and not feed.entries:
        return None

    meta = _extract_meta(feed.feed, url)
    articles = [_extract_article(entry) for entry in feed.entries]

    return {"meta": meta, "articles": articles}


def _extract_meta(feed_data: feedparser.FeedParserDict, url: str) -> dict:
    """Extract feed metadata from parsed feed.

    Parameters:
        feed_data: Parsed feed metadata from feedparser.
        url: Original feed URL.

    Returns:
        Dict with feed metadata fields.
    """
    image_url = ""
    if hasattr(feed_data, "image") and feed_data.image:
        image_url = getattr(feed_data.image, "href", "") or getattr(feed_data.image, "url", "")

    return {
        "url": url,
        "title": getattr(feed_data, "title", "") or url,
        "description": getattr(feed_data, "subtitle", "") or getattr(feed_data, "description", ""),
        "site_url": getattr(feed_data, "link", ""),
        "image_url": image_url,
    }


def _extract_article(entry: feedparser.FeedParserDict) -> dict:
    """Extract article data from a feed entry.

    Parameters:
        entry: A single feed entry from feedparser.

    Returns:
        Dict with article fields.
    """
    pub_date = ""
    if hasattr(entry, "published") and entry.published:
        pub_date = _parse_date(entry.published)
    elif hasattr(entry, "updated") and entry.updated:
        pub_date = _parse_date(entry.updated)

    category = ""
    if hasattr(entry, "tags") and entry.tags:
        category = entry.tags[0].get("term", "") if entry.tags else ""

    description = getattr(entry, "summary", "") or ""
    if hasattr(entry, "content") and entry.content:
        description = entry.content[0].get("value", description)

    return {
        "title": getattr(entry, "title", ""),
        "link": getattr(entry, "link", ""),
        "description": description,
        "author": getattr(entry, "author", ""),
        "category": category,
        "pub_date": pub_date,
        "guid": getattr(entry, "id", "") or getattr(entry, "link", ""),
    }


def _parse_date(date_str: str) -> str:
    """Parse various date formats to ISO 8601.

    Parameters:
        date_str: Date string in RFC 2822 or other common formats.

    Returns:
        ISO 8601 date string, or empty string on failure.
    """
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass

    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue

    return date_str


def validate_feed_url(url: str) -> bool:
    """Check if a URL points to a valid RSS/Atom feed.

    Parameters:
        url: URL to validate.

    Returns:
        True if the URL returns a parseable feed.
    """
    result = fetch_feed(url)
    return result is not None and len(result.get("articles", [])) > 0
