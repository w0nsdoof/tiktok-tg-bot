# tiktok-tg-bot

Telegram bot for downloading short videos from TikTok, YouTube Shorts, and Instagram Reels.

Send a link — get the video back. Works in private chats, groups, and inline mode.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env  # set BOT_TOKEN and ALLOWED_USER_IDS
cd src && uv run python -m bot
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `ALLOWED_USER_IDS` | — | Comma-separated Telegram user IDs |
| `MAX_FILE_SIZE` | `50` | Max video size in MB |
| `MAX_DURATION` | `300` | Max video duration in seconds |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Simultaneous download limit |

## Tech Stack

python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog
