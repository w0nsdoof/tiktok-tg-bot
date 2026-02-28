# tiktok-tg-bot

Telegram bot for downloading short videos from TikTok, YouTube Shorts, and Instagram Reels.

Send a link — get the video back. Works in private chats, groups, and inline mode.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env  # set BOT_TOKEN, ADMIN_USER_IDS, and optionally ALLOWED_USER_IDS
cd src && uv run python -m bot
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_USER_IDS` | — | Comma-separated admin Telegram user IDs (can approve/deny access) |
| `ALLOWED_USER_IDS` | `[]` | Comma-separated seed user IDs (imported as regular users on first run) |
| `MAX_FILE_SIZE` | `50` | Max video size in MB |
| `MAX_DURATION` | `300` | Max video duration in seconds |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Simultaneous download limit |
| `DATA_DIR` | `data` | Directory for persistent data (whitelist JSON) |

## Access Management

The bot uses a dynamic whitelist stored in `data/allowed_users.json`.

- **Admins** (`ADMIN_USER_IDS`): Can approve/deny access requests and add users by forwarding messages.
- **Regular users** (`ALLOWED_USER_IDS`): Seed list imported on first startup. After that, the JSON file is the source of truth.
- **New users**: Message the bot → tap "Request Access" → admin gets notified with Approve/Deny buttons.
- **Forward-to-add**: Admin forwards any message from a user to the bot → user gets whitelisted.

## Tech Stack

python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog
