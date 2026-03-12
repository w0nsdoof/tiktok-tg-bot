# Feature Specification: Output Format Selection

**Feature Branch**: `002-output-format-selection`
**Created**: 2026-03-12
**Status**: Draft
**Input**: User description: "functionality to specify in which format i want output. Like sending a link and by default it operates same way, but if for example sound (or mp3) from a video or if its slides from tiktok - images/pics/png."

## Clarifications

### Session 2026-03-12

- Q: Should format keywords also work in Russian (in addition to English), given the bot already supports EN/RU localization? → A: Yes — support both English and Russian keywords (e.g., "аудио"/"звук" for audio, "картинки"/"фото" for images).
- Q: Should the help message be updated to inform users about format keywords? → A: Yes — update the help/start message to list available format keywords with brief examples.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Default Link Behavior Unchanged (Priority: P1)

A user sends a link to the bot without any format modifier. The bot behaves exactly as it does today: videos are downloaded as MP4, slideshows are sent as images with audio.

**Why this priority**: This is the existing core behavior and must not break. Every current user depends on it.

**Independent Test**: Send any supported link (TikTok, YouTube Shorts, Instagram Reel) without format keywords and verify the current behavior is preserved.

**Acceptance Scenarios**:

1. **Given** a user sends a TikTok video link with no format keyword, **When** the bot processes the link, **Then** the bot downloads and sends the video as MP4 (current behavior).
2. **Given** a user sends a TikTok slideshow link with no format keyword, **When** the bot processes the link, **Then** the bot sends images and audio separately (current behavior).
3. **Given** a user sends a YouTube Shorts or Instagram Reel link with no format keyword, **When** the bot processes the link, **Then** the bot downloads and sends the video as MP4 (current behavior).

---

### User Story 2 - Extract Audio from Video (Priority: P2)

A user wants only the audio track from a video. They send a link along with a format keyword (e.g., "audio", "mp3", or "sound") and the bot extracts and sends just the audio file.

**Why this priority**: Audio extraction is the most commonly requested alternative format. Users often want songs or sounds from TikTok/YouTube without the video.

**Independent Test**: Send a TikTok video link with the keyword "audio" and verify the bot sends an audio file instead of a video.

**Acceptance Scenarios**:

1. **Given** a user sends a TikTok video link with the keyword "audio", **When** the bot processes the message, **Then** the bot extracts the audio track and sends it as an audio file.
2. **Given** a user sends a YouTube Shorts link with the keyword "mp3", **When** the bot processes the message, **Then** the bot extracts the audio and sends it as an audio file.
3. **Given** a user sends a video link with the keyword "sound", **When** the bot processes the message, **Then** the bot extracts the audio and sends it as an audio file.
4. **Given** a user sends a link to a video that has no audio track, **When** the bot processes the message with an audio keyword, **Then** the bot informs the user that no audio is available.

---

### User Story 3 - Extract Images from Slideshow (Priority: P3)

A user wants only the images from a TikTok slideshow, without the accompanying audio. They send a slideshow link with a format keyword (e.g., "images", "pics", "photos", or "png") and the bot sends only the images.

**Why this priority**: Provides granular control over slideshow output. Currently slideshows always send both images and audio; some users only want the pictures.

**Independent Test**: Send a TikTok slideshow link with the keyword "images" and verify the bot sends only images without audio.

**Acceptance Scenarios**:

1. **Given** a user sends a TikTok slideshow link with the keyword "images", **When** the bot processes the message, **Then** the bot sends only the images without the audio file.
2. **Given** a user sends a TikTok slideshow link with the keyword "pics", **When** the bot processes the message, **Then** the bot sends only the images without the audio file.
3. **Given** a user sends a non-slideshow video link with the keyword "images", **When** the bot processes the message, **Then** the bot informs the user that the content is a video, not a slideshow, and no images can be extracted.

---

### User Story 4 - Extract Audio from Slideshow (Priority: P3)

