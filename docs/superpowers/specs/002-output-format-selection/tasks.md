# Tasks: Output Format Selection

**Input**: Design documents from `/specs/002-output-format-selection/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/format-keywords.md

**Tests**: Included — plan.md specifies pytest + pytest-asyncio and lists test files as deliverables.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Core types, services, and messages that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 Add `OutputFormat` enum (DEFAULT, AUDIO, IMAGES) to `src/bot/models/request.py`
- [X] T002 [P] Create format keyword detection service with `AUDIO_KEYWORDS`, `IMAGE_KEYWORDS` sets and `parse_output_format(text, url)` function in `src/bot/services/format_parser.py`
- [X] T003 [P] Add format-related message keys (`downloading_audio`, `sending_audio`, `error_no_audio`, `error_not_slideshow`) in both EN/RU to `src/bot/locales/messages.py`
- [X] T004 Write unit tests for `parse_output_format()` covering: no keyword → DEFAULT, audio keywords (EN/RU) → AUDIO, image keywords (EN/RU) → IMAGES, case-insensitivity, URL exclusion, first-keyword-wins, unrecognized keywords → DEFAULT, and punctuation-adjacent keywords (e.g., "audio!" or "audio,") in `tests/unit/test_format_parser.py`

**Checkpoint**: Foundation types and services ready — user story implementation can begin

---

## Phase 2: User Story 1 — Default Link Behavior Unchanged (Priority: P1) 🎯 MVP

**Goal**: Integrate format detection into the message processing pipeline while preserving existing behavior when no keyword is present. Refactor private/group handlers to use a shared processing helper (per research R6).

**Independent Test**: Send any supported link (TikTok, YouTube Shorts, Instagram Reel) without format keywords and verify current behavior is preserved (video→MP4, slideshow→images+audio).

### Implementation for User Story 1

- [X] T005 [US1] Extract shared `_process_request()` helper from `handle_private_message()` containing: URL extraction, format detection via `parse_output_format()`, metadata extraction, download/send routing. Metadata validation (duration/size checks per FR-011) MUST run before format-specific routing so all paths respect the same limits. DEFAULT format routes to existing video and slideshow logic. Place in a shared location importable by both handlers (e.g., `src/bot/handlers/common.py` or within `src/bot/handlers/private.py`)
- [X] T006 [US1] Refactor `handle_private_message()` to delegate to `_process_request()` in `src/bot/handlers/private.py`
- [X] T007 [US1] Refactor `handle_group_message()` to delegate to `_process_request()` (passing `reply_to=message.message_id`) in `src/bot/handlers/group.py`

**Checkpoint**: Bot behaves identically to before for all links without format keywords. Both handlers use shared logic.

---

## Phase 3: User Story 2 — Extract Audio from Video (Priority: P2)

**Goal**: Users include an audio keyword (e.g., "audio", "mp3", "звук") with a video link and receive the audio track as a Telegram music player file (.m4a).

**Independent Test**: Send a TikTok video link with the keyword "audio" and verify the bot sends an audio file in the music player instead of a video.

### Implementation for User Story 2

- [X] T008 [US2] Add `AudioResult` dataclass (`audio_path`, `title`, `duration`) and `download_audio()` async function using `format="bestaudio/best"` with `FFmpegExtractAudio` postprocessor (`preferredcodec="m4a"`). Detect no-audio-track errors from yt-dlp/FFmpeg and raise a specific `VideoDownloadError` (e.g., new `ErrorType.NO_AUDIO`) so the handler can map it to the `error_no_audio` message (US2 scenario 4) in `src/bot/services/downloader.py`
- [X] T009 [US2] Write unit tests for `download_audio()` (mock yt-dlp) covering: successful extraction returns AudioResult, no-audio-track error raises `NO_AUDIO`, general error handling, and file cleanup in `tests/unit/test_downloader.py`
- [X] T010 [US2] Add AUDIO+video routing to `_process_request()`: show `downloading_audio` status, call `download_audio()`, show `sending_audio` status, send via `reply_audio()` with title and filename metadata. Map `ErrorType.NO_AUDIO` to `error_no_audio` message in error handler in `src/bot/handlers/private.py` (or `common.py`)

**Checkpoint**: Audio extraction works for video links in both private and group chats.

---

## Phase 4: User Story 3 — Extract Images from Slideshow (Priority: P3)

**Goal**: Users include an image keyword (e.g., "images", "pics", "картинки") with a slideshow link and receive only the images, without the audio file. Users who request images from a non-slideshow video get a clear error message.

**Independent Test**: Send a TikTok slideshow link with the keyword "images" and verify the bot sends only images without audio.

### Implementation for User Story 3

- [X] T011 [US3] Add `include_audio` parameter (default `True`) to `_download_slideshow_sync()` and `download_slideshow()` to skip the audio download step when `False` in `src/bot/services/downloader.py`
- [X] T012 [US3] Add IMAGES+slideshow routing to `_process_request()`: call `download_slideshow(url, dir, include_audio=False)`, send only images. Add IMAGES+video routing: reply with `error_not_slideshow` message before download in `src/bot/handlers/private.py` (or `common.py`)

**Checkpoint**: Images-only extraction works for slideshows; incompatible format (images from video) shows error.

---

## Phase 5: User Story 4 — Extract Audio from Slideshow (Priority: P3)

**Goal**: Users include an audio keyword with a slideshow link and receive only the background audio, without images.

**Independent Test**: Send a TikTok slideshow link with the keyword "audio" and verify the bot sends only the audio file without images.

### Implementation for User Story 4

- [X] T013 [US4] Add AUDIO+slideshow routing to `_process_request()`: call `download_audio()` (reuses US2 implementation), send audio via `reply_audio()` with title metadata in `src/bot/handlers/private.py` (or `common.py`)

**Checkpoint**: All four format combinations work (DEFAULT/AUDIO/IMAGES × video/slideshow).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Help message update and final validation

- [X] T014 [P] Update help message in both EN/RU with format keyword examples (e.g., "Add 'audio' or 'images' to your message to change the output format") in `src/bot/locales/messages.py`
- [X] T015 [P] Write handler routing tests covering the 6-branch decision matrix (DEFAULT/AUDIO/IMAGES × video/slideshow) including the IMAGES+video error path, verifying correct download function and send method is called for each combination in `tests/unit/test_handler_routing.py`
- [ ] T016 Run `quickstart.md` manual testing validation (all 10 test scenarios)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — can start immediately. BLOCKS all user stories.
- **US1 (Phase 2)**: Depends on Phase 1 — handler refactoring must complete before format routing.
- **US2 (Phase 3)**: Depends on Phase 2 — needs shared handler to add audio routing.
- **US3 (Phase 4)**: Depends on Phase 3 (US2) — both modify `downloader.py` and handler; must run sequentially.
- **US4 (Phase 5)**: Depends on Phase 4 (US3) — reuses `download_audio()` from US2, sequential to avoid handler conflicts.
- **Polish (Phase 6)**: Depends on all user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 1 — no dependencies on other stories
- **US2 (P2)**: Can start after US1 — no dependencies on US3/US4
- **US3 (P3)**: Can start after US2 — both US2 and US3 modify `downloader.py` and the handler file, so they MUST run sequentially
- **US4 (P3)**: Can start after US3 — reuses `download_audio()` from US2

### Within Each User Story

- Models/dataclasses before service functions
- Service functions before handler routing
- Tests [P] with implementation where marked

### Parallel Opportunities

- T002 and T003 can run in parallel (different files)
- T014 can run in parallel with other Phase 6 tasks
- **Note**: US2 and US3 cannot run in parallel — both modify `downloader.py` and the handler file

---

## Parallel Example: Phase 1 Foundation

```bash
# T002 and T003 can run in parallel (different files):

