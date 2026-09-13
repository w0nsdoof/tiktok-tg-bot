import asyncio
import io
import json
import os
import re
import shutil
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import structlog
import yt_dlp

from bot.models.video_info import VideoInfo

log = structlog.get_logger()


class DownloadError(Exception):
    pass


class ErrorType(Enum):
    TOO_LONG = "too_long"
    TOO_LARGE = "too_large"
    PRIVATE = "private"
    AUTH_REQUIRED = "auth_required"
    PLATFORM_DOWN = "platform_down"
    NOT_VIDEO = "not_video"
    DOWNLOAD_ERROR = "download_error"
    NO_AUDIO = "no_audio"


class VideoDownloadError(DownloadError):
    def __init__(self, error_type: ErrorType, message: str = "") -> None:
        self.error_type = error_type
        super().__init__(message or error_type.value)


@dataclass
class MediaItem:
    url: str
    is_video: bool


@dataclass
class MediaFile:
    path: str
    is_video: bool


@dataclass
class VideoMetadata:
    duration: int | None
    file_size: int | None
    title: str | None
    is_slideshow: bool = False
    info: VideoInfo | None = None
    media_items: list[MediaItem] = field(default_factory=list)


@dataclass
class SlideshowResult:
    image_paths: list[str] = field(default_factory=list)
    audio_path: str | None = None
    title: str | None = None


@dataclass
class AudioResult:
    audio_path: str
    title: str | None = None
    duration: int | None = None


def _classify_error(error_msg: str) -> ErrorType:
    lower = error_msg.lower()
    if any(w in lower for w in ("private", "deleted", "removed")):
        return ErrorType.PRIVATE
    if any(
        w in lower
        for w in (
            "login required",
            "authentication",
            "cookies-from-browser",
            "registered users",
            "rate-limit reached",
            "certain audiences",
        )
    ):
        return ErrorType.AUTH_REQUIRED
    if any(w in lower for w in ("unavailable", "not available")):
        return ErrorType.PRIVATE
    if any(w in lower for w in ("rate", "limit", "429", "too many", "blocked")):
        return ErrorType.PLATFORM_DOWN
    if any(w in lower for w in ("no video", "not a video", "unsupported url")):
        return ErrorType.NOT_VIDEO
    return ErrorType.DOWNLOAD_ERROR


def _resolve_tiktok_shortlink(url: str) -> str:
    """Follow redirects on TikTok short links to get the canonical URL."""
    if re.match(r"https?://v[mt]\.tiktok\.com/", url):
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return cast(str, resp.url)
        except Exception:
            pass
    return url


def _normalize_tiktok_url(url: str) -> str:
    """Resolve short links, then convert /photo/ URLs to /video/ for yt-dlp."""
    url = _resolve_tiktok_shortlink(url)
    return re.sub(r"(tiktok\.com/@[^/]+)/photo/", r"\1/video/", url)


_COMMON_OPTS: dict[str, object] = {
    "quiet": True,
    "no_warnings": True,
    "remote_components": ["ejs:github"],
}


def _ydl_opts(
    *, cookies_file: str | None = None, **overrides: object
) -> dict[str, object]:
    """Build yt-dlp options, optionally authenticating Instagram requests."""
    opts = {**_COMMON_OPTS, **overrides}
    if cookies_file:
        cookie_path = Path(cookies_file)
        if cookie_path.is_file():
            # yt-dlp writes cookies back on close; an in-memory copy keeps
            # a read-only mount working and concurrent downloads from
            # clobbering the shared file.
            try:
                opts["cookiefile"] = io.StringIO(cookie_path.read_text())
            except OSError as exc:
                log.warning(
                    "instagram.cookies_file_unreadable",
                    path=str(cookie_path),
                    error=str(exc),
                )
        else:
            log.warning("instagram.cookies_file_missing", path=str(cookie_path))
    return opts


