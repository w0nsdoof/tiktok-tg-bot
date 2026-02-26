# Research: Video Download Bot

**Date**: 2026-02-24 | **Spec**: spec.md

## Decision Log

### D-001: Telegram Bot Framework

- **Decision**: python-telegram-bot v20+ (async)
- **Rationale**: Most mature Python Telegram library, fully async (asyncio), built-in support for all required features (inline mode, group chats, filters, chat actions). Extensive documentation and community.
- **Alternatives considered**:
  - aiogram 3.x — also excellent and async-first, but python-telegram-bot has larger community and more examples for our exact use case.
  - Telethon — user client library, not a bot framework.

### D-002: Video Download Engine

- **Decision**: yt-dlp (Python library, not CLI)
- **Rationale**: User-specified. Natively supports all three platforms (TikTok, YouTube Shorts, Instagram Reels). Provides metadata extraction without downloading, format selection with size filters, and configurable output paths.
- **Alternatives considered**: None — user requirement.

### D-003: Dependency Management

- **Decision**: uv (with pyproject.toml + uv.lock)
- **Rationale**: Current best practice for Python 3.12 projects (2025/2026). 10-100x faster than pip/Poetry, manages Python versions + venvs + deps in one tool. Committed lockfile ensures reproducible installs.
- **Alternatives considered**:
  - Poetry — viable but slower, uv is strictly better for application projects.
  - pip + requirements.txt — legacy approach, no lockfile guarantees.

### D-004: Configuration Management

- **Decision**: pydantic-settings with SecretStr for bot token
- **Rationale**: Type-safe config with automatic .env loading, validation, and coercion. SecretStr prevents token leakage in logs/repr. Standard pattern for modern Python projects.
- **Alternatives considered**:
  - python-dotenv — no validation, no type safety.
  - Plain os.environ — error-prone, no defaults mechanism.

### D-005: Linting & Formatting

- **Decision**: ruff (lint + format) + mypy (type checking)
- **Rationale**: ruff replaces flake8, isort, black, pyupgrade in a single Rust-based tool. mypy adds static type checking that ruff cannot do.
- **Alternatives considered**: flake8 + black + isort — three tools doing what one does.

### D-006: Testing

- **Decision**: pytest + pytest-asyncio (asyncio_mode="auto")
- **Rationale**: Standard Python testing stack. Auto mode eliminates boilerplate markers on async tests. AsyncMock for coroutines, MagicMock for sync yt-dlp calls.
- **Alternatives considered**: unittest — less ergonomic, no plugin ecosystem.

### D-007: Logging

- **Decision**: structlog (JSON in production, ConsoleRenderer in development)
- **Rationale**: Structured key-value logging with contextvars for per-request context binding. Clean dev output, machine-readable production output.
- **Alternatives considered**: stdlib logging — works but lacks structured output and context binding.

### D-008: Concurrency Model

- **Decision**: asyncio.Semaphore for download concurrency cap + asyncio.to_thread for blocking yt-dlp calls
- **Rationale**: yt-dlp is synchronous and blocking — must run in thread executor. Semaphore caps concurrent downloads (configurable, default 3). python-telegram-bot supports `concurrent_updates` for handling multiple updates simultaneously.
- **Alternatives considered**:
  - asyncio.Queue with workers — more complex, better for strict FIFO ordering. Can be added later if needed.
  - ProcessPoolExecutor — overkill for I/O-bound downloads.

### D-009: Localization Approach

- **Decision**: Simple dict-based translations (en/ru) with language detection from `user.language_code`
- **Rationale**: Only two languages needed. A full i18n framework (gettext, fluent) adds complexity for minimal benefit. Dict lookup with fallback to English is sufficient.
- **Alternatives considered**:
  - gettext/.po files — overkill for 2 languages with ~15 strings.
  - fluent — powerful but unnecessary overhead.

### D-010: Whitelist Implementation

- **Decision**: `filters.User(user_id=...)` for private chat handlers + conditional check in inline handler
- **Rationale**: python-telegram-bot's built-in filter is the cleanest approach for simple whitelists. Group chat handlers omit the filter per spec (open to all members). Inline handler needs a manual check since filters work differently for inline queries.
- **Alternatives considered**:
  - Global TypeHandler gate at group=-1 — would block group chats too, requires more complex logic to exempt them.
  - Decorator pattern — works but redundant when built-in filter exists.

## Technical Findings

### yt-dlp Key Patterns

- **Metadata extraction**: `ydl.extract_info(url, download=False)` returns duration, filesize, formats list
- **Duration check**: Use `match_filter` callback or pre-flight `extract_info` check
- **Format string for <50MB**: `bestvideo[filesize<=50M][ext=mp4]+bestaudio[filesize<=50M][ext=m4a]/best[filesize<=50M]/bestvideo[filesize_approx<=50M]+bestaudio[filesize_approx<=50M]/best[filesize_approx<=50M]/worst`
- **Thread safety**: NOT thread-safe for shared instances. One YoutubeDL instance per download (context manager)
- **Concurrency**: Wrap in `asyncio.to_thread()` to avoid blocking event loop
- **System dependency**: ffmpeg required on PATH for merging separate video+audio streams
- **Error types**: `DownloadError` (general), `ExtractorError` (platform-specific). Parse error message strings to classify (private, deleted, rate-limited)

### python-telegram-bot v20+ Key Patterns

- **Async architecture**: All handlers are `async def`, built on asyncio
- **Chat type routing**: `filters.ChatType.PRIVATE`, `filters.ChatType.GROUP | filters.ChatType.SUPERGROUP`
- **Video sending**: `bot.send_video(chat_id, video=file, supports_streaming=True)` — must be MP4 for native playback
- **File size limit**: 50 MB for multipart upload (standard Bot API)
- **Chat actions**: `bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)` — lasts ~5s, must re-send for longer ops
- **Language code**: `update.effective_user.language_code` — can be None, BCP 47 format
- **Concurrent updates**: `Application.builder().token(TOKEN).concurrent_updates(True).build()`
- **Inline mode**: `InlineQueryHandler` + `InlineQueryResultVideo` / `InlineQueryResultArticle`

### Platform-Specific Notes

| Platform | URL Patterns | Notes |
|----------|-------------|-------|
| TikTok | `tiktok.com/@user/video/ID`, `vm.tiktok.com/SHORTCODE` | Rate limiting possible; may need custom User-Agent |
| YouTube Shorts | `youtube.com/shorts/ID`, `youtu.be/ID` | Reliable extraction |
| Instagram Reels | `instagram.com/reel/ID`, `instagram.com/reels/ID` | May need cookies for private/restricted content |
