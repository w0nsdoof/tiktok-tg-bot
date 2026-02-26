# Tasks: Video Download Bot

**Input**: Design documents from `/specs/001-video-download-bot/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/telegram-bot-interface.md

**Tests**: Not included — not explicitly requested in the feature specification. Test file structure is defined in plan.md for future addition.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and tooling configuration

- [x] T001 Create project directory structure with all `__init__.py` files: `src/bot/`, `src/bot/handlers/`, `src/bot/services/`, `src/bot/models/`, `src/bot/locales/`
- [x] T002 Initialize Python 3.12 project with uv, add python-telegram-bot 21.x, yt-dlp, pydantic-settings, structlog, pytest, pytest-asyncio, ruff, mypy as dependencies in `pyproject.toml` and run `uv sync`
- [x] T003 [P] Configure ruff (lint + format) and mypy (strict mode) settings in `pyproject.toml`
- [x] T004 [P] Create `.env.example` with all environment variables from data-model.md: BOT_TOKEN, ALLOWED_USER_IDS, MAX_DURATION, MAX_FILE_SIZE, MAX_CONCURRENT_DOWNLOADS, DOWNLOAD_DIR, LOG_LEVEL, LOG_JSON
- [x] T005 [P] Create `.gitignore` for Python project (venv, `__pycache__`, `.env`, `*.pyc`, `.mypy_cache`, `.ruff_cache`, `/tmp/tg-bot-downloads/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 [P] Implement Settings class with pydantic-settings in `src/bot/config.py`: BOT_TOKEN (SecretStr), ALLOWED_USER_IDS (list[int] from comma-separated env), MAX_DURATION (default 300), MAX_FILE_SIZE (default 50), MAX_CONCURRENT_DOWNLOADS (default 3), DOWNLOAD_DIR (default /tmp/tg-bot-downloads), LOG_LEVEL (default INFO), LOG_JSON (default false). Use `model_config` with `env_file=".env"`.
- [x] T007 [P] Create Platform enum (tiktok, youtube, instagram), RequestStatus enum (pending, extracting, downloading, sending, completed, failed), ChatType enum (private, group, inline), and VideoRequest dataclass with all fields from data-model.md in `src/bot/models/request.py`
- [x] T008 [P] Implement EN/RU message dictionaries with all keys from data-model.md (downloading, error_too_long, error_too_large, error_private, error_platform_down, error_not_video, error_download, error_unknown, help, help_inline, queued) and `get_message(key, lang)` helper with English fallback in `src/bot/locales/messages.py`
- [x] T009 Implement URL regex matching for all supported platforms (tiktok.com, vm.tiktok.com, youtube.com/shorts, youtu.be, instagram.com/reel, instagram.com/reels) and `extract_url(text)` function that returns the first matched URL plus detected Platform enum, or None in `src/bot/services/url_parser.py`
- [x] T010 [P] Implement yt-dlp wrapper service in `src/bot/services/downloader.py`: `extract_metadata(url)` returns duration/filesize without downloading; `download_video(url, output_dir)` downloads best quality under 50 MB as MP4; validate duration <= MAX_DURATION and file_size <= MAX_FILE_SIZE; classify yt-dlp errors (private/deleted, rate-limited, not-a-video) into user-friendly error types; use `asyncio.to_thread()` for blocking yt-dlp calls; clean up temp files on failure
- [x] T011 [P] Implement asyncio.Semaphore-based concurrency limiter in `src/bot/services/queue.py`: `DownloadQueue` class wrapping Semaphore with configurable limit from Settings; context manager that acquires/releases; method to check if queue is full and notify user with "queued" message
- [x] T012 Create bot Application builder with `concurrent_updates=True`, configure structlog (JSON renderer if LOG_JSON else ConsoleRenderer), create download directory if not exists, and `run_polling()` entry point in `src/bot/__main__.py`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Direct Chat Download (Priority: P1) 🎯 MVP

**Goal**: A whitelisted user sends a video link in a private chat and receives the downloaded video as a playable Telegram video message.

**Independent Test**: Send a valid TikTok/YouTube/Instagram link to the bot in a private chat and verify a video file is returned within 30 seconds.

### Implementation for User Story 1

