# tiktok-tg-bot

Telegram bot for downloading TikTok videos and slideshows, YouTube Shorts, and Instagram
reels, photos and carousels.

Send a link — get the media back. Works in private chats, groups, and inline mode.

## Format Keywords

Add a keyword alongside a link to change the output format:

| Keyword | Language | Effect |
|---|---|---|
| `audio`, `mp3`, `sound` | English | Extract audio only (.m4a) |
| `аудио`, `звук`, `музыка` | Russian | Extract audio only (.m4a) |
| `images`, `pics`, `photos`, `png` | English | Images only (slideshows, Instagram posts) |
| `картинки`, `фото`, `изображения` | Russian | Images only (slideshows, Instagram posts) |

Without a keyword, videos arrive as MP4, slideshows as images + audio, and Instagram posts as
albums of photos and videos.

## Local Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
cp .env.example .env  # set BOT_TOKEN, ADMIN_USER_IDS
cd src && uv run python -m bot
```

Tests and checks run from the repo root: `uv run pytest`, `uv run ruff check .`, `uv run mypy`.

## Configuration

All variables are listed with defaults in [.env.example](.env.example). Notable ones:

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes | Telegram bot token |
| `ADMIN_USER_IDS` / `ALLOWED_USER_IDS` | No | Admin and user IDs imported into the access store on startup |
| `ANALYTICS_DSN` | No | Postgres DSN for usage analytics (e.g. `postgresql://user:pass@host:5432/dbname`); unset = analytics disabled |
| `DATABASE_DSN` | No | Primary PostgreSQL DSN for access control and runtime settings; defaults to `ANALYTICS_DSN` |
| `INSTAGRAM_COOKIES_FILE` | No | Netscape-format cookies file passed to yt-dlp for Instagram posts that require login |

Access requests are handled in Telegram: new users tap "Request Access" and an admin approves
or denies; forwarding a user's message to the bot whitelists them.

### Instagram cookies

Instagram may require a logged-in session or rate-limit anonymous requests. Export a
Netscape-format cookies file from an account that can view the posts, save it on the server
as `secrets/instagram-cookies.txt` in the repo checkout (mounted read-only at `/app/secrets`),
and set `INSTAGRAM_COOKIES_FILE=/app/secrets/instagram-cookies.txt` in `.env`. Keep the file
private; it grants access to that Instagram session.

## Web control panel

The Compose stack includes an Authentik OIDC-protected FastAPI control panel (`web` service,
profile `control-panel`) for access requests, Telegram-to-Authentik account linking, roles, and
live download/group limits. It uses the same PostgreSQL database and is not published directly
to the host.

See [docs/control-panel.md](docs/control-panel.md) for the Authentik, Caddy, environment, and
deployment configuration.

## Deployment

The server holds a git checkout of this repo and its `.env`. `make deploy-bot` in the
petprojects control repo runs `git pull && docker compose --profile control-panel up -d --build`
there, rebuilding both the bot and the control panel.

After a `.env` change use `docker compose up -d`; `restart` does not reload it.

## Tech Stack

python-telegram-bot 21.x, yt-dlp, FastAPI, Authlib, asyncpg, pydantic-settings, structlog
