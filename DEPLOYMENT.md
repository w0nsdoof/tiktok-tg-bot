# Deployment

## Server

- **Host**: `ssh yandex` (Yandex Cloud VM)
- **OS**: Ubuntu 22.04 LTS, x86_64
- **Docker**: 28.x with Compose 2.x
- **Project path**: `~/tiktok-tg-bot`
- **Git remote**: `https://github.com/w0nsdoof/tiktok-tg-bot.git`

## Deploy Code Updates

```bash
ssh yandex
cd ~/tiktok-tg-bot
git pull
docker compose up -d --build
```

## Common Operations

### View logs

```bash
docker compose logs -f          # follow live
docker compose logs --tail 50   # last 50 lines
```

### Restart bot

```bash
# without env/code changes
docker compose restart

# after .env changes (restart does NOT reload .env)
docker compose up -d

# after code changes
docker compose up -d --build
```

### Stop bot

```bash
docker compose down
```

## Docker Setup

The bot runs as a single container via `docker-compose.yml`:

- **Image**: built from `Dockerfile` (Python 3.12-slim + ffmpeg + uv)
- **Restart policy**: `unless-stopped`
- **Volumes**:
  - `downloads` -> `/tmp/tg-bot-downloads` (temporary media files)
  - `botdata` -> `/app/src/data` (persistent whitelist JSON)

## Environment Variables

Configured in `.env` on the server (never committed to git).

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | required | Telegram bot token from @BotFather |
| `ADMIN_USER_IDS` | `[]` | Admin Telegram user IDs (comma-separated) |
| `ALLOWED_USER_IDS` | `[]` | Seed user IDs imported on first run (comma-separated) |
| `MAX_FILE_SIZE` | `50` | Max file size in MB |
| `MAX_DURATION` | `300` | Max video duration in seconds |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Concurrent download limit |
| `DOWNLOAD_DIR` | `/tmp/tg-bot-downloads` | Temp download directory |
| `DATA_DIR` | `data` | Persistent data directory |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_JSON` | `false` | JSON log format |

## Managing Access

Users are managed dynamically — no need to edit `.env` or restart the bot.

- **New user requests access**: They message the bot -> tap "Request Access" -> admin gets Approve/Deny buttons.
- **Forward-to-add**: Forward any message from a user to the bot -> they get whitelisted instantly.
- `ADMIN_USER_IDS` and `ALLOWED_USER_IDS` in `.env` are seed values imported on first startup. After that, `data/allowed_users.json` is the source of truth.

## First-Time Setup

```bash
ssh yandex
git clone https://github.com/w0nsdoof/tiktok-tg-bot.git
cd tiktok-tg-bot
cp .env.example .env
# edit .env: set BOT_TOKEN, ADMIN_USER_IDS
docker compose up -d --build
```
