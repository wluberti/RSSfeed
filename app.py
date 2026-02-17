"""Flask web application for RSS Feed Reader.

Entry point that serves the API and static frontend.
"""

import os
import csv
import io
from typing import Tuple, Union, Any, Dict

from flask import Flask, jsonify, request, send_from_directory, Response
from dotenv import load_dotenv

from database import Database
from feed_service import fetch_feed
from web_search import search_feeds

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")

# Initialize database
# Note: In production with gunicorn workers, this executes per worker process,
# ensuring thread safety for SQLite.
db = Database(os.getenv("DATABASE_PATH", "data/feeds.db"))


# --- Static file serving ---

@app.route("/")
def index() -> Response:
    """Serve the main application page.

    Returns:
        The index.html file.
    """
    return send_from_directory("static", "index.html")


# --- Feed API ---

@app.route("/api/feeds", methods=["GET"])
def get_feeds() -> Response:
    """Get all stored feeds.

    Returns:
        JSON list of feed objects.
    """
    feeds = db.get_feeds()
    return jsonify(feeds)


@app.route("/api/feeds", methods=["POST"])
def add_feed() -> Tuple[Response, int]:
    """Add a new RSS feed by URL.

    Expects JSON body: {"url": "https://example.com/feed.xml"}

    Returns:
        Tuple containing JSON response (feed data or error) and HTTP status code.
    """
    data: Union[Dict[str, Any], None] = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()

    # Fetch and parse the feed
    result = fetch_feed(url)
    if not result:
        return jsonify({"error": "Could not fetch or parse the feed URL"}), 400

    meta = result["meta"]

    try:
        feed = db.add_feed(
            url=url,
            title=meta.get("title", ""),
            description=meta.get("description", ""),
            site_url=meta.get("site_url", ""),
            image_url=meta.get("image_url", ""),
        )
        if not feed:
            return jsonify({"error": "Failed to save feed"}), 500
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": "Feed already exists"}), 409
        return jsonify({"error": str(e)}), 500

    # Store articles
    article_count = db.upsert_articles(feed["id"], result["articles"])
    # Reload feed to get updated counts if necessary, though we just added it.
    # The upsert might have updated last_fetched.
    updated_feed = db.get_feed(feed["id"])

    return jsonify({"feed": updated_feed, "articles_added": article_count}), 201


@app.route("/api/feeds/<int:feed_id>", methods=["DELETE"])
def delete_feed(feed_id: int) -> Tuple[Response, int]:
    """Remove a feed and all its articles.

    Args:
        feed_id: ID of the feed to remove.

    Returns:
        JSON success or 404 error with HTTP status code.
    """
    if db.remove_feed(feed_id):
        return jsonify({"success": True}), 200
    return jsonify({"error": "Feed not found"}), 404


@app.route("/api/feeds/<int:feed_id>/refresh", methods=["POST"])
def refresh_feed(feed_id: int) -> Tuple[Response, int]:
    """Refresh a single feed's articles.

    Args:
        feed_id: ID of the feed to refresh.

    Returns:
        JSON with refresh results and HTTP status code.
    """
    feed = db.get_feed(feed_id)
    if not feed:
        return jsonify({"error": "Feed not found"}), 404

    result = fetch_feed(feed["url"])
    if not result:
        return jsonify({"error": "Could not fetch feed"}), 502

    count = db.upsert_articles(feed_id, result["articles"])
    return jsonify({"success": True, "articles_updated": count}), 200


@app.route("/api/feeds/refresh", methods=["POST"])
def refresh_all_feeds() -> Response:
    """Refresh all stored feeds.

    Returns:
        JSON with per-feed refresh results.
    """
    feeds = db.get_feeds()
    results = []
    for feed in feeds:
        result = fetch_feed(feed["url"])
        if result:
            count = db.upsert_articles(feed["id"], result["articles"])
            results.append({
                "feed_id": feed["id"],
                "title": feed["title"],
                "articles_updated": count
            })
        else:
            results.append({
                "feed_id": feed["id"],
                "title": feed["title"],
                "error": "Failed to fetch"
            })
    return jsonify({"results": results})


# --- Articles API ---

@app.route("/api/articles", methods=["GET"])
def get_articles() -> Response:
    """Get articles with optional filtering and sorting.

    Query parameters:
        feed_id: Filter by feed ID.
        sort: Sort by 'date', 'title', or 'feed'.
        order: 'asc' or 'desc'.
        q: Search query string.
        group: Group filter (e.g., 'youtube').

    Returns:
        JSON list of article objects.
    """
    feed_id_raw = request.args.get("feed_id")
    feed_id = int(feed_id_raw) if feed_id_raw else None

    sort = request.args.get("sort", "date")
    order = request.args.get("order", "desc")
    query = request.args.get("q")
    group = request.args.get("group")

    articles = db.get_articles(
        feed_id=feed_id, sort=sort, order=order, query=query, group=group
    )
    return jsonify(articles)


# --- Web Search API ---

@app.route("/api/search/web", methods=["GET"])
def search_web() -> Tuple[Response, int]:
    """Search the web for RSS feeds.

    Query parameters:
        q: Search query.
        site: Optional site filter.
        feed: Optional feed type filter.

    Returns:
        JSON list of search result objects or error.
    """
    query = request.args.get("q", "").strip()
    site_filter = request.args.get("site", "").strip()
    feed_filter = request.args.get("feed", "").strip()

    if not query:
        return jsonify({"error": "Search query is required"}), 400

    results = search_feeds(query, site_filter=site_filter, feed_filter=feed_filter)
    return jsonify(results), 200


@app.route("/api/feeds/import", methods=["POST"])
def import_feeds() -> Tuple[Response, int]:
    """Import feeds from OPML or CSV.

    Currently supports Google Takeout YouTube subscription CSVs.
    Columns expected: 'Channel ID', 'Channel URL', 'Channel title'

    Returns:
        JSON with import summary (count, errors).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "" or not file.filename:
        return jsonify({"error": "No selected file"}), 400

    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Only .csv files are supported currently"}), 400

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []

        # Verify headers for YouTube Takeout CSV
        # Ideally we should validate more strictly, but simplistic check is okay for now
        # We need at least Channel ID to construct the URL
        if "Channel ID" not in fieldnames:
             pass # Could handle error, but let's try reading anyway

        success_count = 0
        errors = []

        for row in reader:
            channel_id = row.get("Channel ID")
            title = row.get("Channel Title") or row.get("Channel title")

            if not channel_id:
                continue

            # Construct YouTube RSS URL
            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

            # Fetch feed to verify and get metadata
            # This is slower but ensures valid data
            result = fetch_feed(feed_url)
            if not result:
                errors.append(f"Failed to fetch feed for {title or channel_id}")
                continue

            meta = result["meta"]
            try:
                feed = db.add_feed(
                    url=feed_url,
                    title=meta.get("title", title or ""),
                    description=meta.get("description", ""),
                    site_url=meta.get("site_url", f"https://www.youtube.com/channel/{channel_id}"),
                    image_url=meta.get("image_url", ""),
                )
                if feed:
                    db.upsert_articles(feed["id"], result["articles"])
                    success_count += 1
            except Exception as e:
                if "UNIQUE constraint" not in str(e):
                    errors.append(f"Error adding {title}: {str(e)}")

        return jsonify({
            "success": True,
            "count": success_count,
            "errors": errors
        }), 200

    except Exception as e:
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"Starting RSS Feed Reader on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
