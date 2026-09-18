# tiktok-tg-bot

Telegram bot (long polling, outbound only) that downloads TikTok videos/slideshows, YouTube
Shorts and Instagram reels/posts. The optional `web` service (Compose profile `control-panel`)
is an Authentik-OIDC FastAPI panel for access and runtime settings. Human docs: `README.md`,
`docs/control-panel.md`.

## Stack

Python 3.12, uv, python-telegram-bot 21 (job-queue), yt-dlp (ffmpeg + deno in the image),
asyncpg/PostgreSQL, FastAPI + Authlib, pydantic-settings, structlog.

## Commands

- Install: `uv sync --extra dev` (dev tools are an extra; plain `uv sync` removes pytest/ruff/mypy)
- Run bot: `cd src && uv run python -m bot` (settings load `../.env`; `DATA_DIR=data` is under `src/`)
- Tests: `uv run pytest` · Lint: `uv run ruff check .` · Types: `uv run mypy` (strict)

## Layout

- `src/bot/__main__.py` — handler/filter wiring, heartbeat and access-refresh jobs
- `src/bot/handlers/` — private, group, inline, admin (access requests, `/link`), stats
  (`/stats`, `/top`); `common.py` holds the shared download-and-send flow
- `src/bot/services/` — `downloader` (yt-dlp), `url_parser`, `format_parser`, `queue`,
  `user_store` (users, roles, runtime settings), `analytics` (writes), `stats` (reads)
- `src/bot/web.py` — control panel (`bot.web:create_app`); `src/bot/locales/messages.py` — EN/RU text
- `tests/unit/` — all tests; `docs/superpowers/` — historical specs/plans, don't edit

## Gotchas

- PostgreSQL (`DATABASE_DSN`, else `ANALYTICS_DSN`) is authoritative for access and runtime
  settings; `ADMIN_USER_IDS`, `ALLOWED_USER_IDS` and `data/allowed_users.json` are import seeds.
  The bot re-reads the store every 15 s, so panel changes apply without restart.
- Analytics is fire-and-forget: DB errors are logged and dropped, never block a download.
- Liveness is the `data/heartbeat` mtime (written every 30 s); Compose marks the bot unhealthy
  after 90 s.
- Keep `httpx`/`httpcore` logging at WARNING: Telegram API URLs contain the bot token.
- The Instagram cookies file is mounted read-only and handed to yt-dlp as an in-memory copy,
  because yt-dlp rewrites its cookie file on close.

## Deploy

Push to `master`, then `make deploy-bot` from `~/coding/petprojects` (rebuilds `bot` and `web`).
