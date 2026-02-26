import re

from bot.models.request import Platform

_PLATFORM_PATTERNS: list[tuple[re.Pattern[str], Platform]] = [
    (re.compile(r"https?://(?:www\.)?tiktok\.com/@[^/]+/video/\d+"), Platform.TIKTOK),
    (re.compile(r"https?://(?:www\.)?tiktok\.com/@[^/]+/photo/\d+"), Platform.TIKTOK),
    (re.compile(r"https?://(?:www\.)?tiktok\.com/t/\w+"), Platform.TIKTOK),
    (re.compile(r"https?://vm\.tiktok\.com/\w+"), Platform.TIKTOK),
    (re.compile(r"https?://(?:www\.)?youtube\.com/shorts/[\w-]+"), Platform.YOUTUBE),
    (re.compile(r"https?://youtu\.be/[\w-]+"), Platform.YOUTUBE),
    (re.compile(r"https?://(?:www\.)?instagram\.com/reels?/[\w-]+"), Platform.INSTAGRAM),
]

_URL_RE = re.compile(r"https?://\S+")


def extract_url(text: str) -> tuple[str, Platform] | None:
    for url_match in _URL_RE.finditer(text):
        url = url_match.group(0)
        for pattern, platform in _PLATFORM_PATTERNS:
            if pattern.match(url):
                return url, platform
    return None
