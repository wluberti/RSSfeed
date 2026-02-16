"""Tests for the SQLite database layer."""

import os
import tempfile
import pytest
from database import Database


@pytest.fixture
def db():
    """Create a temporary database for testing.

    Returns:
        Database instance with temporary storage.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield Database(db_path)


class TestFeeds:
    """Tests for feed CRUD operations."""

    def test_add_feed(self, db: Database) -> None:
        """Adding a feed returns correct data."""
        feed = db.add_feed(
            url="https://example.com/feed.xml",
            title="Example Feed",
            description="A test feed",
            site_url="https://example.com",
            image_url="https://example.com/logo.png",
        )
        assert feed["url"] == "https://example.com/feed.xml"
        assert feed["title"] == "Example Feed"
        assert feed["id"] is not None

    def test_add_duplicate_feed(self, db: Database) -> None:
        """Adding a duplicate feed URL raises an IntegrityError."""
        db.add_feed(url="https://example.com/feed.xml", title="Feed 1")
        with pytest.raises(Exception):
            db.add_feed(url="https://example.com/feed.xml", title="Feed 2")

    def test_get_feeds(self, db: Database) -> None:
        """get_feeds returns all stored feeds."""
        db.add_feed(url="https://a.com/feed", title="Feed A")
        db.add_feed(url="https://b.com/feed", title="Feed B")
        feeds = db.get_feeds()
        assert len(feeds) == 2
        titles = [f["title"] for f in feeds]
        assert "Feed A" in titles
        assert "Feed B" in titles

    def test_get_feed(self, db: Database) -> None:
        """get_feed returns a single feed by ID."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        result = db.get_feed(feed["id"])
        assert result["title"] == "Test"

    def test_get_feed_not_found(self, db: Database) -> None:
        """get_feed returns None for non-existent ID."""
        assert db.get_feed(999) is None

    def test_remove_feed(self, db: Database) -> None:
        """remove_feed deletes the feed and returns True."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        assert db.remove_feed(feed["id"]) is True
        assert db.get_feed(feed["id"]) is None

    def test_remove_feed_not_found(self, db: Database) -> None:
        """remove_feed returns False for non-existent ID."""
        assert db.remove_feed(999) is False

    def test_remove_feed_cascades_articles(self, db: Database) -> None:
        """Removing a feed also removes its articles."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        db.upsert_articles(feed["id"], [
            {"title": "Article 1", "link": "https://a.com/1", "guid": "1"},
        ])
        assert len(db.get_articles(feed_id=feed["id"])) == 1
        db.remove_feed(feed["id"])
        assert len(db.get_articles(feed_id=feed["id"])) == 0


class TestArticles:
    """Tests for article storage and retrieval."""

    def test_upsert_articles(self, db: Database) -> None:
        """upsert_articles inserts new articles."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        count = db.upsert_articles(feed["id"], [
            {"title": "Art 1", "link": "https://a.com/1", "guid": "g1", "description": "Desc", "author": "Auth", "category": "Cat", "pub_date": "2025-01-01"},
            {"title": "Art 2", "link": "https://a.com/2", "guid": "g2", "description": "", "author": "", "category": "", "pub_date": ""},
        ])
        assert count == 2
        articles = db.get_articles(feed_id=feed["id"])
        assert len(articles) == 2

    def test_upsert_articles_updates_existing(self, db: Database) -> None:
        """upsert_articles updates articles with same guid."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        db.upsert_articles(feed["id"], [
            {"title": "Original", "link": "https://a.com/1", "guid": "g1"},
        ])
        db.upsert_articles(feed["id"], [
            {"title": "Updated", "link": "https://a.com/1", "guid": "g1"},
        ])
        articles = db.get_articles(feed_id=feed["id"])
        assert len(articles) == 1
        assert articles[0]["title"] == "Updated"

    def test_get_articles_sorted_by_title(self, db: Database) -> None:
        """Articles can be sorted by title."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        db.upsert_articles(feed["id"], [
            {"title": "Banana", "guid": "1"},
            {"title": "Apple", "guid": "2"},
            {"title": "Cherry", "guid": "3"},
        ])
        articles = db.get_articles(sort="title", order="asc")
        assert articles[0]["title"] == "Apple"
        assert articles[2]["title"] == "Cherry"

    def test_search_articles(self, db: Database) -> None:
        """Articles can be searched by title and description."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="Test")
        db.upsert_articles(feed["id"], [
            {"title": "Python Tutorial", "description": "Learn Python", "guid": "1"},
            {"title": "JavaScript Guide", "description": "Learn JS", "guid": "2"},
        ])
        results = db.get_articles(query="python")
        assert len(results) == 1
        assert results[0]["title"] == "Python Tutorial"

    def test_get_articles_includes_feed_title(self, db: Database) -> None:
        """Articles include their parent feed title."""
        feed = db.add_feed(url="https://example.com/feed.xml", title="My Feed")
        db.upsert_articles(feed["id"], [
            {"title": "Art", "guid": "1"},
        ])
        articles = db.get_articles()
        assert articles[0]["feed_title"] == "My Feed"
