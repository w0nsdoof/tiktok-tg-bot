# tiktok-tg-bot

Telegram bot for downloading short videos from TikTok, YouTube Shorts, and Instagram Reels.

Send a link — get the video back. Works in private chats, groups, and inline mode.

## Format Keywords

Add a keyword alongside a link to change the output format:

| Keyword | Language | Effect |
|---|---|---|
| `audio`, `mp3`, `sound` | English | Extract audio only (.m4a) |
| `аудио`, `звук`, `музыка` | Russian | Extract audio only (.m4a) |
| `images`, `pics`, `photos`, `png` | English | Slideshow images only (no audio) |
| `картинки`, `фото`, `изображения` | Russian | Slideshow images only (no audio) |

Without a keyword, default behavior is preserved (video as MP4, slideshow as images + audio).

## Local Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env  # set BOT_TOKEN, ADMIN_USER_IDS
cd src && uv run python -m bot
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md).

## Tech Stack

python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog
