import asyncio
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
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
    is_slideshow: bool = False


@dataclass
class SlideshowResult:
    image_paths: list[str] = field(default_factory=list)
    audio_path: str | None = None
    title: str | None = None


def _classify_error(error_msg: str) -> ErrorType:
    lower = error_msg.lower()
    if any(w in lower for w in ("private", "deleted", "removed", "unavailable", "not available")):
        return ErrorType.PRIVATE
    if any(w in lower for w in ("rate", "limit", "429", "too many", "blocked")):
        return ErrorType.PLATFORM_DOWN
    if any(w in lower for w in ("no video", "not a video", "unsupported url")):
        return ErrorType.NOT_VIDEO
    return ErrorType.DOWNLOAD_ERROR


def _normalize_tiktok_url(url: str) -> str:
    """Convert /photo/ URLs to /video/ for yt-dlp compatibility."""
    return re.sub(r"(tiktok\.com/@[^/]+)/photo/", r"\1/video/", url)


def _extract_metadata_sync(url: str) -> VideoMetadata:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(_normalize_tiktok_url(url), download=False)
            if info is None:
                raise VideoDownloadError(ErrorType.NOT_VIDEO, "Could not extract video info")
            is_slideshow = info.get("vcodec") == "none" and "/photo/" in url
            return VideoMetadata(
                duration=info.get("duration"),
                file_size=info.get("filesize") or info.get("filesize_approx"),
                title=info.get("title"),
                is_slideshow=is_slideshow,
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


def _scrape_slideshow_images(url: str) -> list[str]:
    """Fetch image URLs from TikTok slideshow page HTML."""
    video_url = _normalize_tiktok_url(url)
    req = urllib.request.Request(video_url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    match = re.search(
        r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return []

    data = json.loads(match.group(1))
    item = (
        data.get("__DEFAULT_SCOPE__", {})
        .get("webapp.video-detail", {})
        .get("itemInfo", {})
        .get("itemStruct", {})
    )
    image_post = item.get("imagePost")
    if not image_post:
        return []

    image_urls: list[str] = []
    for img in image_post.get("images", []):
        url_list = img.get("imageURL", {}).get("urlList", [])
        if url_list:
            image_urls.append(url_list[0])
    return image_urls


def _download_slideshow_sync(url: str, output_dir: str) -> SlideshowResult:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    unique_prefix = uuid4().hex[:8]

    # 1. Scrape image URLs from the webpage
    image_urls = _scrape_slideshow_images(url)
    if not image_urls:
        raise VideoDownloadError(ErrorType.DOWNLOAD_ERROR, "Could not extract slideshow images")

    # 2. Download images
    image_paths: list[str] = []
    for i, img_url in enumerate(image_urls):
        ext = "jpeg"
        dest = os.path.join(output_dir, f"{unique_prefix}_slide_{i}.{ext}")
        req = urllib.request.Request(img_url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        image_paths.append(dest)

    # 3. Download audio via yt-dlp
    audio_path: str | None = None
    title: str | None = None
    video_url = _normalize_tiktok_url(url)
    audio_template = os.path.join(output_dir, f"{unique_prefix}_audio.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": audio_template,
        "format": "bestaudio/best",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if info:
                title = info.get("title")
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    audio_path = filename
    except yt_dlp.utils.DownloadError:
        log.warning("slideshow.audio_download_failed", url=url)

    return SlideshowResult(image_paths=image_paths, audio_path=audio_path, title=title)


async def download_slideshow(url: str, output_dir: str) -> SlideshowResult:
    start = time.monotonic()
    log.info("slideshow_download.started", url=url)
    try:
        result = await asyncio.to_thread(_download_slideshow_sync, url, output_dir)
        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "slideshow_download.completed",
            duration_ms=duration_ms,
            image_count=len(result.image_paths),
            has_audio=result.audio_path is not None,
            url=url,
        )
        return result
    except VideoDownloadError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning(
            "slideshow_download.failed",
            error_type=e.error_type.value,
            duration_ms=duration_ms,
            url=url,
        )
        raise


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
