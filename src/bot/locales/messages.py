from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "downloading": "Downloading your video...",
        "sending": "Sending video...",
        "error_too_long": "This video is too long. I only support videos under 5 minutes.",
        "error_too_large": (
            "This video is too large to send via Telegram (over 50 MB)."
        ),
        "error_private": "This video is unavailable (private or deleted).",
        "error_platform_down": (
            "Could not reach the platform right now. Please try again in a few minutes."
        ),
        "error_not_video": (
            "This link doesn't point to a video. Please send a direct link to a video."
        ),
        "error_download": "Something went wrong while downloading. Please try again.",
        "error_unknown": "An unexpected error occurred. Please try again later.",
        "help": (
            "Send me a video link from TikTok, YouTube Shorts, or Instagram Reels "
            "and I'll download it for you.\n\n"
            "Supported platforms:\n"
            "- TikTok (tiktok.com, vm.tiktok.com)\n"
            "- YouTube Shorts (youtube.com/shorts, youtu.be)\n"
            "- Instagram Reels (instagram.com/reel)"
        ),
        "help_inline": "Send a video link to download it.",
        "queued": "Your request is queued, please wait...",
        "downloading_photos": "Downloading photos...",
        "sending_photos": "Sending photos...",
        "error_slideshow_inline": (
            "Slideshows can't be sent via inline mode. "
            "Please send the link directly to the bot."
        ),
    },
    "ru": {
        "downloading": "Скачиваю ваше видео...",
        "sending": "Отправляю видео...",
        "error_too_long": "Это видео слишком длинное. Я поддерживаю видео до 5 минут.",
        "error_too_large": (
            "Это видео слишком большое для отправки через Telegram (более 50 МБ)."
        ),
        "error_private": "Это видео недоступно (приватное или удалено).",
        "error_platform_down": (
            "Не удалось связаться с платформой. Попробуйте через несколько минут."
        ),
        "error_not_video": (
            "Эта ссылка не ведёт на видео. Отправьте прямую ссылку на видео."
        ),
        "error_download": "Произошла ошибка при скачивании. Попробуйте ещё раз.",
        "error_unknown": "Произошла непредвиденная ошибка. Попробуйте позже.",
        "help": (
            "Отправьте мне ссылку на видео из TikTok, YouTube Shorts или Instagram Reels, "
            "и я скачаю его для вас.\n\n"
            "Поддерживаемые платформы:\n"
            "- TikTok (tiktok.com, vm.tiktok.com)\n"
            "- YouTube Shorts (youtube.com/shorts, youtu.be)\n"
            "- Instagram Reels (instagram.com/reel)"
        ),
        "help_inline": "Отправьте ссылку на видео для скачивания.",
        "queued": "Ваш запрос в очереди, подождите...",
        "downloading_photos": "Скачиваю фотографии...",
        "sending_photos": "Отправляю фотографии...",
        "error_slideshow_inline": (
            "Слайдшоу нельзя отправить через инлайн-режим. "
            "Отправьте ссылку напрямую боту."
        ),
    },
}


def get_message(key: str, lang: str | None = None, **kwargs: Any) -> str:
    language = "ru" if lang and lang.startswith("ru") else "en"
    messages = MESSAGES.get(language, MESSAGES["en"])
    template = messages.get(key, MESSAGES["en"].get(key, key))
    if kwargs:
        return template.format(**kwargs)
    return template
