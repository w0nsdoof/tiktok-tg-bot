# Research: Output Format Selection

**Feature**: 002-output-format-selection | **Date**: 2026-03-12

## R1: yt-dlp Audio-Only Extraction

### Decision
Use `format="bestaudio/best"` combined with `FFmpegExtractAudio` postprocessor (`preferredcodec="m4a"`) for all audio extraction. This ensures Telegram music player compatibility.

### Rationale
- TikTok videos and Instagram Reels only provide muxed MP4 streams (no separate audio-only streams). `bestaudio` alone finds no match and falls back to `best`, which downloads the full video. The `FFmpegExtractAudio` postprocessor is essential to strip the video track.
- TikTok slideshows and YouTube Shorts do have native audio-only streams, but using the postprocessor uniformly simplifies the code path and guarantees consistent output format.
- `preferredcodec="m4a"` chosen because: (a) Telegram's `send_audio` only renders the music player for `.mp3` and `.m4a` files; (b) TikTok/Instagram sources use AAC codec, so remuxing to m4a is lossless (no re-encoding); (c) YouTube sources use opus, which gets converted to m4a (slight quality loss, but universal Telegram compatibility).
- `preferredcodec="best"` was considered but rejected because it would produce `.opus`/`.webm` files from YouTube sources, which Telegram renders as generic documents instead of the music player.

### Alternatives Considered
- **`preferredcodec="best"` (keep native format)**: Fastest, no re-encoding. Rejected because Telegram only shows music player for mp3/m4a — opus/webm would render as file attachments, breaking UX consistency.
- **`preferredcodec="mp3"`**: Universal compatibility. Rejected because it always re-encodes (lossy + slower), and m4a handles the common case (AAC source) losslessly.
- **No postprocessor (just `format="bestaudio/best"`)**: Works for slideshows/YouTube but fails for TikTok videos and Instagram Reels (downloads full muxed video instead of audio-only).

## R2: Format Keyword Parsing Strategy

### Decision
Create a dedicated `format_parser.py` service with a `parse_output_format(text: str, url: str) -> OutputFormat` function. It strips the URL from the text, then checks remaining words against keyword sets. Case-insensitive matching. Returns the first recognized keyword's format category.

### Rationale
- Separating format parsing from URL parsing (different service) follows single-responsibility principle per Constitution §I.
- Stripping the URL first prevents false positives from URLs containing words like "photo" or "music" in path segments.
- Using sets for keyword lookup gives O(1) per-word matching.
- Case-insensitive: normalize the remaining text to lowercase before matching.
- First-keyword-wins: scan words left-to-right, return the first match (per spec edge case).

### Alternatives Considered
- **Regex-based matching**: More powerful but overkill for simple word matching. Harder to maintain the keyword list.
- **Combining with `extract_url()` in `url_parser.py`**: Would violate single responsibility. URL extraction and format detection are independent concerns.
- **Slash commands (e.g., `/audio`)**: More explicit, but spec requires natural keywords (low-friction interaction). Slash commands would also conflict with Telegram's command system.

## R3: Telegram Audio File Handling

### Decision
Use `message.reply_audio()` with `title` parameter for all audio output. Target m4a format. Provide `filename` parameter with a meaningful name.

### Rationale
- `reply_audio()` displays in Telegram's music player with title, performer, duration, and play/pause controls — appropriate for music/audio from TikTok/YouTube.
- `reply_voice()` displays as a voice message bubble (waveform) — inappropriate for music tracks.
- Telegram accepts mp3 and m4a for music player display. Other formats (opus, ogg, webm) render as generic file attachments.
- The `title` parameter controls what's shown in the music player. Currently used for slideshow audio already.
- The `filename` parameter controls the download filename for users. Providing a meaningful name (e.g., based on video title) improves UX.

### Alternatives Considered
- **`reply_document()`**: Sends as a generic file. No music player. Rejected for poor UX.
- **`reply_voice()`**: Voice message bubble. No title/performer support. Wrong semantics for music.

## R4: Images-Only from Slideshow

### Decision
Reuse the existing `download_slideshow()` function and skip sending audio in the handler. No changes to the downloader needed.

### Rationale
- `download_slideshow()` already returns a `SlideshowResult` with separate `image_paths` and `audio_path`. The handler can simply not send the audio file.
- Downloading audio unnecessarily (then discarding it) is wasteful but keeps the code simple. The audio download is fast (~1-2s) and the complexity of a conditional download path isn't justified.
- Actually, on second thought: we should skip the audio download entirely when images-only is requested. The `download_slideshow` function downloads audio via a separate yt-dlp call, so we can add an `include_audio` parameter to skip that step. This saves ~1-2s and avoids unnecessary network calls.

### Alternatives Considered
- **Always download everything, discard in handler**: Simpler code but wasteful. Rejected because the audio download is a separate explicit step in `_download_slideshow_sync` that's easy to skip.
- **New `download_images_only()` function**: Unnecessary duplication. Adding a parameter to the existing function is cleaner.

## R5: Error Handling for Incompatible Format Requests

### Decision
Handle incompatible format requests (e.g., "images" on a regular video) in the handler layer with a user-friendly error message, before attempting any download.

### Rationale
- Checking compatibility early (after metadata extraction, before download) avoids wasting bandwidth and user time.
- Two incompatible cases exist: (1) requesting images from a non-slideshow video; (2) requesting audio from content with no audio track (rare, handle at download error level).
- Case 1 is detectable from `metadata.is_slideshow` — no download needed.
- Case 2 is rare and detected by yt-dlp/FFmpeg errors — handle in the existing error path.

### Alternatives Considered
- **Silently fall back to default behavior**: Less confusing for the user? Rejected because it violates spec FR-005 (must inform user) and could be confusing ("I asked for images but got a video").
- **Attempt download and catch error**: Works for case 2 (no audio) but wasteful for case 1 (images from video). Better to check early.

## R6: Handler Refactoring Approach

### Decision
Extract a shared `_process_request()` helper used by both private and group handlers, rather than duplicating format logic in both.

### Rationale
- Private and group handlers currently have nearly identical download/send logic (only differing in `reply_to_message_id` and silent-ignore behavior for non-URL messages). Adding format selection would triple the duplication.
- A shared helper reduces code and ensures both handlers behave identically for format selection.
- The helper accepts a `reply_to` parameter to handle the group chat threading difference.
- Per Constitution §I: "Duplicated logic MUST be extracted; copy-paste reuse is forbidden."

### Alternatives Considered
- **Duplicate format logic in both handlers**: Fastest to implement but violates Constitution §I (no copy-paste reuse).
- **Merge into a single handler**: Would complicate the Telegram handler registration (different filters for private vs group). Rejected.
