# Feature Specification: Video Download Bot

**Feature Branch**: `001-video-download-bot`
**Created**: 2026-02-24
**Status**: Draft
**Input**: User description: "A Telegram bot that takes a link
(YouTube, TikTok, Instagram Reels) and outputs the downloaded
video. Focused on short videos with a duration cap. Supports
direct chat messages and inline mode."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Direct Chat Download (Priority: P1)

A user opens a private chat with the bot and sends a link to a
short video (TikTok, YouTube Shorts, or Instagram Reel). The bot
recognizes the link, downloads the video, and sends it back as a
playable video message in the same chat.

**Why this priority**: This is the core value proposition — the
simplest and most common use case. Without this, the bot has no
purpose. A single user in a private chat is the easiest flow to
build and test.

**Independent Test**: Send a valid TikTok/YouTube/Instagram link
to the bot in a private chat and verify a video file is returned.

**Acceptance Scenarios**:

1. **Given** a user in a private chat with the bot,
   **When** the user sends a valid TikTok video link,
   **Then** the bot downloads the video and sends it as a
   playable video message within 30 seconds.

2. **Given** a user in a private chat with the bot,
   **When** the user sends a valid YouTube Shorts link,
   **Then** the bot downloads the video and sends it as a
   playable video message within 30 seconds.

3. **Given** a user in a private chat with the bot,
   **When** the user sends a valid Instagram Reel link,
   **Then** the bot downloads the video and sends it as a
   playable video message within 30 seconds.

4. **Given** a user in a private chat with the bot,
   **When** the user sends a link to a video longer than 5
   minutes,
   **Then** the bot replies with a friendly message explaining
   it only supports short videos (under 5 minutes) and does
   not attempt the download.

5. **Given** a user in a private chat with the bot,
   **When** the user sends a message that is not a recognized
   link,
   **Then** the bot replies with a help message explaining
   supported platforms and usage.

---

### User Story 2 - Group Chat Download (Priority: P2)

A user sends a video link in a Telegram group where the bot is a
member. The bot detects the link and replies with the downloaded
video in the same group chat.

**Why this priority**: Group chats are where sharing happens most.
This extends the P1 functionality to a social context, making the
bot useful for its most natural use case — sharing videos with
friends.

**Independent Test**: Add the bot to a group, send a valid video
link, and verify the bot replies with the downloaded video.

**Acceptance Scenarios**:

1. **Given** the bot is a member of a group chat,
   **When** a user sends a valid TikTok/YouTube/Instagram link
   in the group,
   **Then** the bot replies to that message with the downloaded
   video.

2. **Given** the bot is a member of a group chat,
   **When** a user sends a video link longer than 5 minutes,
   **Then** the bot replies with the duration limit message.

3. **Given** the bot is a member of a group chat,
   **When** a user sends a non-link message,
   **Then** the bot ignores it (no response).

---

### User Story 3 - Inline Mode Download (Priority: P3)

A user is in any Telegram chat (private, group, or channel) and
types `@botname <link>` in the message input field. The bot
processes the link and presents the downloaded video as an inline
result that the user can send into the current conversation.

**Why this priority**: Inline mode is a convenience feature that
lets users invoke the bot without it being a group member. It is
more complex to implement and depends on the core download logic
from P1 being solid first.

**Independent Test**: In any chat, type `@botname` followed by a
valid video link and verify the bot returns an inline result with
the downloadable video.

**Acceptance Scenarios**:

1. **Given** a user in any Telegram chat,
   **When** the user types `@botname <valid-link>` in the
   message field,
   **Then** the bot shows an inline result with a preview, and
   tapping it sends the downloaded video into the chat.

2. **Given** a user in any Telegram chat,
   **When** the user types `@botname <link-to-long-video>`,
   **Then** the bot shows an inline result indicating the video
   exceeds the duration limit.

3. **Given** a user in any Telegram chat,
   **When** the user types `@botname` with no link or an
   invalid link,
   **Then** the bot shows a help message as an inline result
   explaining supported platforms and usage format.

---

### Edge Cases

- What happens when the video is set to private or has been
  deleted? The bot MUST reply with a clear error: "This video
  is unavailable (private or deleted)."
- What happens when the platform is temporarily down or rate-
  limiting requests? The bot MUST reply: "Could not reach
  [platform] right now. Please try again in a few minutes."
- What happens when the video file exceeds Telegram's 50 MB
  upload limit? The bot MUST reply: "This video is too large
  to send via Telegram (over 50 MB)."
- What happens when the user sends multiple links at once?
  The bot MUST process only the first recognized link and
  ignore the rest.
- What happens when the same video is requested by multiple
  users simultaneously? The bot MUST handle concurrent
  requests without crashing or producing corrupted files.
