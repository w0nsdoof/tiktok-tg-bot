import time
from pathlib import Path

from telegram.ext import ContextTypes

HEARTBEAT_FILENAME = "heartbeat"


def heartbeat_path(data_dir: str) -> Path:
    return Path(data_dir) / HEARTBEAT_FILENAME


def clear_heartbeat(data_dir: str) -> None:
    # The file sits in a persistent volume; a new container must not inherit the old beat.
    heartbeat_path(data_dir).unlink(missing_ok=True)


def write_heartbeat(data_dir: str) -> None:
    heartbeat_path(data_dir).write_text(str(int(time.time())))


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    write_heartbeat(settings.data_dir)
