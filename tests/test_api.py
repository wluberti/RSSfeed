"""Integration tests for the Flask API endpoints."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from app import app
from database import Database


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <link>https://example.com</link>
        <description>Test</description>
        <item>
            <title>Test Article</title>
            <link>https://example.com/1</link>
            <description>Description</description>
            <guid>https://example.com/1</guid>
            <pubDate>Mon, 10 Feb 2025 08:00:00 +0100</pubDate>
        </item>
    </channel>
</rss>"""


@pytest.fixture
def client():
    """Create a Flask test client with temporary database.

    Returns:
        Flask test client.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        # Monkey-patch the module-level db
        import app as app_module
        app_module.db = Database(db_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client


class TestFeedEndpoints:
    """Tests for feed API endpoints."""

    @patch("app.fetch_feed")
    def test_add_feed(self, mock_fetch: MagicMock, client) -> None:
        """POST /api/feeds adds a new feed."""
        mock_fetch.return_value = {
            "meta": {"title": "Test Feed", "description": "Test", "site_url": "https://example.com", "image_url": ""},
            "articles": [{"title": "Art", "link": "https://a.com/1", "guid": "g1", "description": "", "author": "", "category": "", "pub_date": ""}],
        }
        resp = client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["feed"]["title"] == "Test Feed"
        assert data["articles_added"] == 1

    def test_add_feed_no_url(self, client) -> None:
        """POST /api/feeds without URL returns 400."""
        resp = client.post("/api/feeds", json={})
        assert resp.status_code == 400

    @patch("app.fetch_feed")
    def test_add_feed_invalid_url(self, mock_fetch: MagicMock, client) -> None:
        """POST /api/feeds with invalid feed URL returns 400."""
        mock_fetch.return_value = None
        resp = client.post("/api/feeds", json={"url": "https://example.com/not-a-feed"})
        assert resp.status_code == 400

    def test_get_feeds_empty(self, client) -> None:
        """GET /api/feeds returns empty list initially."""
        resp = client.get("/api/feeds")
        assert resp.status_code == 200
        assert resp.get_json() == []

    @patch("app.fetch_feed")
    def test_get_feeds(self, mock_fetch: MagicMock, client) -> None:
        """GET /api/feeds returns stored feeds."""
        mock_fetch.return_value = {
            "meta": {"title": "Test", "description": "", "site_url": "", "image_url": ""},
            "articles": [],
        }
        client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})
        resp = client.get("/api/feeds")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Test"

    @patch("app.fetch_feed")
    def test_delete_feed(self, mock_fetch: MagicMock, client) -> None:
        """DELETE /api/feeds/<id> removes the feed."""
        mock_fetch.return_value = {
            "meta": {"title": "Test", "description": "", "site_url": "", "image_url": ""},
            "articles": [],
        }
        resp = client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})
        feed_id = resp.get_json()["feed"]["id"]

        resp = client.delete(f"/api/feeds/{feed_id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        resp = client.get("/api/feeds")
        assert resp.get_json() == []

    def test_delete_feed_not_found(self, client) -> None:
        """DELETE /api/feeds/<id> returns 404 for non-existent."""
        resp = client.delete("/api/feeds/999")
        assert resp.status_code == 404


class TestArticleEndpoints:
    """Tests for article API endpoints."""

    @patch("app.fetch_feed")
    def test_get_articles(self, mock_fetch: MagicMock, client) -> None:
        """GET /api/articles returns articles."""
        mock_fetch.return_value = {
            "meta": {"title": "Test", "description": "", "site_url": "", "image_url": ""},
            "articles": [
                {"title": "Art 1", "link": "https://a.com/1", "guid": "g1", "description": "D1", "author": "A1", "category": "C1", "pub_date": "2025-01-01"},
            ],
        }
        client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})

        resp = client.get("/api/articles")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Art 1"
        assert data[0]["feed_title"] == "Test"

    @patch("app.fetch_feed")
    def test_get_articles_with_search(self, mock_fetch: MagicMock, client) -> None:
        """GET /api/articles?q=... filters articles."""
        mock_fetch.return_value = {
            "meta": {"title": "Test", "description": "", "site_url": "", "image_url": ""},
            "articles": [
                {"title": "Python Guide", "guid": "1", "description": "", "author": "", "category": "", "pub_date": "", "link": ""},
                {"title": "JS Guide", "guid": "2", "description": "", "author": "", "category": "", "pub_date": "", "link": ""},
            ],
        }
        client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})

        resp = client.get("/api/articles?q=python")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Python Guide"


class TestWebSearch:
    """Tests for web search endpoint."""

    def test_search_no_query(self, client) -> None:
        """GET /api/search/web without query returns 400."""
        resp = client.get("/api/search/web")
        assert resp.status_code == 400

    @patch("app.search_feeds")
    def test_search_returns_results(self, mock_search: MagicMock, client) -> None:
        """GET /api/search/web returns search results."""
        mock_search.return_value = [
            {
                "site_url": "https://example.com",
                "feed_url": "https://example.com/feed.xml",
                "title": "Example Feed",
                "description": "A test feed",
            },
        ]
        resp = client.get("/api/search/web?q=example")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Example Feed"
        assert data[0]["feed_url"] == "https://example.com/feed.xml"
        assert data[0]["site_url"] == "https://example.com"
        assert data[0]["description"] == "A test feed"
