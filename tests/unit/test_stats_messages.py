"""Locale coverage for /stats and /top strings."""

import pytest

from bot.locales.messages import MESSAGES, get_message

STATS_KEYS = [
    "stats_unavailable",
    "stats_empty",
    "stats_personal",
    "stats_global",
    "top_usage",
    "top_tags_title",
    "top_creators_title",
    "top_videos_title",
    "top_empty",
]


@pytest.mark.parametrize("key", STATS_KEYS)
def test_key_exists_in_both_languages(key):
    assert key in MESSAGES["en"]
    assert key in MESSAGES["ru"]


def test_personal_template_formats():
    text = get_message(
        "stats_personal",
        "en",
        requests=10,
        downloads=8,
        since="2026-07-20",
        platforms="1. tiktok — 6",
        creators="1. @cat — 3",
        hashtags="1. #fyp — 4",
    )
    assert "10" in text and "@cat" in text


def test_help_mentions_new_commands():
    for lang in ("en", "ru"):
        assert "/stats" in MESSAGES[lang]["help"]
        assert "/top" in MESSAGES[lang]["help"]
