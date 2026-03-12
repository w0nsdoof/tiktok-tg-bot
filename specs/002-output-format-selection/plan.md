# Implementation Plan: Output Format Selection

**Branch**: `002-output-format-selection` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-output-format-selection/spec.md`

## Summary

Add format keyword detection to the message processing pipeline so users can request alternative output formats (audio-only or images-only) by including a keyword alongside a link. The default behavior (video as MP4, slideshow as images+audio) remains unchanged when no keyword is present.

The implementation adds a format parser service, a new `download_audio()` function in the downloader (using yt-dlp's `FFmpegExtractAudio` postprocessor), and modifies the private/group handlers to route based on the detected format.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: python-telegram-bot 21.x (21.11.1), yt-dlp, pydantic-settings, structlog
**Storage**: Temp files for downloads, JSON for whitelist (no changes needed)
**Testing**: pytest + pytest-asyncio (asyncio_mode="auto")
**Target Platform**: Linux server (Telegram bot)
**Project Type**: Telegram bot service
**Performance Goals**: Audio extraction should complete within similar time as video download (~5-15s depending on source)
**Constraints**: 50MB Telegram file size limit, 3 concurrent downloads, Telegram `send_audio` only renders music player for `.mp3`/`.m4a` formats
**Scale/Scope**: Small whitelisted user base, ~15 source files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality** | ✅ PASS | New `format_parser` service has single responsibility (keyword detection). All new code will be typed and tested. No dead code introduced. |
| **II. UX Consistency** | ✅ PASS | New messages follow existing tone/structure in both EN/RU. Error messages are human-friendly ("This content is a video, not a slideshow — images can't be extracted."). Status messages follow existing pattern ("Downloading audio..."). Help message updated with format keyword examples. |
| **III. No Backwards Compatibility** | ✅ PASS | No deprecated code paths. Default behavior preserved naturally (format defaults to `DEFAULT` when no keyword found). No shims or migration layers. |
| **Development Standards** | ✅ PASS | No new secrets. No new dependencies (yt-dlp already has FFmpeg postprocessor built-in). Existing timeout/retry patterns maintained. |
| **Quality Gates** | ✅ PASS | Unit tests for format parser and audio download. Lint/format checks pass. |

## Project Structure

### Documentation (this feature)

```text
specs/002-output-format-selection/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── format-keywords.md
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/bot/
├── handlers/
│   ├── private.py       # MODIFY: add format detection, audio/images-only routing
│   ├── group.py         # MODIFY: same changes as private.py
│   └── inline.py        # NO CHANGE: inline mode ignores format keywords (per spec)
├── locales/
│   └── messages.py      # MODIFY: add new message keys for format-related UX
├── models/
│   └── request.py       # MODIFY: add OutputFormat enum
└── services/
    ├── format_parser.py # NEW: format keyword detection from message text
    ├── downloader.py    # MODIFY: add download_audio() function
    └── url_parser.py    # NO CHANGE: URL extraction is independent of format parsing

tests/
├── unit/
│   ├── test_format_parser.py  # NEW: keyword detection tests
│   └── test_downloader.py     # NEW: audio download tests (mock yt-dlp)
└── integration/
```

**Structure Decision**: Single-project layout (existing). No new directories beyond `contracts/` in specs. One new service file (`format_parser.py`), one new test file (`test_format_parser.py`), one new test file (`test_downloader.py`). All other changes are modifications to existing files.

## Complexity Tracking

No constitution violations — table not needed.
