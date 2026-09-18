# Quickstart: Video Download Bot

## Prerequisites

- Python 3.12+
- ffmpeg installed and on PATH (`sudo apt install ffmpeg` / `brew install ffmpeg`)
- [uv](https://docs.astral.sh/uv/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Telegram Bot token from [@BotFather](https://t.me/BotFather) (enable inline mode via BotFather)

## Setup

```bash
# Clone and enter project
git clone <repo-url> && cd tiktok-tg-bot

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your bot token and whitelist
```

## Environment Variables

```env
BOT_TOKEN=your-telegram-bot-token
ALLOWED_USER_IDS=123456789,987654321
MAX_DURATION=300
MAX_FILE_SIZE=50
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_DIR=/tmp/tg-bot-downloads
LOG_LEVEL=INFO
LOG_JSON=false
```

## Run

```bash
uv run python -m bot
```

## Test

```bash
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## How It Works

1. User sends a video link (TikTok, YouTube Shorts, Instagram Reel) to the bot
2. Bot extracts the URL, validates the platform, and checks the whitelist
3. Bot sends "Downloading..." feedback message
4. yt-dlp extracts metadata (duration check) then downloads the video
5. Bot sends the video as a native Telegram video message
6. Temporary file is cleaned up

## Project Structure

```
src/
└── bot/
    ├── __init__.py
    ├── __main__.py          # Entry point
    ├── config.py             # pydantic-settings Settings
    ├── handlers/
    │   ├── __init__.py
    │   ├── private.py        # Private chat message handler
    │   ├── group.py          # Group chat message handler
    │   └── inline.py         # Inline query handler
    ├── services/
    │   ├── __init__.py
    │   ├── downloader.py     # yt-dlp wrapper service
    │   ├── url_parser.py     # URL detection and platform matching
    │   └── queue.py          # Download concurrency management
    ├── models/
    │   ├── __init__.py
    │   └── request.py        # VideoRequest, enums, status
    └── locales/
        ├── __init__.py
        └── messages.py       # EN/RU message dicts
tests/
├── conftest.py
├── unit/
│   ├── test_url_parser.py
│   ├── test_downloader.py
│   └── test_handlers.py
└── integration/
    └── test_bot_flow.py
```
