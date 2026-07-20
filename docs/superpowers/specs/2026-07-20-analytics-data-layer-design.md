# Analytics Data Layer — Design

**Date:** 2026-07-20
**Status:** Approved
**Sub-project:** A of 3 (A = this data layer; B = Grafana/VictoriaMetrics/Alloy observability stack, see `~/petprojects/docs/grafana-one-pane-observability.md`; C = analytics surfaces — Grafana dashboards + `/stats`/`/top` bot commands)

## Goal

Record every download request — success and failure — plus full normalized video
metadata into the shared Postgres, so that rich content analytics (per-user stats,
hashtag index, creator leaderboards, trending — see `docs/ideas.md`) can be built
on top. Capture starts now; surfaces (B, C) come later. No historical backfill is
possible, so every day without capture is data lost.

## Decisions (from brainstorm, 2026-07-20)

- Scope: rich content analytics (full `ideas.md` vision), not just operational counters.
- Consumption: bot commands **and** web dashboards, both deferred to sub-project C.
- Visualization layer: Grafana (one pane for the whole box, replacing Beszel) — sub-project B.
- Storage: **shared Postgres** (`postgres` container, internal `db` network), not SQLite —
  Grafana reads Postgres as a core datasource; SQLite would need a community plugin plus
  volume-mount coupling between bot and Grafana containers.
- Write path: **fire-and-forget** — analytics must never slow or break a download.
  Postgres-down means a few lost events; acceptable.
- Build order: A first (this spec), then B, then C.

## 1. Storage

New database `tiktokbot` (dedicated user, password via env) on the shared Postgres 16.

```sql
CREATE TABLE IF NOT EXISTS videos (
    platform        text        NOT NULL,
    video_id        text        NOT NULL,
    url             text        NOT NULL,
    title           text,
    description     text,
    hashtags        text[]      NOT NULL DEFAULT '{}',
    author_handle   text,
    author_name     text,
    duration_s      integer,
    view_count      bigint,
    like_count      bigint,
    comment_count   bigint,
    share_count     bigint,     -- TikTok only
    save_count      bigint,     -- TikTok only
    track           text,       -- music title (TikTok always, YT music videos)
    artist          text,
    uploaded_at     timestamptz,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, video_id)
);

CREATE TABLE IF NOT EXISTS download_events (
    id              bigserial   PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    user_id         bigint      NOT NULL,
    chat_type       text        NOT NULL,   -- private | group | inline
    platform        text        NOT NULL,
    video_id        text,                   -- NULL when metadata extraction failed
    url             text        NOT NULL,
    output_format   text        NOT NULL,   -- default | audio | images
    status          text        NOT NULL,   -- ok | too_long | too_large | private |
                                            -- platform_down | not_video | download_error |
                                            -- no_audio | not_slideshow | unknown_error
    duration_ms     integer,                -- total processing time
    file_size_bytes bigint
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON download_events (ts);
CREATE INDEX IF NOT EXISTS idx_events_user ON download_events (user_id);
```

- `videos` is **upserted** on every request: engagement counts overwrite to the latest
  snapshot, `last_seen_at` refreshes, `first_seen_at` is preserved.
- **No FK** from `download_events.video_id` to `videos`: with fire-and-forget writes the
  video upsert isn't guaranteed to land before the event insert, and a dangling event is
  better than a rejected one.
- Limit rejections (`too_long`, `too_large`, `not_slideshow`) are events too — they are
  usage even though nothing was sent.

## 2. Metadata capture — `VideoInfo`

`_extract_metadata_sync()` already calls `extract_info(download=False)` and receives the
full yt-dlp info dict on **every** request path (private, group, inline all call
`extract_metadata()` first). Zero extra network calls needed.

- New model `src/bot/models/video_info.py`: normalized `VideoInfo` dataclass exactly as
  proposed in `docs/research/yt-dlp-metadata.md` (per-platform field mapping table there
  is the source of truth), including the `extract_hashtags()` helper (YouTube: `tags`
  list; TikTok/Instagram: regex `#(\w+)` over `description`; lowercased, sorted, deduped).
- `VideoMetadata` gains an `info: VideoInfo | None` field, populated by
  `_extract_metadata_sync()` from the info dict. `None` when extraction fails.

