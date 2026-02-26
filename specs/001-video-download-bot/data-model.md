# Data Model: Video Download Bot

**Date**: 2026-02-24 | **Spec**: spec.md

> This bot has no persistent storage. All models are in-memory runtime objects.

## Entities

### VideoRequest

Represents a single user download request from creation to completion.

| Field | Type | Description |
|-------|------|-------------|
| id | str (UUID) | Unique request identifier |
| url | str | Original URL sent by the user |
| platform | Platform (enum) | Detected source platform |
| user_id | int | Telegram user ID of requester |
| chat_id | int | Telegram chat ID where request originated |
| message_id | int \| None | Original message ID (for reply_to in groups) |
| chat_type | ChatType (enum) | private, group, supergroup, or inline |
| language | str | User's language code ("en" or "ru") |
| status | RequestStatus (enum) | Current processing state |
| duration | int \| None | Video duration in seconds (from metadata) |
| file_size | int \| None | Video file size in bytes (from metadata or post-download) |
| file_path | str \| None | Local path to downloaded file (temporary) |
| error | str \| None | Error message if failed |
| created_at | datetime | Request creation timestamp |

**Validation rules**:
- `url` must match a supported platform pattern
- `duration` must be <= 300 seconds (5 minutes) to proceed with download
- `file_size` must be <= 52,428,800 bytes (50 MB) to send via Telegram

### RequestStatus (Enum)

State machine for a video request lifecycle.

```
pending → extracting → downloading → sending → completed
    \         \            \           \
     → failed   → failed    → failed    → failed
```

| Value | Description |
|-------|-------------|
| pending | Request received, awaiting processing |
| extracting | Fetching video metadata (duration, formats) |
| downloading | Downloading video file |
| sending | Uploading video to Telegram |
| completed | Video sent successfully |
| failed | Error occurred at any stage |

### Platform (Enum)

| Value | URL Patterns |
|-------|-------------|
| tiktok | `tiktok.com`, `vm.tiktok.com` |
| youtube | `youtube.com/shorts`, `youtu.be` |
| instagram | `instagram.com/reel`, `instagram.com/reels` |

### ChatType (Enum)

| Value | Description |
|-------|-------------|
| private | Direct message to bot |
| group | Group or supergroup chat |
| inline | Inline query from any chat |

## Settings (pydantic-settings)

| Field | Type | Default | Env Var | Description |
|-------|------|---------|---------|-------------|
| bot_token | SecretStr | — (required) | BOT_TOKEN | Telegram Bot API token |
| allowed_user_ids | list[int] | [] | ALLOWED_USER_IDS | Comma-separated whitelist |
| max_duration | int | 300 | MAX_DURATION | Max video duration in seconds |
| max_file_size | int | 50 | MAX_FILE_SIZE | Max file size in MB |
| max_concurrent_downloads | int | 3 | MAX_CONCURRENT_DOWNLOADS | Semaphore limit |
| download_dir | str | /tmp/tg-bot-downloads | DOWNLOAD_DIR | Temp directory for downloads |
| log_level | str | INFO | LOG_LEVEL | Logging level |
| log_json | bool | false | LOG_JSON | JSON log output (for production) |

## Localization Strings

Two dicts: `MESSAGES["en"]` and `MESSAGES["ru"]`, keyed by message identifier.

| Key | Context |
|-----|---------|
| downloading | Feedback after receiving valid link |
| success | (none — video is sent as the response) |
| error_too_long | Video exceeds duration limit |
| error_too_large | Video exceeds file size limit |
| error_private | Video is private or deleted |
| error_platform_down | Platform unreachable / rate limited |
| error_not_video | Link doesn't point to a video |
| error_download | Generic download failure |
| error_unknown | Unexpected error |
| help | Usage instructions (private chat) |
| help_inline | Usage hint shown as inline result |
| queued | Request queued (concurrent limit reached) |