A user wants only the background audio from a TikTok slideshow. They send a slideshow link with a format keyword (e.g., "audio", "mp3", "sound") and the bot sends only the audio.

**Why this priority**: Complements the images-only option. Some users want just the song from a slideshow.

**Independent Test**: Send a TikTok slideshow link with the keyword "audio" and verify the bot sends only the audio file without images.

**Acceptance Scenarios**:

1. **Given** a user sends a TikTok slideshow link with the keyword "audio", **When** the bot processes the message, **Then** the bot sends only the audio file without the images.
2. **Given** a user sends a TikTok slideshow link with the keyword "sound", **When** the bot processes the message, **Then** the bot sends only the audio without images.

---

### Edge Cases

- What happens when a user sends multiple format keywords in one message (e.g., "audio images")? The bot uses the first recognized keyword.
- What happens when a user sends an unrecognized format keyword? The bot ignores it and uses default behavior.
- What happens when format keywords appear as part of a URL or unrelated text? The bot only recognizes format keywords outside of the URL itself.
- What happens when a user requests audio from a very short video (e.g., 1-2 seconds)? The bot still extracts and sends whatever audio is available.
- How does format selection work in group chats? Same behavior as private chats — format keywords in the same message as the link are recognized.
- How does format selection work in inline mode? Format keywords are not supported in inline mode; inline mode uses default behavior only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST continue to download and send content in the default format (MP4 for videos, images+audio for slideshows) when no format keyword is present in the message.
- **FR-002**: System MUST recognize audio format keywords in English ("audio", "mp3", "sound") and Russian ("аудио", "звук", "музыка") as a request to extract only the audio track from any video or slideshow content.
- **FR-003**: System MUST recognize image format keywords in English ("images", "pics", "photos", "png") and Russian ("картинки", "фото", "изображения") as a request to extract only the images from slideshow content.
- **FR-004**: System MUST send audio files with the content title as the audio title metadata when extracting audio.
- **FR-005**: System MUST inform the user with a clear message when the requested format is incompatible with the content type (e.g., requesting images from a regular video).
- **FR-006**: Format keywords MUST be case-insensitive (e.g., "Audio", "AUDIO", "audio" all work).
- **FR-007**: Format keywords MUST be detected only outside of the URL portion of the message text.
- **FR-008**: System MUST support format selection in both private and group chat contexts.
- **FR-009**: System MUST use the first recognized format keyword when multiple keywords appear in a single message.
- **FR-010**: System MUST fall back to default behavior when format keywords are used in inline mode.
- **FR-011**: System MUST respect the same file size and duration limits for format-selected downloads as for default downloads.
- **FR-012**: The help/start message MUST be updated to list available format keywords with brief usage examples, in both English and Russian.

### Key Entities

- **Format Keyword**: A recognized word in the user's message that indicates the desired output format. Belongs to a format category (audio or images).
- **Output Format**: The resolved format to use for downloading and sending content. One of: default (current behavior), audio-only, or images-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can request audio extraction by including a format keyword in their message, and receive an audio file within the same time frame as a standard video download.
- **SC-002**: Users can request images-only from slideshows and receive only images without audio, completing in less time than the current full slideshow flow.
- **SC-003**: Existing users who send links without format keywords experience no change in behavior or response time.
- **SC-004**: Format keywords are correctly recognized in 100% of messages where they appear as standalone words outside of URLs.

## Assumptions

- Format keywords are simple standalone words in the message text (not slash commands or special syntax), keeping the interaction natural and low-friction.
- Audio files are extracted as `.m4a` via yt-dlp's `FFmpegExtractAudio` postprocessor. AAC sources (TikTok, Instagram) are remuxed losslessly; opus sources (YouTube) are transcoded to m4a for Telegram music player compatibility. The keyword "mp3" is a user-friendly alias for "audio extraction," not a format guarantee.
- Inline mode does not support format selection due to the limited input context (query string only). This can be revisited in a future iteration.
- The maximum of 3 concurrent downloads limit applies equally to format-selected downloads.
