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
            'Add "audio" or "mp3" to get the sound only.\n'
            'Add "images" or "photos" to get slideshow pictures without audio.'
        ),
        "help_inline": "Send a video link to download it.",
        "queued": "Your request is queued, please wait...",
        "downloading_audio": "Downloading audio...",
        "sending_audio": "Sending audio...",
        "error_no_audio": "This content has no audio track.",
        "error_not_slideshow": (
            "This is a video, not a slideshow — images can't be extracted. "
            'Try "audio" to get the sound.'
        ),
        "downloading_photos": "Downloading photos...",
        "sending_photos": "Sending photos...",
        "error_slideshow_inline": (
            "Slideshows can't be sent via inline mode. "
            "Please send the link directly to the bot."
        ),
        "access_denied": (
            "You don't have access to this bot.\n"
            "Use the button below to request access."
        ),
        "request_access_button": "Request Access",
        "access_requested": (
            "Your access request has been sent to the admin. Please wait."
        ),
        "access_already_requested": (
            "You have already requested access. Please wait for admin approval."
        ),
        "admin_access_request": (
            "Access request from {name} ({user_id}).\n"
            "Username: @{username}"
        ),
        "admin_approve_button": "Approve",
        "admin_deny_button": "Deny",
        "admin_approved": "User {name} ({user_id}) has been approved.",
        "admin_denied": "User {name} ({user_id}) has been denied.",
        "access_granted": (
            "Your access has been approved! Send me a video link to get started."
        ),
        "access_rejected": "Your access request has been denied.",
        "user_added": "User {name} ({user_id}) has been added.",
        "user_already_allowed": "User {name} ({user_id}) is already allowed.",
        "forward_hidden_user": (
            "Cannot add this user — their identity is hidden in the forwarded message."
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
            "Добавьте «аудио» или «звук», чтобы получить только звук.\n"
            "Добавьте «картинки» или «фото», чтобы получить фотографии слайдшоу без аудио."
        ),
        "help_inline": "Отправьте ссылку на видео для скачивания.",
        "queued": "Ваш запрос в очереди, подождите...",
        "downloading_audio": "Скачиваю аудио...",
        "sending_audio": "Отправляю аудио...",
        "error_no_audio": "В этом контенте нет аудиодорожки.",
        "error_not_slideshow": (
            "Это видео, а не слайдшоу — изображения нельзя извлечь. "
            "Попробуйте «аудио», чтобы получить звук."
        ),
        "downloading_photos": "Скачиваю фотографии...",
        "sending_photos": "Отправляю фотографии...",
        "error_slideshow_inline": (
            "Слайдшоу нельзя отправить через инлайн-режим. "
            "Отправьте ссылку напрямую боту."
        ),
        "access_denied": (
            "У вас нет доступа к этому боту.\n"
            "Нажмите кнопку ниже, чтобы запросить доступ."
        ),
        "request_access_button": "Запросить доступ",
        "access_requested": (
            "Ваш запрос на доступ отправлен администратору. Пожалуйста, подождите."
        ),
        "access_already_requested": (
            "Вы уже отправили запрос. Пожалуйста, дождитесь одобрения."
        ),
        "admin_access_request": (
            "Запрос на доступ от {name} ({user_id}).\n"
            "Username: @{username}"
        ),
        "admin_approve_button": "Одобрить",
        "admin_deny_button": "Отклонить",
        "admin_approved": "Пользователь {name} ({user_id}) одобрен.",
        "admin_denied": "Пользователь {name} ({user_id}) отклонён.",
        "access_granted": (
            "Ваш доступ одобрен! Отправьте мне ссылку на видео, чтобы начать."
        ),
        "access_rejected": "Ваш запрос на доступ отклонён.",
        "user_added": "Пользователь {name} ({user_id}) добавлен.",
        "user_already_allowed": "Пользователь {name} ({user_id}) уже в списке.",
        "forward_hidden_user": (
            "Невозможно добавить пользователя — "
            "его личность скрыта в пересланном сообщении."
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
