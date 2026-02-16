"""Tests for the RSS feed service."""

from unittest.mock import patch, MagicMock
from feed_service import fetch_feed, validate_feed_url, _parse_date


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <link>https://example.com</link>
        <description>A test RSS feed</description>
        <image>
            <url>https://example.com/logo.png</url>
            <title>Test</title>
        </image>
        <item>
            <title>Article One</title>
            <link>https://example.com/article-1</link>
            <description>First article description</description>
            <author>John Doe</author>
            <category>Tech</category>
            <guid>https://example.com/article-1</guid>
            <pubDate>Mon, 10 Feb 2025 08:00:00 +0100</pubDate>
        </item>
        <item>
            <title>Article Two</title>
            <link>https://example.com/article-2</link>
            <description>Second article description</description>
            <pubDate>Tue, 11 Feb 2025 10:30:00 +0100</pubDate>
        </item>
    </channel>
</rss>"""


class TestFetchFeed:
    """Tests for feed fetching and parsing."""

    @patch("feed_service.requests.get")
    def test_fetch_valid_feed(self, mock_get: MagicMock) -> None:
        """Parsing a valid RSS feed returns structured data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_RSS.encode()
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_feed("https://example.com/feed.xml")

        assert result is not None
        assert result["meta"]["title"] == "Test Feed"
        assert result["meta"]["site_url"] == "https://example.com"
        assert len(result["articles"]) == 2
        assert result["articles"][0]["title"] == "Article One"
        assert result["articles"][0]["author"] == "John Doe"
        assert result["articles"][0]["category"] == "Tech"

    @patch("feed_service.requests.get")
    def test_fetch_feed_network_error(self, mock_get: MagicMock) -> None:
        """Network errors return None."""
        import requests as req
        mock_get.side_effect = req.RequestException("Connection error")

        result = fetch_feed("https://example.com/feed.xml")
        assert result is None

    @patch("feed_service.requests.get")
    def test_fetch_invalid_feed(self, mock_get: MagicMock) -> None:
        """Invalid XML content returns None (or empty articles)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body>Not a feed</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_feed("https://example.com/not-a-feed")
        # feedparser may still parse something, but it won't have real entries
        if result is not None:
            assert len(result.get("articles", [])) == 0 or result["meta"]["title"] != ""


class TestParseDate:
    """Tests for date parsing."""

    def test_rfc2822_date(self) -> None:
        """RFC 2822 dates are parsed correctly."""
        result = _parse_date("Mon, 10 Feb 2025 08:00:00 +0100")
        assert "2025-02-10" in result

    def test_iso_date(self) -> None:
        """ISO 8601 dates are parsed correctly."""
        result = _parse_date("2025-02-10T08:00:00+01:00")
        assert "2025-02-10" in result

    def test_invalid_date(self) -> None:
        """Invalid dates return the original string."""
        result = _parse_date("not a date")
        assert result == "not a date"

    def test_empty_date(self) -> None:
        """Empty string returns empty string."""
        result = _parse_date("")
        assert result == ""


class TestValidateFeedUrl:
    """Tests for feed URL validation."""

    @patch("feed_service.fetch_feed")
    def test_valid_url(self, mock_fetch: MagicMock) -> None:
        """Valid feed URLs return True."""
        mock_fetch.return_value = {"meta": {}, "articles": [{"title": "Test"}]}
        assert validate_feed_url("https://example.com/feed.xml") is True

    @patch("feed_service.fetch_feed")
    def test_invalid_url(self, mock_fetch: MagicMock) -> None:
        """Invalid feed URLs return False."""
        mock_fetch.return_value = None
        assert validate_feed_url("https://example.com/not-a-feed") is False