- [x] T013 [US1] Implement private chat message handler in `src/bot/handlers/private.py`: filter with `filters.ChatType.PRIVATE & filters.User(user_id=allowed_ids)`; extract URL via url_parser; if no URL found → send localized help message; if URL found → send "Downloading..." feedback with `send_chat_action(UPLOAD_VIDEO)`; acquire download queue; extract metadata and validate duration/size; download video; `send_video()` with `supports_streaming=True`; handle all error types from downloader with localized error messages from locales/messages.py; clean up temp file in finally block
- [x] T014 [US1] Implement /start and /help command handlers in `src/bot/handlers/private.py`: `/start` sends welcome message with usage instructions; `/help` sends supported platforms list and usage format; both use localized messages based on `user.language_code`; both filtered to whitelisted users only
- [x] T015 [US1] Register private chat MessageHandler, /start CommandHandler, and /help CommandHandler in `src/bot/__main__.py`

**Checkpoint**: User Story 1 fully functional — bot accepts links in private chat and returns videos

---

## Phase 4: User Story 2 — Group Chat Download (Priority: P2)

**Goal**: Any user sends a video link in a group where the bot is a member, and the bot replies to that message with the downloaded video.

**Independent Test**: Add the bot to a group, send a valid video link, and verify the bot replies with the downloaded video.

### Implementation for User Story 2

- [x] T016 [US2] Implement group chat message handler in `src/bot/handlers/group.py`: filter with `filters.ChatType.GROUP | filters.ChatType.SUPERGROUP`; no whitelist check (open to all members); extract URL via url_parser; if no URL found → silently ignore (no response per FR-011); if URL found → send "Downloading..." reply; acquire download queue; extract metadata and validate; download video; `send_video()` with `reply_to_message_id` and `supports_streaming=True`; handle all error types with localized messages; clean up temp file in finally block
- [x] T017 [US2] Register group chat MessageHandler in `src/bot/__main__.py`

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 — Inline Mode Download (Priority: P3)

**Goal**: A whitelisted user types `@botname <link>` in any chat and receives an inline result with the downloaded video to share.

**Independent Test**: In any chat, type `@botname` followed by a valid video link and verify the bot returns an inline result with the downloadable video.

### Implementation for User Story 3

- [x] T018 [US3] Implement inline query handler in `src/bot/handlers/inline.py`: manually check `user_id` against whitelist (non-whitelisted → return empty results); parse query text via url_parser; if no valid URL → return `InlineQueryResultArticle` with help_inline message; if valid URL → acquire download queue; extract metadata and validate; download video; return `InlineQueryResultCachedVideo` or upload and return `InlineQueryResultVideo`; on validation errors (too long, too large, private, etc.) → return `InlineQueryResultArticle` with localized error description; set `cache_time=0`; clean up temp file
- [x] T019 [US3] Register InlineQueryHandler in `src/bot/__main__.py`

**Checkpoint**: All three user stories independently functional

---

## Phase 6: Logging & Observability

**Purpose**: Structured logging and metrics for operational visibility. Per constitution Development Standards, all external API calls MUST be observable. Per research D-007, structlog with contextvars provides per-request context binding with JSON output in production.

- [x] T020 [P] Create structlog configuration module in `src/bot/logging.py`: define processor chain (timestamper, add_log_level, StackInfoRenderer, format_exc_info, JSONRenderer if LOG_JSON else ConsoleRenderer); integrate contextvars for per-request binding; configure stdlib logging to route through structlog; update `src/bot/__main__.py` to call this module's `setup_logging(settings)` instead of inline structlog config
- [x] T021 [P] Add per-request context binding in all handlers (`src/bot/handlers/private.py`, `src/bot/handlers/group.py`, `src/bot/handlers/inline.py`): at request start bind request_id (UUID4), user_id, chat_id, chat_type, and language to structlog context using `structlog.contextvars.bind_contextvars()`; clear context in finally block; log `request.received` event at entry and `request.completed` event with total_duration_ms at exit
- [x] T022 [P] Add request lifecycle logging in `src/bot/services/downloader.py`: log `download.metadata_extracted` (with duration_ms, video_duration_s, file_size_bytes, platform), `download.started`, `download.completed` (with duration_ms, file_size_bytes, output_format), and `download.failed` (with error_type, stage, duration_ms) as structured events; include platform and URL in all events
- [x] T023 [P] Add external API call logging for Telegram Bot API calls in handlers (`src/bot/handlers/private.py`, `src/bot/handlers/group.py`, `src/bot/handlers/inline.py`): log `telegram.send_video` and `telegram.send_message` calls with duration_ms and success/failure; log `telegram.send_chat_action` calls; ensure all yt-dlp errors in `src/bot/services/downloader.py` log the classified error_type (private, rate_limited, not_video, download_error) with platform context
- [x] T024 [P] Add operational metrics events in `src/bot/services/queue.py` and `src/bot/services/downloader.py`: emit `queue.acquired` (with current_active count), `queue.released`, `queue.full` (with queue_depth) structured log events in queue.py; emit `metrics.download` summary event in downloader.py on completion with platform, success (bool), duration_ms, file_size_bytes — these JSON log events enable external monitoring via log aggregation
- [x] T025 [P] Add startup and health logging in `src/bot/__main__.py`: log `bot.starting` event with configured settings (redact BOT_TOKEN), allowed_user_ids count, max_concurrent_downloads, log_level; log `bot.ready` after polling starts; log `bot.shutdown` on graceful exit; log `bot.error` for unhandled exceptions with full context