## 3. Write path — `src/bot/services/analytics.py`

- `Analytics` class owning an asyncpg pool (`min_size=0`, `max_size=2`), created from
  `settings.analytics_dsn`.
- `ensure_schema()` runs the `CREATE TABLE IF NOT EXISTS` DDL at startup.
- `record(event: DownloadEvent, video: VideoInfo | None)` spawns a background asyncio
  task; the task upserts `videos` (if `video` present) then inserts the event. Any
  exception → `log.warning("analytics.write_failed", ...)`, event dropped. Pool
  acquisition failures self-heal on the next event (no circuit breaker needed).
- `close()` on shutdown.
- **Disabled mode:** if `ANALYTICS_DSN` is unset, `Analytics` is a no-op stub — local dev
  and tests run without Postgres. Bot behavior is byte-identical with analytics on or off.
- New dependency: `asyncpg`. No ORM, no migration framework — plain SQL matches project scale.
- Wiring: instantiated in `__main__.py`, stored in `context.bot_data["analytics"]`,
  `ensure_schema()` awaited before `run_polling()` (failure logs a warning, does not
  block startup).

## 4. Capture points

Both entry paths are restructured so **every** exit funnels through exactly one
`analytics.record(...)`:

- `process_request()` in `handlers/common.py` (covers private + group): track
  `status`/`video_id`/`file_size` in local outcome state; record in a `finally` block
  with total `duration_ms` measured from entry. `user_id` from `message.from_user`,
  `chat_type` from `message.chat.type` (mapped to `private`/`group`).
- `handle_inline_query()` in `handlers/inline.py`: same pattern, `chat_type="inline"`
  (it already measures `total_duration_ms` — reuse that). Inline has no format keywords,
  so its events always record `output_format="default"`.
- Early returns (limit rejections), `VideoDownloadError` handlers, and the catch-all
  `except Exception` (→ `status="unknown_error"`) all set outcome state instead of
  bypassing it. This is the only refactor of existing code.

## 5. Config & infra

- `Settings` gains `analytics_dsn: str | None = None` (env `ANALYTICS_DSN`, e.g.
  `postgresql://tiktokbot:<pw>@postgres:5432/tiktokbot`).
- **bot `docker-compose.yml`:** join the external `db` network **in addition to** the
  default bridge network (the bot needs outbound internet; attaching only `db` would
  drop the default network).
- **postgres repo** (`~/petprojects/postgres`, local-only git): add
  `initdb/` script creating `tiktokbot` DB + user from `TIKTOKBOT_DB_PASSWORD`, and the
  env var to its compose. Because initdb scripts only run on a fresh volume, the DB/user
  is **created manually via psql once** on the live server (same procedure as the
  kurakkorpe migration, 2026-07-12).
- **server bot `.env`:** add `ANALYTICS_DSN`. The repo is public — the DSN never appears
  in code or compose; `.env` stays git-ignored.
- Deploy: normal `make deploy-bot` (git pull + rebuild) after the DB exists.

## 6. Testing

Unit tests (no Postgres required):
- `VideoInfo` normalization per platform — fixtures built from the field tables in
  `docs/research/yt-dlp-metadata.md` (TikTok, YouTube Shorts, Instagram Reels).
- `extract_hashtags()` — tags list, description regex, mixed, dedup/casing.
- Disabled-mode stub: `record()` is a no-op, no connection attempted.
- Event assembly: with a fake pool, assert one event per exit path of
  `process_request()` (ok, each error type, limit rejection, unhandled exception) with
  correct `status`/`output_format`/`chat_type`.

Integration (manual, post-deploy): send one link of each platform/format, check rows via psql.

## Non-goals

- Grafana/VictoriaMetrics/Alloy stack and retiring Beszel → sub-project B
  (`~/petprojects/docs/grafana-one-pane-observability.md`).
- Dashboards, `/stats`, `/top #tag`, trending, recaps → sub-project C.
- Whitelist migration to Postgres — `allowed_users.json` stays as is.
- Historical backfill — nothing was recorded before this feature.
- Durable event spool / delivery guarantees — fire-and-forget is the accepted trade-off.
