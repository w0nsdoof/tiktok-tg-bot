import pytest

from bot.models.request import OutputFormat
from bot.services.format_parser import parse_output_format

DUMMY_URL = "https://www.tiktok.com/@user/video/123456"


class TestParseOutputFormat:
    def test_no_keyword_returns_default(self):
        assert parse_output_format(DUMMY_URL, DUMMY_URL) == OutputFormat.DEFAULT

    def test_extra_text_no_keyword_returns_default(self):
        assert parse_output_format(f"check this {DUMMY_URL}", DUMMY_URL) == OutputFormat.DEFAULT

    @pytest.mark.parametrize("keyword", ["audio", "mp3", "sound"])
    def test_english_audio_keywords(self, keyword: str):
        text = f"{keyword} {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    @pytest.mark.parametrize("keyword", ["аудио", "звук", "музыка"])
    def test_russian_audio_keywords(self, keyword: str):
        text = f"{DUMMY_URL} {keyword}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    @pytest.mark.parametrize("keyword", ["images", "pics", "photos", "png"])
    def test_english_image_keywords(self, keyword: str):
        text = f"{keyword} {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.IMAGES

    @pytest.mark.parametrize("keyword", ["картинки", "фото", "изображения"])
    def test_russian_image_keywords(self, keyword: str):
        text = f"{DUMMY_URL} {keyword}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.IMAGES

    @pytest.mark.parametrize("keyword", ["AUDIO", "Audio", "AuDiO", "MP3", "SOUND"])
    def test_case_insensitive(self, keyword: str):
        text = f"{keyword} {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    def test_url_excluded(self):
        """Keywords inside the URL should not be detected."""
        url = "https://www.tiktok.com/@audio/video/123"
        text = url
        assert parse_output_format(text, url) == OutputFormat.DEFAULT

    def test_first_keyword_wins_audio_before_images(self):
        text = f"audio images {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    def test_first_keyword_wins_images_before_audio(self):
        text = f"images audio {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.IMAGES

    def test_unrecognized_keyword_returns_default(self):
        text = f"download {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.DEFAULT

    def test_punctuation_adjacent_audio(self):
        text = f"audio! {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    def test_punctuation_adjacent_comma(self):
        text = f"audio, {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    def test_keyword_after_url(self):
        text = f"{DUMMY_URL} звук"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO

    def test_keyword_before_url(self):
        text = f"mp3 {DUMMY_URL}"
        assert parse_output_format(text, DUMMY_URL) == OutputFormat.AUDIO
