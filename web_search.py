"""Web search for discovering RSS feeds.

Searches for RSS feeds using multiple strategies:
1. Common feed URL patterns on a domain
2. HTML page feed link discovery
3. Web search via DuckDuckGo (no API key required)
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote_plus
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed


REQUEST_TIMEOUT = 3
# Standard browser user agent to avoid blocking
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Common feed paths to probe on websites
COMMON_FEED_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/feeds/posts/default",
    "/index.xml",
    "/blog/feed",
    "/blog/rss",
    "/?feed=rss2",
]


def search_feeds(query: str) -> list[dict]:
    """Search the web for RSS feeds matching a query.

    Combines results from DuckDuckGo search and direct URL probing.
    Each result includes site_url (website) and feed_url (RSS feed).

    Parameters:
        query: Search query string.

    Returns:
        List of dicts with keys: site_url, feed_url, title, description.
    """
    results: list[dict] = []
    seen_sites: set[str] = set()
    futures = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        # Strategy 1: If query looks like a URL, try direct discovery
        if _looks_like_url(query):
            url = query if query.startswith("http") else f"https://{query}"
            futures.append(executor.submit(_process_direct_url, url))

        # Strategy 2: Search DuckDuckGo
        search_results = _search_duckduckgo(query)
        for r in search_results:
            site_url = r["url"]
            if site_url in seen_sites:
                continue
            seen_sites.add(site_url)
            futures.append(executor.submit(_process_search_result, r))

        for future in as_completed(futures):
            try:
                res_list = future.result()
                if res_list:
                    results.extend(res_list)
            except Exception:
                pass

    return results[:20]


def _process_direct_url(url: str) -> list[dict]:
    """Helper to process a direct URL discovery."""
    results = []
    direct_results = _discover_feeds_from_url(url)
    for r in direct_results:
        results.append({
            "site_url": url,
            "feed_url": r["url"],
            "title": r["title"],
            "description": r["description"],
        })
    return results


def _process_search_result(result: dict) -> list[dict]:
    """Helper to process a search result."""
    site_url = result["url"]
    feeds = _discover_feeds_from_url(site_url)
    feed_url = feeds[0]["url"] if feeds else None
    feed_desc = result["description"] or (feeds[0]["description"] if feeds else "")

    return [{
        "site_url": site_url,
        "feed_url": feed_url,
        "title": result["title"],
        "description": feed_desc,
    }]


def _looks_like_url(text: str) -> bool:
    """Check if text looks like a URL or domain name.

    Parameters:
        text: Text to check.

    Returns:
        True if text resembles a URL.
    """
    return "." in text and " " not in text.strip()


def _discover_feeds_from_url(url: str) -> list[dict]:
    """Discover RSS feeds from a website URL.

    Checks HTML <link> tags and common feed URL patterns.

    Parameters:
        url: Website URL to check for feeds.

    Returns:
        List of discovered feed dicts.
    """
    results = []

    # Try to find feed links in HTML
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")

            # Check if the URL itself is a feed
            if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    title = getattr(feed.feed, "title", url)
                    results.append({
                        "url": url,
                        "title": title,
                        "description": getattr(feed.feed, "subtitle", "") or getattr(feed.feed, "description", ""),
                    })
                    return results

            # Parse HTML for <link> feed references
            soup = BeautifulSoup(resp.text, "lxml")
            feed_links = soup.find_all(
                "link",
                type=lambda t: t and ("rss" in t or "atom" in t or "xml" in t),
            )
            for link in feed_links:
                href = link.get("href", "")
                if href:
                    feed_url = urljoin(url, href)
                    title = link.get("title", "") or feed_url
                    results.append({"url": feed_url, "title": title, "description": ""})

    except Exception:
        pass

    # Optimization: If we found feeds in HTML, return immediately and skip guessing paths
    if results:
        return results

    # Improved Step: Parallelize common path probing
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    with ThreadPoolExecutor(max_workers=5) as executor:
        path_futures = []
        for path in COMMON_FEED_PATHS:
            feed_url = base_url + path
            # optimization: feed_url check against existing results moved inside task or check after
            if feed_url in {r["url"] for r in results}:
                 continue
            path_futures.append(executor.submit(_probe_feed_url, feed_url))

        for future in as_completed(path_futures):
            try:
                res = future.result()
                if res and res["url"] not in {r["url"] for r in results}:
                    results.append(res)
            except Exception:
                pass

    return results


def _probe_feed_url(feed_url: str) -> dict | None:
    """Helper to probe a single feed URL."""
    try:
        resp = requests.get(
            feed_url,
            timeout=5,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct or "atom" in ct:
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    title = getattr(feed.feed, "title", feed_url)
                    return {
                        "url": feed_url,
                        "title": title,
                        "description": getattr(feed.feed, "subtitle", "") or "",
                    }
    except requests.RequestException:
        pass
    return None


def _search_duckduckgo(query: str) -> list[dict]:
    """Search DuckDuckGo for RSS feed URLs.

    Parameters:
        query: Search query.

    Returns:
        List of dicts with url, title, description.
    """
    results = []
    search_query = f"{query} RSS feed"
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"

    try:
        resp = requests.get(
            search_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        result_items = soup.select(".result")

        for item in result_items[:10]:
            link = item.select_one(".result__a")
            if not link:
                continue

            href = link.get("href", "")
            title = link.get_text(strip=True)

            # Extract snippet description
            snippet_el = item.select_one(".result__snippet")
            description = snippet_el.get_text(strip=True) if snippet_el else ""

            # DuckDuckGo wraps URLs in redirects
            if "uddg=" in href:
                from urllib.parse import parse_qs
                params = parse_qs(urlparse(href).query)
                href = params.get("uddg", [href])[0]

            if href and href.startswith("http"):
                results.append({
                    "url": href,
                    "title": title,
                    "description": description,
                })

    except Exception:
        pass

    return results


REQUEST_TIMEOUT = 5
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Common feed paths to probe on websites
COMMON_FEED_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/feeds/posts/default",
    "/index.xml",
    "/blog/feed",
    "/blog/rss",
    "/?feed=rss2",
]


def search_feeds(query: str) -> list[dict]:
    """Search the web for RSS feeds matching a query.

    Combines results from DuckDuckGo search and direct URL probing.
    Each result includes site_url (website) and feed_url (RSS feed).

    Parameters:
        query: Search query string.

    Returns:
        List of dicts with keys: site_url, feed_url, title, description.
    """
    results: list[dict] = []
    seen_sites: set[str] = set()

    # Strategy 1: If query looks like a URL, try direct discovery
    if _looks_like_url(query):
        url = query if query.startswith("http") else f"https://{query}"
        direct_results = _discover_feeds_from_url(url)
        for r in direct_results:
            if r["url"] not in seen_sites:
                seen_sites.add(r["url"])
                results.append({
                    "site_url": url,
                    "feed_url": r["url"],
                    "title": r["title"],
                    "description": r["description"],
                })

    # Strategy 2: Search DuckDuckGo
    search_results = _search_duckduckgo(query)
    for r in search_results:
        site_url = r["url"]
        if site_url in seen_sites:
            continue
        seen_sites.add(site_url)

        # Probe website for actual RSS feed URL
        feeds = _discover_feeds_from_url(site_url)
        feed_url = feeds[0]["url"] if feeds else None
        feed_desc = r["description"] or (feeds[0]["description"] if feeds else "")

        results.append({
            "site_url": site_url,
            "feed_url": feed_url,
            "title": r["title"],
            "description": feed_desc,
        })

    return results[:20]


def _looks_like_url(text: str) -> bool:
    """Check if text looks like a URL or domain name.

    Parameters:
        text: Text to check.

    Returns:
        True if text resembles a URL.
    """
    return "." in text and " " not in text.strip()


def _discover_feeds_from_url(url: str) -> list[dict]:
    # ... (docstring)
    results = []

    # Try to find feed links in HTML
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")

            # Check if the URL itself is a feed
            if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    title = getattr(feed.feed, "title", url)
                    results.append({
                        "url": url,
                        "title": title,
                        "description": getattr(feed.feed, "subtitle", "") or getattr(feed.feed, "description", ""),
                    })
                    return results

            # Parse HTML for <link> feed references
            soup = BeautifulSoup(resp.text, "lxml")
            feed_links = soup.find_all(
                "link",
                type=lambda t: t and ("rss" in t or "atom" in t or "xml" in t),
            )
            for link in feed_links:
                href = link.get("href", "")
                if href:
                    feed_url = urljoin(url, href)
                    title = link.get("title", "") or feed_url
                    results.append({"url": feed_url, "title": title, "description": ""})

    except Exception:
        pass

    # Try common feed paths
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    for path in COMMON_FEED_PATHS:
        feed_url = base_url + path
        if feed_url in {r["url"] for r in results}:
            continue
        try:
            resp = requests.get(
                feed_url,
                timeout=5,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "xml" in ct or "rss" in ct or "atom" in ct:
                    feed = feedparser.parse(resp.content)
                    if feed.entries:
                        title = getattr(feed.feed, "title", feed_url)
                        results.append({
                            "url": feed_url,
                            "title": title,
                            "description": getattr(feed.feed, "subtitle", "") or "",
                        })
        except requests.RequestException:
            continue

    return results


def _search_duckduckgo(query: str) -> list[dict]:
    """Search DuckDuckGo for RSS feed URLs.

    Parameters:
        query: Search query.

    Returns:
        List of dicts with url, title, description.
    """
    results = []
    search_query = f"{query} RSS feed"
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"

    try:
        resp = requests.get(
            search_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        result_items = soup.select(".result")

        for item in result_items[:10]:
            link = item.select_one(".result__a")
            if not link:
                continue

            href = link.get("href", "")
            title = link.get_text(strip=True)

            # Extract snippet description
            snippet_el = item.select_one(".result__snippet")
            description = snippet_el.get_text(strip=True) if snippet_el else ""

            # DuckDuckGo wraps URLs in redirects
            if "uddg=" in href:
                from urllib.parse import parse_qs
                params = parse_qs(urlparse(href).query)
                href = params.get("uddg", [href])[0]

            if href and href.startswith("http"):
                results.append({
                    "url": href,
                    "title": title,
                    "description": description,
                })

    except Exception:
        pass

    return results