---

## Phase 7: Polish & Validation

**Purpose**: Final validation and cross-cutting improvements

- [x] T026 Run quickstart.md end-to-end validation: verify `uv sync` installs cleanly, `uv run python -m bot` starts without errors (with valid .env), `uv run ruff check src/` passes, `uv run mypy src/` passes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phases 3–5)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Logging & Observability (Phase 6)**: Depends on all user stories being complete (modifies handler and service files)
- **Polish & Validation (Phase 7)**: Depends on Phase 6 being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — No dependencies on other stories
- **User Story 2 (P2)**: Can start after Phase 2 — Shares services with US1 but is independently testable
- **User Story 3 (P3)**: Can start after Phase 2 — Shares services with US1/US2 but is independently testable

### Within Each User Story

- Handler implementation before handler registration
- Core message handling before command handlers (US1)
- Each story is complete before moving to next priority

### Parallel Opportunities

- Phase 1: T003, T004, T005 can run in parallel
- Phase 2: T006, T007, T008 can run in parallel; then T010, T011 can run in parallel
- Once Phase 2 completes, all three user stories can start in parallel
- Phase 6: T020, T021, T022, T023, T024, T025 can all run in parallel (different files or non-overlapping concerns)

---

## Parallel Example: Phase 2 (Foundational)

```text
# First wave — no interdependencies:
Task T006: "Implement Settings class in src/bot/config.py"
Task T007: "Create enums and VideoRequest in src/bot/models/request.py"
Task T008: "Implement EN/RU messages in src/bot/locales/messages.py"

# Second wave — depend on first wave:
Task T009: "Implement URL parser in src/bot/services/url_parser.py"
Task T010: "Implement downloader in src/bot/services/downloader.py"
Task T011: "Implement queue in src/bot/services/queue.py"

# Third wave — depends on above:
Task T012: "Create bot entry point in src/bot/__main__.py"
```

## Parallel Example: User Stories (after Phase 2)

```text
# All three stories can launch in parallel:
Developer A: T013 → T014 → T015 (User Story 1)
Developer B: T016 → T017 (User Story 2)
Developer C: T018 → T019 (User Story 3)
```

## Parallel Example: Logging & Observability (Phase 6)

```text
# All logging tasks target different files or non-overlapping concerns:
Task T020: "Create structlog configuration module in src/bot/logging.py"
Task T021: "Add per-request context binding in handlers"
Task T022: "Add request lifecycle logging in downloader"
Task T023: "Add external API call logging in handlers and downloader"
Task T024: "Add operational metrics events in queue and downloader"
Task T025: "Add startup and health logging in __main__.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Send a real TikTok/YouTube/Instagram link to the bot in a private chat
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test in private chat → Deploy (MVP!)
3. Add User Story 2 → Test in group chat → Deploy
4. Add User Story 3 → Test inline mode → Deploy
5. Logging & Observability → Structured logging, metrics events → Deploy
6. Polish & Validation → Quickstart validation → Final deploy

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All temporary video files MUST be cleaned up (finally blocks in handlers)
- Whitelist applies to private chat + inline mode only; group chats are open
