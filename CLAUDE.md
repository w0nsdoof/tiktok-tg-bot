# tiktok-tg-bot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-07-20

## Active Technologies
- Python 3.12 + python-telegram-bot 21.x (21.11.1), yt-dlp, pydantic-settings, structlog

## Project Structure

```text
src/bot/
├── handlers/
│   ├── common.py       # Shared process_request() helper (format routing)
│   ├── private.py      # Private chat handler
│   ├── group.py        # Group chat handler
│   ├── inline.py       # Inline mode handler
│   └── admin.py        # Access management
├── locales/
│   └── messages.py     # EN/RU message catalog
├── models/
│   ├── request.py      # Platform, OutputFormat, VideoRequest
│   └── video_info.py   # VideoInfo (parsed yt-dlp metadata)
└── services/
    ├── format_parser.py # Format keyword detection
    ├── downloader.py    # yt-dlp download (video, audio, slideshow)
    ├── url_parser.py    # URL extraction and platform detection
    ├── queue.py         # Async download queue
    ├── user_store.py    # Persistent whitelist (JSON)
    └── analytics.py     # Download events + video metadata into Postgres
tests/
├── unit/
│   ├── test_format_parser.py   # Keyword detection tests
│   ├── test_downloader.py      # Audio download tests
│   └── test_handler_routing.py # 6-branch routing matrix tests
└── integration/
```

## Commands

- Install deps: `uv sync`
- Run bot: `cd src && uv run python -m bot`
- Tests: `cd src && uv run pytest`
- Lint: `cd src && uv run ruff check .`

## Code Style

Python 3.12: Follow standard conventions

## Recent Changes
- 003-analytics-data-layer: download events + video metadata into shared Postgres (asyncpg, fire-and-forget)
- 002-output-format-selection: Added format keyword detection (audio/images), audio extraction via FFmpegExtractAudio, shared handler logic, 40 unit tests
- 001-video-download-bot: Initial bot with video/slideshow download, whitelist, inline mode

<!-- MANUAL ADDITIONS START -->

## Quick Start

See [README.md](README.md) for setup instructions and configuration options.

<!-- MANUAL ADDITIONS END -->