def _instagram_media_items(info: dict[str, Any]) -> list[MediaItem]:
    """Ordered photos/videos of a photo or carousel post; empty for a single video."""
    if info.get("_type") == "playlist":
        entries = list(info.get("entries") or [])
    elif not info.get("formats"):
        entries = [info]
    else:
        return []

    items: list[MediaItem] = []
    for entry in entries:
        formats = entry.get("formats") or []
        if formats:
            # DASH formats are separate video/audio streams; progressive ones are complete.
            progressive = [
                f
                for f in formats
                if f.get("url") and not str(f.get("format_id", "")).startswith("dash")
            ]
            if progressive:
                best = max(progressive, key=lambda f: f.get("height") or 0)
                items.append(MediaItem(url=best["url"], is_video=True))
        else:
            thumbnails = [t for t in entry.get("thumbnails") or [] if t.get("url")]
            if thumbnails:
                best = max(thumbnails, key=lambda t: t.get("width") or 0)
                items.append(MediaItem(url=best["url"], is_video=False))
    return items


def _extract_metadata_sync(
    url: str, cookies_file: str | None = None
) -> VideoMetadata:
    resolved_url = _resolve_tiktok_shortlink(url)
    normalized_url = re.sub(r"(tiktok\.com/@[^/]+)/photo/", r"\1/video/", resolved_url)
    ydl_opts = _ydl_opts(skip_download=True, cookies_file=cookies_file)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            media_items: list[MediaItem] = []
            if "instagram.com/" in normalized_url:
                # Unprocessed info, so photo and carousel posts don't trip
                # yt-dlp's "No video formats found" check.
                info = ydl.extract_info(normalized_url, download=False, process=False)
                media_items = _instagram_media_items(info) if info else []
                if info and not media_items:
                    info = ydl.process_ie_result(info, download=False)
            else:
                info = ydl.extract_info(normalized_url, download=False)
            if info is None:
                raise VideoDownloadError(ErrorType.NOT_VIDEO, "Could not extract video info")
            is_slideshow = info.get("vcodec") == "none" and "/photo/" in resolved_url
            video_info: VideoInfo | None = None
            try:
                video_info = VideoInfo.from_info_dict(info, normalized_url)
            except Exception:
                log.warning("metadata.video_info_failed", exc_info=True)
            return VideoMetadata(
                duration=info.get("duration"),
                file_size=info.get("filesize") or info.get("filesize_approx"),
                title=info.get("title"),
                is_slideshow=is_slideshow,
                info=video_info,
                media_items=media_items,
            )
    except yt_dlp.utils.DownloadError as e:
        raise VideoDownloadError(_classify_error(str(e)), str(e)) from e


def _download_video_sync(
    url: str, output_dir: str, cookies_file: str | None = None
) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # Use UUID prefix to avoid collisions when same video is requested concurrently
    unique_prefix = uuid4().hex[:8]
    output_template = os.path.join(output_dir, f"{unique_prefix}_%(id)s.%(ext)s")
    ydl_opts = _ydl_opts(
        cookies_file=cookies_file,
        outtmpl=output_template,
        format=(
            "bestvideo[filesize<=50M][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[filesize<=50M]+bestaudio/"
            "best[filesize<=50M]/"
            "bestvideo[filesize_approx<=50M]+bestaudio[filesize_approx<=50M]/"
            "best[filesize_approx<=50M]/"
            "best"
        ),
        merge_output_format="mp4",
    )
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


def _download_audio_sync(
    url: str, output_dir: str, cookies_file: str | None = None
) -> AudioResult:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    unique_prefix = uuid4().hex[:8]
    audio_template = os.path.join(output_dir, f"{unique_prefix}_audio.%(ext)s")
    normalized_url = _normalize_tiktok_url(url)
    ydl_opts = _ydl_opts(
        cookies_file=cookies_file,
        outtmpl=audio_template,
        format="bestaudio/best",
        postprocessors=[{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }],
    )
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalized_url, download=True)
            if info is None:
                raise VideoDownloadError(
                    ErrorType.DOWNLOAD_ERROR, "Audio download returned no info"
                )
            title = info.get("title")
            duration = info.get("duration")
            # After FFmpegExtractAudio, the file extension changes to m4a
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            m4a_path = base + ".m4a"
            if os.path.exists(m4a_path):
                return AudioResult(audio_path=m4a_path, title=title, duration=duration)
            if os.path.exists(filename):
                return AudioResult(audio_path=filename, title=title, duration=duration)
            raise VideoDownloadError(
                ErrorType.DOWNLOAD_ERROR, "Audio file not found after extraction"
            )
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        if "audio" in error_msg and ("no" in error_msg or "not" in error_msg):
            raise VideoDownloadError(ErrorType.NO_AUDIO, str(e)) from e
        raise VideoDownloadError(_classify_error(str(e)), str(e)) from e


