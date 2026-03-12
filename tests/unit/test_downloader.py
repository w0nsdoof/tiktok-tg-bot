import os
from unittest.mock import MagicMock, patch

import pytest

from bot.services.downloader import (
    AudioResult,
    ErrorType,
    VideoDownloadError,
    _download_audio_sync,
)


class TestDownloadAudioSync:
    def test_successful_extraction(self, tmp_path):
        """Successful audio extraction returns AudioResult with correct fields."""
        m4a_file = tmp_path / "abc_audio.m4a"
        m4a_file.write_bytes(b"fake audio data")

        mock_info = {
            "title": "Test Video",
            "duration": 30,
        }
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = str(tmp_path / "abc_audio.opus")
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
            result = _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert isinstance(result, AudioResult)
        assert result.audio_path == str(m4a_file)
        assert result.title == "Test Video"
        assert result.duration == 30

    def test_no_audio_track_raises_no_audio(self, tmp_path):
        """When yt-dlp reports no audio, raises VideoDownloadError with NO_AUDIO."""
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "no audio streams found"
        )
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with (
            patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl),
            pytest.raises(VideoDownloadError) as exc_info,
        ):
            _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert exc_info.value.error_type == ErrorType.NO_AUDIO

    def test_general_download_error(self, tmp_path):
        """General yt-dlp errors raise VideoDownloadError with DOWNLOAD_ERROR."""
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "some general error"
        )
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with (
            patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl),
            pytest.raises(VideoDownloadError) as exc_info,
        ):
            _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert exc_info.value.error_type == ErrorType.DOWNLOAD_ERROR

    def test_file_not_found_after_extraction(self, tmp_path):
        """If extracted file doesn't exist on disk, raises DOWNLOAD_ERROR."""
        mock_info = {
            "title": "Test",
            "duration": 10,
        }
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = str(tmp_path / "nonexistent.opus")
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with (
            patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl),
            pytest.raises(VideoDownloadError) as exc_info,
        ):
            _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert exc_info.value.error_type == ErrorType.DOWNLOAD_ERROR

    def test_fallback_to_original_filename(self, tmp_path):
        """If m4a doesn't exist but original filename does, use that."""
        orig_file = tmp_path / "abc_audio.opus"
        orig_file.write_bytes(b"fake audio data")

        mock_info = {"title": "Fallback", "duration": 15}
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = str(orig_file)
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
            result = _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert result.audio_path == str(orig_file)
        assert result.title == "Fallback"

    def test_output_dir_created(self, tmp_path):
        """Output directory is created if it doesn't exist."""
        new_dir = tmp_path / "subdir"
        m4a_file = new_dir / "abc_audio.m4a"

        mock_info = {"title": "Test", "duration": 5}
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = str(new_dir / "abc_audio.opus")
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_extract(url, download=True):
            # Simulate yt-dlp creating the directory and file
            new_dir.mkdir(parents=True, exist_ok=True)
            m4a_file.write_bytes(b"audio")
            return mock_info

        mock_ydl.extract_info.side_effect = fake_extract

        with patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
            result = _download_audio_sync(
                "https://www.tiktok.com/@user/video/123", str(new_dir)
            )

        assert os.path.exists(result.audio_path)
