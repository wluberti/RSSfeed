"""SQLite database layer for RSS feed reader.

Manages feeds and articles storage with full CRUD operations.
"""

import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union


class Database:
    """SQLite database manager for feeds and articles."""

    def __init__(self, db_path: str = "data/feeds.db") -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new database connection with row factory.

        Returns:
            sqlite3.Connection configured with Row factory.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Initialize database schema if tables don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    site_url TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL,
                    last_fetched TEXT
                );

                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    pub_date TEXT NOT NULL DEFAULT '',
                    guid TEXT NOT NULL DEFAULT '',
                    thumbnail TEXT NOT NULL DEFAULT '',
                    read INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
                    UNIQUE(feed_id, guid)
                );

                CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
                CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date);
                CREATE INDEX IF NOT EXISTS idx_articles_guid ON articles(guid);
            """)
            # Migration: add thumbnail column to existing databases
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN thumbnail TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()
        finally:
            conn.close()

    def add_feed(
        self,
        url: str,
        title: str = "",
        description: str = "",
        site_url: str = "",
        image_url: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Add a new feed to the database.

        Args:
            url: Feed URL.
            title: Feed title.
            description: Feed description.
            site_url: Website URL.
            image_url: Feed image/logo URL.

        Returns:
            Dict with the newly created feed data, or None on failure.
        """
        conn = self._get_conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """INSERT INTO feeds (url, title, description, site_url, image_url, added_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (url, title, description, site_url, image_url, now),
            )
            conn.commit()
            return self.get_feed(cursor.lastrowid)
        finally:
            conn.close()

    def remove_feed(self, feed_id: int) -> bool:
        """Remove a feed and all its articles.

        Args:
            feed_id: ID of the feed to remove.

        Returns:
            True if feed was found and removed, False otherwise.
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_feeds(self) -> List[Dict[str, Any]]:
        """Get all stored feeds.

        Returns:
            List of feed dicts.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT *, (SELECT COUNT(*) FROM articles WHERE feed_id = feeds.id) as article_count FROM feeds ORDER BY title"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_feed(self, feed_id: int) -> Optional[Dict[str, Any]]:
        """Get a single feed by ID.

        Args:
            feed_id: ID of the feed.

        Returns:
            Feed dict or None if not found.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT *, (SELECT COUNT(*) FROM articles WHERE feed_id = feeds.id) as article_count FROM feeds WHERE id = ?",
                (feed_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def upsert_articles(self, feed_id: int, articles: List[Dict[str, Any]]) -> int:
        """Insert or update articles for a feed.

        Args:
            feed_id: ID of the parent feed.
            articles: List of article dicts with keys: title, link, description,
                      author, category, pub_date, guid, thumbnail.

        Returns:
            Number of articles inserted/updated.
        """
        conn = self._get_conn()
        try:
            count = 0
            for article in articles:
                guid = article.get("guid") or article.get("link") or article.get("title", "")
                try:
                    conn.execute(
                        """INSERT INTO articles
                           (feed_id, title, link, description, author, category, pub_date, guid, thumbnail)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(feed_id, guid) DO UPDATE SET
                             title=excluded.title,
                             link=excluded.link,
                             description=excluded.description,
                             author=excluded.author,
                             category=excluded.category,
                             pub_date=excluded.pub_date,
                             thumbnail=excluded.thumbnail""",
                        (
                            feed_id,
                            article.get("title", ""),
                            article.get("link", ""),
                            article.get("description", ""),
                            article.get("author", ""),
                            article.get("category", ""),
                            article.get("pub_date", ""),
                            guid,
                            article.get("thumbnail", ""),
                        ),
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    continue
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE feeds SET last_fetched = ? WHERE id = ?", (now, feed_id))
            conn.commit()
            return count
        finally:
            conn.close()

    def get_articles(
        self,
        feed_id: Optional[int] = None,
        sort: str = "date",
        order: str = "desc",
        query: Optional[str] = None,
        group: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get articles with optional filtering and sorting.

        Args:
            feed_id: Optional feed ID to filter by.
            sort: Sort field — 'date', 'title', or 'feed'.
            order: Sort order — 'asc' or 'desc'.
            query: Optional search query to filter articles.
            group: Optional group filter ('youtube').

        Returns:
            List of article dicts with feed title included.
        """
        sort_map = {
            "date": "a.pub_date",
            "title": "a.title",
            "feed": "f.title",
        }
        sort_col = sort_map.get(sort, "a.pub_date")
        order_dir = "ASC" if order.lower() == "asc" else "DESC"

        conditions = []
        params: List[Any] = []

        if feed_id is not None:
            conditions.append("a.feed_id = ?")
            params.append(feed_id)

        if group == "youtube":
            conditions.append("(f.url LIKE '%youtube.com%' OR f.site_url LIKE '%youtube.com%')")

        if query:
            conditions.append("(a.title LIKE ? OR a.description LIKE ? OR a.author LIKE ? OR a.category LIKE ?)")
            q = f"%{query}%"
            params.extend([q, q, q, q])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        conn = self._get_conn()
        try:
            # Need to join with feeds to filter by group if needed
            # The join is already there in the original query
            sql = f"""SELECT a.*, f.title as feed_title, f.image_url as feed_image
                    FROM articles a
                    JOIN feeds f ON a.feed_id = f.id
                    {where_clause}
                    ORDER BY {sort_col} {order_dir}
                    LIMIT 500"""

            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
