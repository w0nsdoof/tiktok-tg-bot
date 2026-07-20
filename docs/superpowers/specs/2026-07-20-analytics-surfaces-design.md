# Analytics Surfaces — Design

**Date:** 2026-07-20
**Status:** Approved
**Sub-project:** C of 3 (A = analytics data layer, live 2026-07-20, see
`2026-07-20-analytics-data-layer-design.md`; B = Grafana/VictoriaMetrics/Alloy stack,
live 2026-07-20, see `~/petprojects/docs/grafana-one-pane-observability.md`).
Closes item 2 of `~/petprojects/docs/monitoring-follow-ups.md`.

## Goal

Surface the analytics that sub-project A now captures: a provisioned Grafana dashboard
reading the `tiktokbot` Postgres DB (global/admin view), and `/stats` + `/top` bot
commands (per-user view in Telegram). Both in this iteration.

## Decisions (from brainstorm, 2026-07-20)

- Scope: **both surfaces** — Grafana dashboard and bot commands, one iteration.
- Bot data path: **direct SQL from the bot** through the existing `Analytics` asyncpg
  pool (Approach 1). Rejected: Grafana deep-links (Authelia-gated, useless to
  whitelisted users), separate analytics HTTP API (fourth moving part, YAGNI).
- `/stats`: personal stats for any whitelisted user; **`/stats all`** adds the global
  view, admin-only.
- `/top`: **subcommand style** — `/top tags`, `/top creators`, `/top #tag`; bare or
  unrecognized argument shows usage help.
- Dashboard: all four panel groups (usage & errors, content tops, users, performance).
- Grafana connects as a **dedicated read-only role** `tiktokbot_ro`, never as the
  bot's read-write user.
- Commands are private-chat + whitelist only; groups stay download-only.

## 1. Infra — read-only Postgres access for Grafana

- New role `tiktokbot_ro`, password from `TIKTOKBOT_RO_PASSWORD`:

  ```sql
  CREATE ROLE tiktokbot_ro LOGIN PASSWORD '<pw>';
  GRANT CONNECT ON DATABASE tiktokbot TO tiktokbot_ro;
  -- in DB tiktokbot:
  GRANT USAGE ON SCHEMA public TO tiktokbot_ro;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO tiktokbot_ro;
  ALTER DEFAULT PRIVILEGES FOR ROLE tiktokbot IN SCHEMA public
      GRANT SELECT ON TABLES TO tiktokbot_ro;
  ```

- Created **manually via psql on the live server** (initdb scripts only run on a fresh
  volume — same procedure as the `tiktokbot` user, 2026-07-20). Mirrored in the
  postgres repo (`~/petprojects/postgres`): initdb script + `TIKTOKBOT_RO_PASSWORD`
  in compose env, for fresh-volume parity. The compose change recreates the postgres
  container on next `deploy-postgres` (brief blip for miniflux/linkding/kurakkorpe/bot)
  — **owner times that ride-along; not needed for this feature to work.**
- Monitoring repo: new `grafana/provisioning/datasources/tiktokbot.yml` — type
  `postgres`, uid **`tiktokbot`**, host `postgres:5432`, database `tiktokbot`, user
  `tiktokbot_ro`, `sslmode: disable` (internal `db` network only), password via env
  interpolation from the server-side monitoring `.env` (non-numeric secret — safe per
  the provisioning gotcha in `~/vault/petprojects/monitoring.md`). Grafana compose
  passes the env var through.
- No network changes (grafana already joins `db`), no Caddy changes, no DNS changes.

## 2. Grafana dashboard

One provisioned JSON: `grafana/dashboards/tiktok-bot-analytics.json`, picked up by the
existing dashboards provider. All panels query datasource uid `tiktokbot` with
`$__timeFilter(ts)` so the dashboard time picker works. Four rows:

- **Usage & errors** — downloads over time stacked by `status`; splits by `platform`,
  `output_format`, `chat_type`; error-rate stat over the selected range.
