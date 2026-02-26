# Implementation Plan: Video Download Bot

**Branch**: `001-video-download-bot` | **Date**: 2026-02-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-video-download-bot/spec.md`

## Summary

Build a Telegram bot in Python that accepts video links (TikTok, YouTube Shorts, Instagram Reels) and returns the downloaded video as a native Telegram video message. Uses python-telegram-bot v20+ for the Telegram interface and yt-dlp for video extraction/download. Supports private chats (whitelisted), group chats (open), and inline mode (whitelisted). Bilingual (EN/RU) with auto-detection.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog
**Storage**: N/A (no persistent storage; temporary files only)
**Testing**: pytest + pytest-asyncio (asyncio_mode="auto"), ruff, mypy
**Target Platform**: Linux server (Docker-deployable)
**Project Type**: Long-running service (Telegram bot with polling)
**Performance Goals**: Video delivered within 30s for videos under 2 minutes; 10 concurrent requests without degradation
**Constraints**: Telegram 50 MB upload limit; 5-minute video duration cap; ffmpeg required on PATH
**Scale/Scope**: Small user base (whitelist-gated); ~15 source files; single process

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Phase 0 Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | PASS | Type hints via mypy strict mode; ruff for lint/format; pytest for all business logic; single-responsibility modules |
| II. UX Consistency | PASS | Uniform message templates in locales/messages.py; all errors human-friendly per contract; immediate "Downloading..." feedback; /help command |
| III. No Backwards Compat | PASS | Greenfield project — no legacy to carry |
| Dev Standards | PASS | Conventional commits; secrets via env vars (pydantic SecretStr); deps pinned via uv.lock; yt-dlp retries with backoff |
| Quality Gates | PASS | CI will run ruff + mypy + pytest |

### Post-Phase 1 Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | PASS | Clean module separation: handlers/ services/ models/ locales/. No duplication — shared download logic in services/downloader.py used by all three handler types |
| II. UX Consistency | PASS | All user-facing strings in contracts/telegram-bot-interface.md; consistent EN/RU templates; reply-to in groups; inline results with descriptions |
| III. No Backwards Compat | PASS | No migration or compat concerns |
| Dev Standards | PASS | All settings in one pydantic-settings class; no secrets in code |
| Quality Gates | PASS | Test structure mirrors source structure |

**Gate result: PASS** — no violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/001-video-download-bot/
├── plan.md              # This file
├── research.md          # Phase 0 output — technology decisions
├── data-model.md        # Phase 1 output — entities and config
├── quickstart.md        # Phase 1 output — setup and run instructions
├── contracts/           # Phase 1 output — bot interface contract
│   └── telegram-bot-interface.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
└── bot/
    ├── __init__.py
    ├── __main__.py           # Entry point: build Application, register handlers, run_polling
    ├── config.py             # pydantic-settings Settings class
    ├── handlers/
    │   ├── __init__.py
    │   ├── private.py        # Private chat: link detection → download → send video
    │   ├── group.py          # Group chat: link detection → download → reply with video
    │   └── inline.py         # Inline query: link → process → InlineQueryResult
    ├── services/
    │   ├── __init__.py
    │   ├── downloader.py     # yt-dlp wrapper: extract_metadata, download_video
    │   ├── url_parser.py     # URL regex matching, platform detection
    │   └── queue.py          # asyncio.Semaphore-based concurrency limiter
    ├── models/
    │   ├── __init__.py
    │   └── request.py        # VideoRequest dataclass, enums (Platform, RequestStatus, ChatType)
    └── locales/
        ├── __init__.py
        └── messages.py       # EN/RU message dicts, get_message(key, lang) helper

tests/
├── conftest.py               # Shared fixtures: mock_bot, mock_message, mock_ydl
├── unit/
│   ├── test_url_parser.py    # URL detection and platform matching
│   ├── test_downloader.py    # yt-dlp wrapper (mocked yt-dlp)
│   ├── test_handlers.py      # Handler logic (mocked services)
│   └── test_messages.py      # Localization completeness
└── integration/
    └── test_bot_flow.py      # End-to-end with mocked Telegram API
```

**Structure Decision**: Single-project layout. This is a standalone bot service with no frontend/backend split, no library publishing, and no multi-platform targets. Flat `src/bot/` package with handler/service/model separation.

## Complexity Tracking

> No constitution violations — table not needed.
