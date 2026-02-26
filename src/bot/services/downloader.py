import asyncio
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import uuid4

import structlog
import yt_dlp

log = structlog.get_logger()


class DownloadError(Exception):
    pass


class ErrorType(Enum):
    TOO_LONG = "too_long"
    TOO_LARGE = "too_large"
    PRIVATE = "private"
    PLATFORM_DOWN = "platform_down"
    NOT_VIDEO = "not_video"
    DOWNLOAD_ERROR = "download_error"


class VideoDownloadError(DownloadError):
    def __init__(self, error_type: ErrorType, message: str = "") -> None:
        self.error_type = error_type
        super().__init__(message or error_type.value)


@dataclass
class VideoMetadata:
    duration: int | None
    file_size: int | None
    title: str | None


def _classify_error(error_msg: str) -> ErrorType:
    lower = error_msg.lower()
    if any(w in lower for w in ("private", "deleted", "removed", "unavailable", "not available")):
        return ErrorType.PRIVATE
    if any(w in lower for w in ("rate", "limit", "429", "too many", "blocked")):
        return ErrorType.PLATFORM_DOWN
    if any(w in lower for w in ("no video", "not a video", "unsupported url")):
        return ErrorType.NOT_VIDEO
    return ErrorType.DOWNLOAD_ERROR


def _extract_metadata_sync(url: str) -> VideoMetadata:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise VideoDownloadError(ErrorType.NOT_VIDEO, "Could not extract video info")
            return VideoMetadata(
                duration=info.get("duration"),
                file_size=info.get("filesize") or info.get("filesize_approx"),
                title=info.get("title"),
            )
    except yt_dlp.utils.DownloadError as e:
        raise VideoDownloadError(_classify_error(str(e)), str(e)) from e


def _download_video_sync(url: str, output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # Use UUID prefix to avoid collisions when same video is requested concurrently
    unique_prefix = uuid4().hex[:8]
    output_template = os.path.join(output_dir, f"{unique_prefix}_%(id)s.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": output_template,
        "format": (
            "bestvideo[filesize<=50M][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[filesize<=50M]+bestaudio/"
            "best[filesize<=50M]/"
            "bestvideo[filesize_approx<=50M]+bestaudio[filesize_approx<=50M]/"
            "best[filesize_approx<=50M]/"
            "best"
        ),
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise VideoDownloadError(ErrorType.DOWNLOAD_ERROR, "Download returned no info")
            filename: str = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            mp4_path = base + ".mp4"
            if os.path.exists(mp4_path):
                return str(mp4_path)
            if os.path.exists(filename):
                return str(filename)
            raise VideoDownloadError(
                ErrorType.DOWNLOAD_ERROR, "Downloaded file not found"
            )
    except yt_dlp.utils.DownloadError as e:
        raise VideoDownloadError(_classify_error(str(e)), str(e)) from e


async def extract_metadata(url: str) -> VideoMetadata:
    start = time.monotonic()
    try:
        metadata = await asyncio.to_thread(_extract_metadata_sync, url)
        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "download.metadata_extracted",
            duration_ms=duration_ms,
            video_duration_s=metadata.duration,
            file_size_bytes=metadata.file_size,
            url=url,
        )
        return metadata
    except VideoDownloadError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning(
            "download.failed",
            error_type=e.error_type.value,
            stage="metadata",
            duration_ms=duration_ms,
            url=url,
        )
        raise


async def download_video(url: str, output_dir: str) -> str:
    start = time.monotonic()
    log.info("download.started", url=url)
    try:
        file_path = await asyncio.to_thread(_download_video_sync, url, output_dir)
        duration_ms = int((time.monotonic() - start) * 1000)
        file_size = os.path.getsize(file_path)
        log.info(
            "download.completed",
            duration_ms=duration_ms,
            file_size_bytes=file_size,
            output_format="mp4",
            url=url,
        )
        return file_path
    except VideoDownloadError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning(
            "download.failed",
            error_type=e.error_type.value,
            stage="download",
            duration_ms=duration_ms,
            url=url,
        )
        raise
