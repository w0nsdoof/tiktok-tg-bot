import pytest

from bot.models.request import Platform
from bot.services.url_parser import extract_url


class TestExtractUrlInstagram:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/reel/C1a2B3c4D5e/",
            "https://instagram.com/reels/C1a2B3c4D5e",
            "https://www.instagram.com/p/DczZiD_Nlf0/?stkn=MXdkbGMxM3BwbDQ2ZQ==",
        ],
    )
    def test_recognizes_instagram_urls(self, url: str):
        result = extract_url(url)
        assert result is not None
        assert result[1] == Platform.INSTAGRAM
