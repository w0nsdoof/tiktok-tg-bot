# Contract: Telegram Bot Interface

**Date**: 2026-02-24 | **Type**: User-facing bot interactions

This bot exposes no HTTP APIs. All interaction is via Telegram Bot API update handlers.

## Message Handlers

### Private Chat — Text Message

**Trigger**: Any text message in a 1-on-1 chat with the bot.
**Access**: Whitelisted users only (non-whitelisted users are silently ignored).

| Input | Bot Response |
|-------|-------------|
| Valid video URL (supported platform, first link extracted) | Status message → Downloaded video as native video message |
| Valid URL but video > 5 min | Error: duration limit message |
| Valid URL but video > 50 MB | Error: file size limit message |
| Valid URL but private/deleted video | Error: unavailable video message |
| Valid URL but not a video page | Error: not a video link message |
| Non-URL text or unsupported platform | Help/usage message |

**Status feedback**: Bot sends "Downloading your video..." immediately upon receiving a valid link, before processing completes.

**Reply format**: Video is sent via `send_video` (native playable video, not document). Status/error messages are plain text.

### Group Chat — Text Message

**Trigger**: Any text message in a group/supergroup where the bot is a member.
**Access**: All group members (no whitelist check).

| Input | Bot Response |
|-------|-------------|
| Message containing a valid video URL | Reply-to-message with downloaded video |
| Message containing a valid URL but failing validation | Reply-to-message with appropriate error |
| Message without a recognized URL | No response (silent ignore) |

**Reply format**: Always uses `reply_to_message_id` to thread the response to the original message.

### Inline Query

**Trigger**: User types `@botname <query>` in any chat's message input field.
**Access**: Whitelisted users only (non-whitelisted users receive no results).

| Input | Inline Result |
|-------|--------------|
| Valid video URL | `InlineQueryResultVideo` or `InlineQueryResultCachedVideo` with the downloaded video |
| Valid URL but failing validation (too long, too large, etc.) | `InlineQueryResultArticle` with error description |
| Empty query or invalid URL | `InlineQueryResultArticle` with help/usage text |

**Cache**: `cache_time=0` during development; configurable for production.

## Commands

| Command | Scope | Description |
|---------|-------|-------------|
| /start | Private | Welcome message + usage instructions |
| /help | Private | Usage instructions with supported platforms |

No other commands are registered. The bot operates purely on link detection.

## Error Message Contract

All error messages follow this format:
- Human-friendly, no technical jargon or stack traces
- Available in English and Russian (auto-detected from `user.language_code`)
- Actionable where possible (e.g., "Please send a direct link to a video")

| Error Code | EN Template | RU Template |
|-----------|-------------|-------------|
| too_long | "This video is too long. I only support videos under 5 minutes." | "Это видео слишком длинное. Я поддерживаю видео до 5 минут." |
| too_large | "This video is too large to send via Telegram (over 50 MB)." | "Это видео слишком большое для отправки через Telegram (более 50 МБ)." |
| private | "This video is unavailable (private or deleted)." | "Это видео недоступно (приватное или удалено)." |
| platform_down | "Could not reach the platform right now. Please try again in a few minutes." | "Не удалось связаться с платформой. Попробуйте через несколько минут." |
| not_video | "This link doesn't point to a video. Please send a direct link to a video." | "Эта ссылка не ведёт на видео. Отправьте прямую ссылку на видео." |
| download_error | "Something went wrong while downloading. Please try again." | "Произошла ошибка при скачивании. Попробуйте ещё раз." |
| queued | "Your request is queued, please wait..." | "Ваш запрос в очереди, подождите..." |

## Rate Limits & Concurrency

- Max concurrent downloads: configurable (default 3)
- Excess requests: queued with user notification
- Telegram Bot API: standard rate limits apply (~30 messages/second per bot)
