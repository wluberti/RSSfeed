# FeedFlow - RSS Feed Reader

A modern, fast, and clean RSS/Atom feed reader built with Python (Flask) and vanilla JavaScript.

![Screenshot](screenshot.png)

## Features

-   **Clean Interface**: Minimalist design with light and dark mode support.
-   **Fast**: Backend processing with concurrent feed fetching and efficient caching.
-   **Search**: Discover new feeds by searching the web or entering URLs directly.
    -   Advanced filters: Filter search results by site name or feed URL.
-   **Privacy Focused**: No tracking, self-hosted.
-   **Dockerized**: Easy to deploy with Docker Compose.

## Installation

### Prerequisites

-   Docker
-   Docker Compose

### Quick Start

1.  Clone the repository:
    ```bash
    git clone https://github.com/yourusername/feedflow.git
    cd feedflow
    ```

2.  Create a `.env` file (optional, defaults provided):
    ```bash
    cp .env.example .env
    ```

3.  Start the application:
    ```bash
    docker compose up -d
    ```

4.  Open your browser and navigate to `http://localhost:5050`.

## Configuration

The application can be configured via environment variables in the `.env` file or `docker-compose.yml`.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `FLASK_PORT` | Port to run the application on | `5050` |
| `DATABASE_PATH` | Path to SQLite database | `data/feeds.db` |
| `FLASK_ENV` | Environment (development/production) | `production` |

## Development

To run locally without Docker:

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Run the application:
    ```bash
    python app.py
    ```

## License

MIT License. See [LICENSE](LICENSE) for details.