- **Content tops** — tables: top hashtags (`unnest(hashtags)` over videos joined to
  successful events in range), top creators by event count, top videos by `like_count`.
- **Users** — per-user event counts (bare Telegram IDs — the DB stores no usernames;
  acceptable at this user count), active users per week.
- **Performance** — `duration_ms` p50/p95 by platform, avg/max `file_size_bytes`.

## 3. Bot read layer — `src/bot/services/stats.py`

- `StatsService` owning the **read** queries, reusing the pool from `Analytics`
  (which gains a `pool` accessor returning its asyncpg pool, `None` in disabled
  mode; write path untouched).
- Methods: `user_stats(user_id)`, `global_stats()`, `top_tags(limit)`,
  `top_creators(limit)`, `top_videos_for_tag(tag, limit)`.
- "Top" queries count **successful** (`status = 'ok'`) events only; `/stats` reports
  total requests and successful downloads as separate numbers.
- Reads use `command_timeout=5` seconds.
- **Disabled mode** (no `ANALYTICS_DSN`): all methods signal unavailability; handlers
  reply with a localized "stats unavailable" message. No connection attempted.

## 4. Bot commands — `src/bot/handlers/stats.py`

- **`/stats`** (private + whitelist filter): the caller's totals — requests,
  successful downloads, top platforms, top 5 creators, top 5 hashtags (events joined
  to `videos` on `(platform, video_id)`), date of first use.
- **`/stats all`**: admin check inside the handler (via `user_store`); global
  equivalents + top users by download count. Non-admins get the personal reply.
- **`/top`** argument parsing: `tags` → top 10 hashtags with counts; `creators` →
  top 10 creators by successful downloads; argument starting with `#` → top 5 videos
  where `$1 = ANY(hashtags)` ranked `like_count DESC NULLS LAST` (title, author,
  likes, URL); anything else (including bare `/top`) → usage help. Input tags are
  lowercased and stripped of `#` before querying — A stores hashtags lowercased.
- Registered in `__main__.py` with the existing `private & whitelist` pattern.
- EN/RU strings for every reply in `locales/messages.py`; `/help` text updated to
  mention both commands.

## 5. Error handling

- Any query/pool failure → `log.warning` + localized "stats unavailable" reply.
  Commands never raise into the framework.
- Empty results (fresh DB, unknown hashtag) → localized "no data yet" replies.

## 6. Testing

Unit tests (no Postgres, fake pool — same approach as sub-project A's tests):

- `/top` argument parsing: `tags`, `creators`, `#tag`, `#TAG` casing, bare, junk.
- Reply assembly for `/stats`, `/stats all`, and each `/top` form — empty and
  populated datasets.
- Admin gating: `/stats all` from non-admin returns personal stats.
- Disabled mode: commands reply "unavailable", no connection attempted.

Manual post-deploy: send one link, run `/stats`, `/stats all`, each `/top` form;
open the dashboard and check all four rows render.

## 7. Rollout order

1. Server: create `tiktokbot_ro` role + grants via psql (root/host op).
2. Monitoring repo: datasource YAML + dashboard JSON + `TIKTOKBOT_RO_PASSWORD` in the
   server-side `.env` → `make deploy-monitoring` (grafana recreate — harmless, no
   user sessions in grafana itself).
3. Bot repo: stats service + handlers + locales + tests → `make deploy-bot`.
4. Postgres repo parity change deploys whenever the container is next recreated
   (owner-timed).
5. Close out item 2 in `~/petprojects/docs/monitoring-follow-ups.md`.

## Non-goals

- Trending / personal recap pushes (`ideas.md`) — the dashboard's time picker plus
  `/top` cover discovery for now; recaps are a possible later iteration.
- Username resolution for the Users panels — the DB stores only Telegram IDs.
- HTTP API for analytics — rejected in brainstorm.
- Whitelist migration to Postgres — unchanged from A.
- Grafana alerting on bot SQL — nothing to alert on yet.
