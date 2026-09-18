# Quickstart: Output Format Selection

**Feature**: 002-output-format-selection | **Date**: 2026-03-12

## What This Feature Does

Adds format keyword detection to the bot's message processing. Users include a keyword (e.g., "audio", "images") alongside a link to control the output format. Without a keyword, behavior is unchanged.

## Files to Create

| File | Purpose |
|------|---------|
| `src/bot/services/format_parser.py` | Parse format keywords from message text (outside URL) |
| `tests/unit/test_format_parser.py` | Unit tests for keyword detection |
| `tests/unit/test_downloader.py` | Unit tests for audio download (mock yt-dlp) |

## Files to Modify

| File | Changes |
|------|---------|
| `src/bot/models/request.py` | Add `OutputFormat` enum |
| `src/bot/services/downloader.py` | Add `AudioResult` dataclass, `download_audio()` function, `include_audio` param on `download_slideshow()` |
| `src/bot/handlers/private.py` | Add format detection, route to audio/images-only paths, extract shared logic |
| `src/bot/handlers/group.py` | Same changes as private.py (shared helper) |
| `src/bot/locales/messages.py` | Add new message keys, update help message |

## Implementation Order

1. **`OutputFormat` enum** in `models/request.py` — foundation type
2. **`format_parser.py`** service + tests — keyword detection (independently testable)
3. **`download_audio()`** in `downloader.py` + tests — audio extraction (independently testable)
4. **`include_audio` param** on `download_slideshow()` — skip audio for images-only
5. **Message keys** in `messages.py` — new UX strings
6. **Handler updates** — wire format detection into private.py and group.py, extract shared helper
7. **Help message update** — add format keyword examples to help/start

## Key Technical Decisions

- **Audio format**: m4a (lossless remux from AAC sources, Telegram music player compatible)
- **yt-dlp postprocessor**: `FFmpegExtractAudio` with `preferredcodec="m4a"` — required for TikTok/Instagram (muxed-only sources)
- **Keyword matching**: Case-insensitive, whole-word, URL-excluded, first-match-wins
- **Handler dedup**: Shared helper function to avoid duplicating format logic in private.py and group.py (Constitution §I)

## How to Test Locally

```bash
# Run all tests
cd src && uv run pytest

# Run format parser tests only
cd src && uv run pytest tests/unit/test_format_parser.py -v

# Lint
cd src && uv run ruff check .
```

## Manual Testing Checklist

1. Send a TikTok video link with no keyword → video as MP4 (unchanged)
2. Send a TikTok video link with "audio" → audio file in music player
3. Send a YouTube Shorts link with "mp3" → audio file
4. Send a TikTok slideshow link with no keyword → images + audio (unchanged)
5. Send a TikTok slideshow link with "images" → images only, no audio
6. Send a TikTok slideshow link with "звук" → audio only
7. Send a video link with "pics" → error message about incompatible format
8. Send a link with "AUDIO" (uppercase) → audio file (case-insensitive)
9. Send a link in a group chat with "audio" → audio file (group support)
10. Send a link via inline mode with "audio" → default behavior (inline ignores keywords)