Task T002: "Create format_parser.py in src/bot/services/format_parser.py"
Task T003: "Add message keys in src/bot/locales/messages.py"

# Then T004 (tests for format parser) after T002 completes
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Foundational types and services
2. Complete Phase 2: US1 — handler refactoring with format detection
3. **STOP and VALIDATE**: Send links without keywords, verify behavior unchanged
4. Deploy if ready — zero user-facing changes, but infrastructure is in place

### Incremental Delivery

1. Phase 1 (Foundational) → Core types ready
2. Phase 2 (US1) → Default behavior preserved with format infrastructure → **MVP**
3. Phase 3 (US2) → Audio extraction from videos → Deploy
4. Phase 4 (US3) → Images-only from slideshows → Deploy
5. Phase 5 (US4) → Audio from slideshows → Deploy
6. Phase 6 (Polish) → Help message updated → Final deploy

### Key Technical Notes

- **Audio format**: m4a via `FFmpegExtractAudio` postprocessor (per research R1)
- **Keyword matching**: Case-insensitive, whole-word, URL-excluded, first-match-wins (per research R2)
- **Handler dedup**: Shared `_process_request()` helper (per research R6, Constitution §I)
- **Slideshow images-only**: `include_audio=False` param on existing `download_slideshow()` (per research R4)
- **Error handling**: Check format compatibility after metadata extraction, before download (per research R5)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
