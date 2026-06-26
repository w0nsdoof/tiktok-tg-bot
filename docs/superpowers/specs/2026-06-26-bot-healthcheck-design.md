# tiktok-tg-bot — heartbeat healthcheck

**Date:** 2026-06-26
**Status:** approved design, pending implementation

## Problem

`tiktok-tg-bot` runs `python-telegram-bot` in **polling** mode with no HTTP port.
The container currently has **no `HEALTHCHECK`**, so Docker only knows whether the
main process exists. The real failure mode for a polling bot is a *wedged or
network-dead event loop while the process stays up* — invisible today. Beszel
shows the container as running; nothing flags that it has stopped serving.

## Goal

Detect "the polling loop is no longer alive" and surface it as Docker health
`unhealthy` (visible in `docker ps`, `docker inspect`, and Beszel's container view).

Non-goals: traffic/usage metrics (handled separately), auto-restart-on-unhealthy
(Docker marks unhealthy but does not restart by default; revisit later if wanted).

## Design

A liveness **heartbeat file** written from inside the running event loop, checked
by the Docker healthcheck.

### Heartbeat writer (`src/bot/__main__.py`)

The `[job-queue]` extra is already a dependency (`python-telegram-bot[job-queue]`).
Register a repeating job that writes the current epoch to a file under the existing
data dir, just before `app.run_polling()`:

```python
import time
from pathlib import Path
from telegram.ext import ContextTypes

HEARTBEAT_INTERVAL = 30  # seconds

async def _heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    path = Path(context.bot_data["settings"].data_dir) / "heartbeat"
    path.write_text(str(int(time.time())))

# ... after handlers are registered, before app.run_polling():
app.job_queue.run_repeating(_heartbeat, interval=HEARTBEAT_INTERVAL, first=0)
```

`settings.data_dir` already exists and is writable (the `UserStore` writes
`allowed_users.json` there). The job runs on the same loop that processes updates,
so if the loop wedges, the file goes stale — exactly the signal we want.

### Healthcheck (`docker-compose.yml`)

Use the in-image Python (base is `python:3.12-slim`); no extra tooling. Fail if the
heartbeat is older than 90s (3× the write interval — tolerates a missed beat):

```yaml
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import os,time,sys; sys.exit(0 if time.time()-os.path.getmtime('/app/src/data/heartbeat')<90 else 1)\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
```

`start_period: 40s` covers boot before the first beat. The absolute path
`/app/src/data/heartbeat` matches the `botdata` volume mount (`botdata:/app/src/data`).

## Files touched

| File | Change |
|---|---|
| `src/bot/__main__.py` | add `_heartbeat` callback + `run_repeating` registration |
| `docker-compose.yml` | add `healthcheck:` block to the `bot` service |

## Deploy

`make deploy-bot` (rebuilds the image — code changed — and recreates the container).

## Test plan

1. After deploy, wait past `start_period`, then:
   `docker inspect -f '{{.State.Health.Status}}' tiktok-tg-bot-bot-1` → `healthy`.
2. Confirm the file updates: `docker exec tiktok-tg-bot-bot-1 cat /app/src/data/heartbeat`
   twice, ~30s apart — value increases.
3. Negative test (optional): pause the container's heartbeat by deleting the file and
   blocking writes, or `docker pause`, and confirm status flips to `unhealthy` within
   ~90s, then recovers after unpause.

## Rollback

Revert the two files and `make deploy-bot`. No data/state involved.

## Risks

- None significant. Additive change, no shared infra, ~0 footprint. The only
  behavioral change is one tiny file write every 30s to an existing volume.
