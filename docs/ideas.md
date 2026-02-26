# Ideas

## Video Analytics & Tracking

**Research**: [yt-dlp metadata fields](research/yt-dlp-metadata.md)

Track metadata for every video downloaded through the bot. Store per-user download history with full video info (author, hashtags, engagement stats, platform, duration).

Possible features:

- **Per-user stats**: what platforms they use most, total videos downloaded, favorite creators
- **Hashtag index**: build a hashtag-to-video mapping from all downloads across users
- **Top N by hashtag**: endpoint or bot command that returns the top 5 most-liked/viewed videos for a given hashtag (e.g. `/top #fyp`)
- **Trending**: surface hashtags or creators that appear frequently across recent downloads
- **Creator leaderboard**: most downloaded creators across all users
- **Personal feed recap**: weekly/monthly summary of a user's download patterns (top hashtags, top creators, total watch time)

Would require adding persistent storage (SQLite or Postgres) and a `VideoInfo` model to capture the normalized metadata on every download. Could expose the data via bot commands first (`/stats`, `/top #tag`) and optionally as an HTTP API later.
