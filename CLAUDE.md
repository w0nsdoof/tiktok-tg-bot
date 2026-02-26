# tiktok-tg-bot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-24

## Active Technologies

- Python 3.12 + python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog (001-video-download-bot)

## Project Structure

```text
src/
tests/
```

## Commands

- Install deps: `uv sync`
- Run bot: `cd src && uv run python -m bot`
- Tests: `cd src && uv run pytest`
- Lint: `cd src && uv run ruff check .`

## Code Style

Python 3.12: Follow standard conventions

## Recent Changes

- 001-video-download-bot: Added Python 3.12 + python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog

<!-- MANUAL ADDITIONS START -->

## Quick Start

See [README.md](README.md) for setup instructions and configuration options.

<!-- MANUAL ADDITIONS END -->
