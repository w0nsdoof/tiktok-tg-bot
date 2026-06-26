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