- What happens when the concurrent download limit is reached?
  The bot MUST queue excess requests and notify the user
  (e.g., "Your request is queued, please wait...").
- What happens if the link is valid but points to a non-video
  page (e.g., a TikTok profile, YouTube channel)? The bot
  MUST reply: "This link doesn't point to a video. Please
  send a direct link to a video."
- What happens when a non-whitelisted user messages the bot
  in a private chat or uses inline mode? The bot MUST silently
  ignore the request (no response, no error message).
- What happens when a non-whitelisted user sends a link in a
  group chat? The bot MUST process it normally — group chats
  are open to all members.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept plain-text messages containing
  a single URL and extract the link automatically (no commands
  or prefixes required).
- **FR-002**: System MUST support links from TikTok (tiktok.com,
  vm.tiktok.com), YouTube (youtube.com/shorts, youtu.be), and
  Instagram Reels (instagram.com/reel, instagram.com/reels).
- **FR-003**: System MUST determine the video duration before
  downloading. Videos exceeding 5 minutes MUST be rejected with
  a user-friendly message.
- **FR-004**: System MUST download the video in the best
  available quality that fits within Telegram's 50 MB file size
  limit.
- **FR-005**: System MUST send the downloaded video as a native
  Telegram video message (not as a document/file attachment).
- **FR-006**: System MUST provide immediate feedback (e.g.,
  "Downloading your video...") upon receiving a valid link,
  before the download completes.
- **FR-007**: System MUST work in private chats (1-on-1 with
  the bot).
- **FR-008**: System MUST work in group chats where the bot is
  a member, replying to the message that contained the link.
- **FR-009**: System MUST support Telegram inline mode, allowing
  users to invoke the bot via `@botname <link>` from any chat.
- **FR-010**: System MUST reply with a help/usage message when
  the user sends an unrecognized message in a private chat.
- **FR-011**: System MUST silently ignore non-link messages in
  group chats (no spam).
- **FR-012**: System MUST handle errors gracefully with
  human-friendly messages (private videos, network errors,
  unsupported links, oversized files).
- **FR-013**: System MUST clean up temporary downloaded files
  after sending or upon failure (no disk space leaks).
- **FR-014**: System MUST restrict access to a configurable
  whitelist of allowed Telegram user IDs (stored in environment
  variable or config). In private chats and inline mode, messages
  from non-whitelisted users MUST be silently ignored. In group
  chats, the bot MUST respond to all members regardless of
  whitelist status.
- **FR-015**: System MUST support two languages: English and
  Russian. The bot MUST auto-detect the user's language from
  Telegram's `language_code` field and respond in the matching
  language. Default to English if the locale is unavailable or
  unsupported.

### Key Entities

- **Video Request**: Represents a user's download request;
  attributes include source platform, original URL, video
  duration, file size, and request status (pending, downloading,
  sending, completed, failed).
- **Supported Platform**: A recognized video source (TikTok,
  YouTube, Instagram); attributes include platform name, URL
  patterns for matching, and duration/size limits.

## Assumptions

- The 5-minute duration cap is a reasonable default for "short
  videos" and prevents downloading full-length content like
  podcasts or movies.
- Telegram's 50 MB bot upload limit applies (bots cannot send
  files larger than 50 MB without Telegram Premium on the
  receiving end; we target the standard limit).
- The bot restricts access to a configurable whitelist of
  allowed Telegram user IDs. Non-whitelisted users are ignored.
- The bot does not store or cache downloaded videos long-term;
  each request is a one-time download-and-send operation.
- The bot name/username will be configured via environment
  variables at deployment time.

## Clarifications

### Session 2026-02-24

- Q: How should the bot handle abuse prevention / access control? → A: Whitelist of allowed Telegram user IDs; non-whitelisted users are silently ignored.
- Q: What language(s) should the bot respond in? → A: Both English and Russian, auto-detected from user's Telegram locale.
- Q: Should whitelist apply in group chats? → A: No. Group chats are open to all members; whitelist only gates private chat and inline mode.
- Q: What happens when concurrent download limit is exceeded? → A: Queue excess requests and notify the user of queue status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users receive the downloaded video within 30
  seconds of sending a valid link for videos under 2 minutes
  in length.
- **SC-002**: 95% of valid short-video links from supported
  platforms result in a successful video delivery.
- **SC-003**: 100% of error scenarios (private video, long
  video, oversized file, network error) produce a clear,
  human-friendly error message — never a raw error or silence.
- **SC-004**: Users can successfully use inline mode
  (`@botname <link>`) to share downloaded videos in any chat.
- **SC-005**: The bot handles at least 10 concurrent download
  requests without degradation or failures. Excess requests
  are queued and the user is notified of the queue status.
