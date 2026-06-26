# Bot Heartbeat Healthcheck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Docker report `tiktok-tg-bot` as `unhealthy` when its polling event loop stops running, not merely when the process dies.

**Architecture:** A repeating `python-telegram-bot` job, running on the same event loop that processes updates, writes the current epoch to a `heartbeat` file in the data dir every 30s. A Docker `HEALTHCHECK` fails when that file is older than 90s. The write logic lives in a small focused module (`src/bot/health.py`) so it is unit-testable in isolation from PTB wiring.

**Tech Stack:** Python 3.12, `python-telegram-bot[job-queue]` (already a dependency), pytest (`asyncio_mode = auto`), uv, Docker Compose.

## Global Constraints

- Python target `py312`; ruff line-length `100`; ruff lint selects `E,F,I,N,UP,B,SIM,RUF`; mypy is configured — new code must pass `uv run ruff check` and `uv run mypy`.
- `python-telegram-bot` is pinned `>=21.0,<22.0`; the `[job-queue]` extra is already installed — do not add new dependencies.
- The container data dir is the `botdata` volume mounted at `/app/src/data`; `settings.data_dir` resolves to it at runtime.
- Tests import the package as `from bot.<module> import ...` and use the pytest `tmp_path` fixture (see `tests/unit/test_downloader.py`).

---

### Task 1: Heartbeat module + wiring

**Files:**
- Create: `src/bot/health.py`
- Test: `tests/unit/test_health.py`
- Modify: `src/bot/__main__.py` (add import + register the repeating job before `app.run_polling()`)

**Interfaces:**
- Produces:
  - `bot.health.HEARTBEAT_FILENAME: str` = `"heartbeat"`
  - `bot.health.heartbeat_path(data_dir: str) -> pathlib.Path`
  - `bot.health.write_heartbeat(data_dir: str) -> None` — writes `str(int(time.time()))` to the heartbeat file, creating it if absent.
  - `bot.health.heartbeat_job(context) -> None` — async PTB job callback; reads `context.bot_data["settings"].data_dir` and calls `write_heartbeat`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_health.py`:

```python
import time
from types import SimpleNamespace

from bot.health import HEARTBEAT_FILENAME, heartbeat_job, heartbeat_path, write_heartbeat


class TestWriteHeartbeat:
    def test_creates_file_with_recent_epoch(self, tmp_path):
        before = int(time.time())
        write_heartbeat(str(tmp_path))
        path = tmp_path / HEARTBEAT_FILENAME
        assert path.exists()
        written = int(path.read_text())
        assert written >= before

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / HEARTBEAT_FILENAME
        path.write_text("0")
        write_heartbeat(str(tmp_path))
        assert int(path.read_text()) > 0

    def test_heartbeat_path_joins_filename(self, tmp_path):
        assert heartbeat_path(str(tmp_path)) == tmp_path / HEARTBEAT_FILENAME


class TestHeartbeatJob:
    async def test_job_writes_via_settings_data_dir(self, tmp_path):
        ctx = SimpleNamespace(bot_data={"settings": SimpleNamespace(data_dir=str(tmp_path))})
        await heartbeat_job(ctx)
        assert (tmp_path / HEARTBEAT_FILENAME).exists()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd ~/petprojects/tiktok-tg-bot && uv run pytest tests/unit/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.health'`.

- [x] **Step 3: Write the minimal implementation**

Create `src/bot/health.py`:

```python
import time
from pathlib import Path

from telegram.ext import ContextTypes

HEARTBEAT_FILENAME = "heartbeat"


def heartbeat_path(data_dir: str) -> Path:
    return Path(data_dir) / HEARTBEAT_FILENAME


def write_heartbeat(data_dir: str) -> None:
    heartbeat_path(data_dir).write_text(str(int(time.time())))


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    write_heartbeat(settings.data_dir)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_health.py -v`
Expected: PASS (4 passed).

- [x] **Step 5: Wire the job into the bot**

In `src/bot/__main__.py`, add to the existing import group:

```python
from bot.health import heartbeat_job
```

Then, immediately before `app.run_polling()` (after all handlers are registered and the `log.info("bot.starting", ...)` call), add:

```python
    app.job_queue.run_repeating(heartbeat_job, interval=30, first=0)
```

`first=0` writes the first heartbeat at startup so the file exists before the
healthcheck's `start_period` elapses.

- [x] **Step 6: Run the full suite + linters**

Run: `uv run pytest -q && uv run ruff check && uv run mypy src`
Expected: all tests pass; ruff reports no issues; mypy reports no errors.

- [x] **Step 7: Commit** (only with the user's go-ahead — see Execution notes)

```bash
git add src/bot/health.py tests/unit/test_health.py src/bot/__main__.py
git commit -m "feat: add heartbeat liveness for the polling loop"
```

---

### Task 2: Docker healthcheck + live verification

**Files:**
- Modify: `docker-compose.yml` (add a `healthcheck:` block to the `bot` service)

**Interfaces:**
- Consumes: the `heartbeat` file written by Task 1 at `/app/src/data/heartbeat`.

- [x] **Step 1: Add the healthcheck to compose**

In `docker-compose.yml`, under the `bot:` service (sibling of `mem_limit`), add:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import os,time,sys; sys.exit(0 if time.time()-os.path.getmtime('/app/src/data/heartbeat')<90 else 1)\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
```

- [x] **Step 2: Validate compose parses**

Run: `cd ~/petprojects/tiktok-tg-bot && docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML/schema error).

- [x] **Step 3: Deploy** (confirm with the user first — this restarts the live bot)

Run: `make deploy-bot` (from `~/petprojects`)
Expected: image rebuilds, `tiktok-tg-bot-bot-1` recreated and starts.

- [x] **Step 4: Verify the container reports healthy**

After ~45s (past `start_period`), run on the server:
`docker inspect -f '{{.State.Health.Status}}' tiktok-tg-bot-bot-1`
Expected: `healthy`.

- [x] **Step 5: Verify the heartbeat advances**

Run twice ~30s apart on the server:
`docker exec tiktok-tg-bot-bot-1 cat /app/src/data/heartbeat`
Expected: the integer increases between reads.

- [x] **Step 6: Commit** (only with the user's go-ahead)

```bash
git add docker-compose.yml
git commit -m "feat: docker healthcheck on bot heartbeat freshness"
```

---

## Execution notes

- **Commits:** per the user's standing rule, commit only on explicit go-ahead. Treat the commit steps as ready-to-run, but ask before executing them.
- **Deploy:** Task 2 Step 3 restarts the production bot; confirm before running `make deploy-bot`.

## Self-Review

- **Spec coverage:** heartbeat writer (Task 1 Steps 1–4), loop-based liveness via `job_queue` (Task 1 Step 5), 90s/30s healthcheck with `start_period` (Task 2 Step 1), `make deploy-bot` (Task 2 Step 3), `docker inspect` health + heartbeat-advance tests (Task 2 Steps 4–5), rollback = revert files + redeploy (covered by git history + deploy). All spec items mapped.
- **Placeholder scan:** none — every code/command step is concrete.
- **Type consistency:** `write_heartbeat(data_dir: str)`, `heartbeat_path(data_dir: str) -> Path`, `heartbeat_job(context)`, and `HEARTBEAT_FILENAME` are used identically in the module, tests, and wiring.
