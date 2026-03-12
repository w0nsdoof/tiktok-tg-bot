import re

from bot.models.request import OutputFormat

AUDIO_KEYWORDS: set[str] = {
    # English
    "audio", "mp3", "sound",
    # Russian
    "аудио", "звук", "музыка",
}

IMAGE_KEYWORDS: set[str] = {
    # English
    "images", "pics", "photos", "png",
    # Russian
    "картинки", "фото", "изображения",
}

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")  # noqa: RUF001


def parse_output_format(text: str, url: str) -> OutputFormat:
    """Detect output format keyword from message text, excluding the URL portion.

    Case-insensitive, whole-word matching. First recognized keyword wins.
    """
    text_without_url = text.replace(url, "")
    for match in _WORD_RE.finditer(text_without_url):
        word = match.group(0).lower()
        if word in AUDIO_KEYWORDS:
            return OutputFormat.AUDIO
        if word in IMAGE_KEYWORDS:
            return OutputFormat.IMAGES
    return OutputFormat.DEFAULT
