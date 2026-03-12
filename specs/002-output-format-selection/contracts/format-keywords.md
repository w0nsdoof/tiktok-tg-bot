# Contract: Format Keywords

**Feature**: 002-output-format-selection | **Date**: 2026-03-12

## Overview

Users control the output format by including a keyword in the same message as a link. Keywords are detected outside the URL portion of the message text, are case-insensitive, and the first recognized keyword wins when multiple are present.

## Keyword → Format Mapping

### Audio Format

Triggers audio-only extraction from any content type (video or slideshow).

| Keyword | Language |
|---------|----------|
| `audio` | English |
| `mp3` | English |
| `sound` | English |
| `аудио` | Russian |
| `звук` | Russian |
| `музыка` | Russian |

**Output**: Audio file sent via Telegram music player (`.m4a` format). Title set from content metadata.

### Images Format

Triggers images-only extraction from slideshows. Returns error for non-slideshow content.

| Keyword | Language |
|---------|----------|
| `images` | English |
| `pics` | English |
| `photos` | English |
| `png` | English |
| `картинки` | Russian |
| `фото` | Russian |
| `изображения` | Russian |

**Output**: Images sent as Telegram media group(s), no audio.

## Behavior Rules

1. **No keyword** → default behavior (unchanged from current bot behavior)
2. **Keyword matching** → case-insensitive, whole-word only
3. **URL exclusion** → keywords inside the URL are ignored
4. **Multiple keywords** → first recognized keyword wins (left-to-right scan)
5. **Unrecognized keywords** → ignored, default behavior
6. **Group chats** → same behavior as private chats
7. **Inline mode** → format keywords ignored, default behavior only

## Compatibility Matrix

| Format | Video Content | Slideshow Content |
|--------|--------------|-------------------|
| DEFAULT | MP4 video | Images + audio |
| AUDIO | Audio track extracted | Audio track only |
| IMAGES | Error message | Images only (no audio) |

## Example Messages

```
# Default behavior (no keyword)
https://tiktok.com/@user/video/123
→ Downloads and sends video as MP4

# Audio extraction
audio https://tiktok.com/@user/video/123
→ Extracts and sends audio as .m4a

# Audio from slideshow
https://tiktok.com/@user/photo/123 звук
→ Sends only the slideshow's background audio

# Images only from slideshow
images https://tiktok.com/@user/photo/123
→ Sends only the slideshow images, no audio

# Incompatible format
pics https://tiktok.com/@user/video/123
→ Error: "This is a video, not a slideshow — images can't be extracted."
```