def _download_slideshow_sync(
    url: str,
    output_dir: str,
    *,
    include_audio: bool = True,
    cookies_file: str | None = None,
) -> SlideshowResult:
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

    # 3. Download audio via yt-dlp (if requested)
    audio_path: str | None = None
    title: str | None = None
    if include_audio:
        video_url = _normalize_tiktok_url(url)
        audio_template = os.path.join(output_dir, f"{unique_prefix}_audio.%(ext)s")
        ydl_opts = _ydl_opts(
            cookies_file=cookies_file,
            outtmpl=audio_template,
            format="bestaudio/best",
        )
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


def _download_instagram_media_sync(
    items: list[MediaItem], output_dir: str, max_bytes: int
) -> list[MediaFile]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    prefix = f"{uuid4().hex[:8]}_ig_"
    files: list[MediaFile] = []
    try:
        for i, item in enumerate(items):
            dest = os.path.join(output_dir, f"{prefix}{i}.{'mp4' if item.is_video else 'jpg'}")
            req = urllib.request.Request(item.url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            })
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            if item.is_video and os.path.getsize(dest) > max_bytes:
                os.remove(dest)
                log.info("instagram_media.video_too_large", url=item.url)
                continue
            files.append(MediaFile(path=dest, is_video=item.is_video))
    except OSError as e:
        for name in os.listdir(output_dir):
            if name.startswith(prefix):
                os.remove(os.path.join(output_dir, name))
        raise VideoDownloadError(ErrorType.DOWNLOAD_ERROR, str(e)) from e

    if not files:
        raise VideoDownloadError(ErrorType.TOO_LARGE, "All videos exceed the size limit")
    return files


async def download_audio(
    url: str, output_dir: str, cookies_file: str | None = None
) -> AudioResult:
    start = time.monotonic()
    log.info("audio_download.started", url=url)
    try:
        result = await asyncio.to_thread(
            _download_audio_sync, url, output_dir, cookies_file
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "audio_download.completed",
            duration_ms=duration_ms,
            url=url,
        )
        return result
    except VideoDownloadError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning(
            "audio_download.failed",
            error_type=e.error_type.value,
            duration_ms=duration_ms,
            url=url,
        )
        raise


async def download_slideshow(
    url: str,
    output_dir: str,
    *,
    include_audio: bool = True,
    cookies_file: str | None = None,
) -> SlideshowResult:
    start = time.monotonic()
    log.info("slideshow_download.started", url=url)
    try:
        result = await asyncio.to_thread(
            _download_slideshow_sync,
            url,
            output_dir,
            include_audio=include_audio,
            cookies_file=cookies_file,
        )
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


async def download_instagram_media(
    items: list[MediaItem], output_dir: str, max_bytes: int
) -> list[MediaFile]:
    start = time.monotonic()
    log.info("instagram_media_download.started", item_count=len(items))
    try:
        files = await asyncio.to_thread(
            _download_instagram_media_sync, items, output_dir, max_bytes
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "instagram_media_download.completed",
            duration_ms=duration_ms,
            file_count=len(files),
        )
        return files
    except VideoDownloadError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning(
            "instagram_media_download.failed",
            error_type=e.error_type.value,
            duration_ms=duration_ms,
        )
        raise


async def extract_metadata(
    url: str, cookies_file: str | None = None
) -> VideoMetadata:
    start = time.monotonic()
    try:
        metadata = await asyncio.to_thread(_extract_metadata_sync, url, cookies_file)
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


async def download_video(
    url: str, output_dir: str, cookies_file: str | None = None
) -> str:
    start = time.monotonic()
    log.info("download.started", url=url)
    try:
        file_path = await asyncio.to_thread(
            _download_video_sync, url, output_dir, cookies_file
        )
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
