# Deployment Guide

## Server Access

```bash
ssh yandex
cd ~/tiktok-tg-bot
```

## Common Operations

### View logs

```bash
docker compose logs -f          # follow live
docker compose logs --tail 50   # last 50 lines
```

### Restart bot (without env changes)

```bash
docker compose restart
```

### Restart bot (with env changes)

**Important:** `docker compose restart` does NOT reload `.env`. You must recreate the container:

```bash
docker compose up -d
```

### Rebuild and restart (after code changes)

```bash
docker compose up -d --build
```

### Stop bot

```bash
docker compose down
```

## Managing Access

Users are now managed dynamically — no need to edit `.env` or restart the bot.

### Via Telegram (preferred)

- **New user requests access**: They message the bot → tap "Request Access" → admin gets Approve/Deny buttons.
- **Forward-to-add**: Forward any message from a user to the bot → they get whitelisted instantly.

### Via env (initial setup only)

`ADMIN_USER_IDS` and `ALLOWED_USER_IDS` in `.env` are seed values. They get imported into `data/allowed_users.json` on first startup. After that, the JSON file is the source of truth.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token | required |
| `ADMIN_USER_IDS` | Admin Telegram user IDs (comma-separated) | `[]` |
| `ALLOWED_USER_IDS` | Seed user IDs imported on first run (comma-separated) | `[]` |
| `MAX_DURATION` | Max video duration in seconds | `300` |
| `MAX_FILE_SIZE` | Max file size in MB | `50` |
| `MAX_CONCURRENT_DOWNLOADS` | Concurrent download limit | `3` |
| `DOWNLOAD_DIR` | Temp download directory | `/tmp/tg-bot-downloads` |
| `DATA_DIR` | Persistent data directory (whitelist JSON) | `data` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_JSON` | JSON log format | `false` |

## Deploying Code Updates

```bash
# on server
cd ~/tiktok-tg-bot
git pull
docker compose up -d --build
```
