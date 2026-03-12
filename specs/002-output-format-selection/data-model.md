# Data Model: Output Format Selection

**Feature**: 002-output-format-selection | **Date**: 2026-03-12

## New Entities

### OutputFormat (Enum)

**Location**: `src/bot/models/request.py`

Represents the user's desired output format, parsed from message keywords.

| Value | Description |
|-------|-------------|
| `DEFAULT` | No format keyword detected. Use current behavior (video→MP4, slideshow→images+audio). |
| `AUDIO` | User requested audio-only extraction. Extract and send audio track from any content type. |
| `IMAGES` | User requested images-only. Send slideshow images without audio. Only valid for slideshows. |

**Relationships**: Used by handlers to decide which download/send path to follow. Produced by `format_parser.parse_output_format()`.

**Validation**: `IMAGES` format is only compatible with slideshow content. If `IMAGES` is requested for non-slideshow content, the handler returns an error message (FR-005).

**State transitions**: N/A (stateless enum, resolved once per request).

## Modified Entities

### VideoMetadata (dataclass)

**Location**: `src/bot/services/downloader.py`

No structural changes needed. The existing `is_slideshow` field is sufficient for the handler to validate format compatibility.

### SlideshowResult (dataclass)

**Location**: `src/bot/services/downloader.py`

No structural changes needed. The handler decides whether to send `image_paths`, `audio_path`, or both based on the `OutputFormat`.

### AudioResult (new dataclass)

**Location**: `src/bot/services/downloader.py`

Returned by the new `download_audio()` function.

| Field | Type | Description |
|-------|------|-------------|
| `audio_path` | `str` | Local filesystem path to the downloaded audio file (.m4a) |
| `title` | `str \| None` | Content title from metadata (used as audio title in Telegram) |
| `duration` | `int \| None` | Duration in seconds (used for Telegram audio metadata) |

**Relationships**: Created by `download_audio()`, consumed by handlers to send via `reply_audio()`.

## Keyword Sets

Not persisted as data — defined as constants in `format_parser.py`.

### Audio Keywords

```python
AUDIO_KEYWORDS: set[str] = {
    # English
    "audio", "mp3", "sound",
    # Russian
    "аудио", "звук", "музыка",
}
```

### Image Keywords

```python
IMAGE_KEYWORDS: set[str] = {
    # English
    "images", "pics", "photos", "png",
    # Russian
    "картинки", "фото", "изображения",
}
```

## Message Keys (new)

Added to `MESSAGES` dict in `src/bot/locales/messages.py`:

| Key | EN | RU | Used When |
|-----|----|----|-----------|
| `downloading_audio` | "Downloading audio..." | "Скачиваю аудио..." | Audio extraction started |
| `sending_audio` | "Sending audio..." | "Отправляю аудио..." | Audio upload started |
| `error_no_audio` | "This content has no audio track." | "В этом контенте нет аудиодорожки." | Audio requested but none available |
| `error_not_slideshow` | "This is a video, not a slideshow — images can't be extracted. Try "audio" to get the sound." | "Это видео, а не слайдшоу — изображения нельзя извлечь. Попробуйте «аудио», чтобы получить звук." | Images requested from non-slideshow |
| `help` (updated) | Updated to include format keyword examples | Updated to include format keyword examples | /start, /help, no-URL message |

## Entity Relationship Summary

```
Message Text
    │
    ├──► extract_url() ──► (url, Platform)
    │
    └──► parse_output_format(text, url) ──► OutputFormat
                                                │
                Handler decision matrix:        │
                ┌───────────────────────────────┘
                │
                ├─ DEFAULT + video      → download_video() → reply_video()
                ├─ DEFAULT + slideshow  → download_slideshow() → images + audio
                ├─ AUDIO + video        → download_audio() → reply_audio()
                ├─ AUDIO + slideshow    → download_audio() → reply_audio()
                ├─ IMAGES + slideshow   → download_slideshow(include_audio=False) → images only
                └─ IMAGES + video       → error_not_slideshow message
```
