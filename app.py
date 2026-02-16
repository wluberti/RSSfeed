"""Flask web application for RSS Feed Reader.

Entry point that serves the API and static frontend.
"""

import os
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

from database import Database
from feed_service import fetch_feed
from web_search import search_feeds

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")

db = Database(os.getenv("DATABASE_PATH", "data/feeds.db"))


# --- Static file serving ---

@app.route("/")
def index():
    """Serve the main application page.

    Returns:
        The index.html file.
    """
    return send_from_directory("static", "index.html")


# --- Feed API ---

@app.route("/api/feeds", methods=["GET"])
def get_feeds():
    """Get all stored feeds.

    Returns:
        JSON list of feed objects.
    """
    feeds = db.get_feeds()
    return jsonify(feeds)


@app.route("/api/feeds", methods=["POST"])
def add_feed():
    """Add a new RSS feed by URL.

    Expects JSON body: {"url": "https://example.com/feed.xml"}

    Returns:
        JSON with the new feed data and fetched articles, or error.
    """
    data = request.get_json()
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
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": "Feed already exists"}), 409
        return jsonify({"error": str(e)}), 500

    # Store articles
    article_count = db.upsert_articles(feed["id"], result["articles"])
    feed = db.get_feed(feed["id"])

    return jsonify({"feed": feed, "articles_added": article_count}), 201


@app.route("/api/feeds/<int:feed_id>", methods=["DELETE"])
def delete_feed(feed_id: int):
    """Remove a feed and all its articles.

    Parameters:
        feed_id: ID of the feed to remove.

    Returns:
        JSON success or 404 error.
    """
    if db.remove_feed(feed_id):
        return jsonify({"success": True})
    return jsonify({"error": "Feed not found"}), 404


@app.route("/api/feeds/<int:feed_id>/refresh", methods=["POST"])
def refresh_feed(feed_id: int):
    """Refresh a single feed's articles.

    Parameters:
        feed_id: ID of the feed to refresh.

    Returns:
        JSON with refresh results.
    """
    feed = db.get_feed(feed_id)
    if not feed:
        return jsonify({"error": "Feed not found"}), 404

    result = fetch_feed(feed["url"])
    if not result:
        return jsonify({"error": "Could not fetch feed"}), 502

    count = db.upsert_articles(feed_id, result["articles"])
    return jsonify({"success": True, "articles_updated": count})


@app.route("/api/feeds/refresh", methods=["POST"])
def refresh_all_feeds():
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
            results.append({"feed_id": feed["id"], "title": feed["title"], "articles_updated": count})
        else:
            results.append({"feed_id": feed["id"], "title": feed["title"], "error": "Failed to fetch"})
    return jsonify({"results": results})


# --- Articles API ---

@app.route("/api/articles", methods=["GET"])
def get_articles():
    """Get articles with optional filtering and sorting.

    Query parameters:
        feed_id: Filter by feed ID.
        sort: Sort by 'date', 'title', or 'feed'.
        order: 'asc' or 'desc'.
        q: Search query string.

    Returns:
        JSON list of article objects.
    """
    feed_id = request.args.get("feed_id", type=int)
    sort = request.args.get("sort", "date")
    order = request.args.get("order", "desc")
    query = request.args.get("q")

    articles = db.get_articles(feed_id=feed_id, sort=sort, order=order, query=query)
    return jsonify(articles)


# --- Web Search API ---

@app.route("/api/search/web", methods=["GET"])
def search_web():
    """Search the web for RSS feeds.

    Query parameters:
        q: Search query.

    Returns:
        JSON list of search result objects.
    """
    query = request.args.get("q", "").strip()
    site_filter = request.args.get("site", "").strip()
    feed_filter = request.args.get("feed", "").strip()

    if not query:
        return jsonify({"error": "Search query is required"}), 400

    results = search_feeds(query, site_filter=site_filter, feed_filter=feed_filter)
    return jsonify(results)


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"Starting RSS Feed Reader on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
