import io
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from bot.services.downloader import (
    AudioResult,
    ErrorType,
    MediaItem,
    VideoDownloadError,
    _classify_error,
    _download_audio_sync,
    _download_instagram_media_sync,
    _extract_metadata_sync,
    _ydl_opts,
)


class TestErrorClassification:
    def test_login_or_rate_limit_is_not_reported_as_private(self):
        message = (
            "Requested content is not available, rate-limit reached or login required. "
            "Use --cookies-from-browser or --cookies for the authentication"
        )
        assert _classify_error(message) == ErrorType.AUTH_REQUIRED

    def test_explicit_private_or_deleted_content_remains_private(self):
        assert _classify_error("This post is private or deleted") == ErrorType.PRIVATE

    def test_instagram_audience_restriction_is_auth_required(self):
        message = (
            "[Instagram] DczZiD_Nlf0: This content isn't available to everyone: "
            "It can't be seen by certain audiences."
        )
        assert _classify_error(message) == ErrorType.AUTH_REQUIRED


class TestYtDlpOptions:
    def test_read_only_cookie_file_is_loaded_and_left_unchanged(self, tmp_path):
        cookie_file = tmp_path / "instagram-cookies.txt"
        content = (
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tTRUE\t1999999999\tsessionid\tabc\n"
        )
        cookie_file.write_text(content)
        cookie_file.chmod(0o444)

        with yt_dlp.YoutubeDL(_ydl_opts(cookies_file=str(cookie_file))) as ydl:
            assert [cookie.name for cookie in ydl.cookiejar] == ["sessionid"]

        assert cookie_file.read_text() == content

    def test_unreadable_cookie_file_is_ignored(self, tmp_path):
        cookie_file = tmp_path / "instagram-cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        cookie_file.chmod(0o000)

        opts = _ydl_opts(cookies_file=str(cookie_file))

        assert "cookiefile" not in opts

    def test_missing_cookie_file_is_ignored(self, tmp_path):
        opts = _ydl_opts(cookies_file=str(tmp_path / "missing.txt"))

        assert "cookiefile" not in opts


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


class TestMetadataVideoInfo:
    def _fake_ydl(self, info):
        ydl = MagicMock()
        ydl.extract_info.return_value = info
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=ydl)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    def test_info_populated(self):
        info = {
            "id": "123",
            "extractor_key": "TikTok",
            "title": "t",
            "description": "#fyp",
            "duration": 10,
            "uploader": "u",
            "channel": "U",
        }
        with patch(
            "bot.services.downloader.yt_dlp.YoutubeDL",
            return_value=self._fake_ydl(info),
        ):
            meta = _extract_metadata_sync("https://www.tiktok.com/@u/video/123")
        assert meta.info is not None
        assert meta.info.video_id == "123"
        assert meta.info.platform == "tiktok"
        assert meta.info.hashtags == ["fyp"]

    def test_normalization_failure_returns_none_info(self):
        info = {"id": "123", "extractor_key": "TikTok", "duration": 10}
        with (
            patch(
                "bot.services.downloader.yt_dlp.YoutubeDL",
                return_value=self._fake_ydl(info),
            ),
            patch(
                "bot.services.downloader.VideoInfo.from_info_dict",
                side_effect=RuntimeError("boom"),
            ),
        ):
            meta = _extract_metadata_sync("https://www.tiktok.com/@u/video/123")
        assert meta.info is None
        assert meta.duration == 10  # metadata itself still works


class TestInstagramMetadata:
    def _extract(self, raw, processed=None):
        ydl = MagicMock()
        ydl.extract_info.return_value = raw
        ydl.process_ie_result.return_value = processed
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=ydl)
        cm.__exit__ = MagicMock(return_value=False)
        with patch("bot.services.downloader.yt_dlp.YoutubeDL", return_value=cm):
            meta = _extract_metadata_sync("https://www.instagram.com/p/abc/")
        return meta, ydl

    def test_single_photo_uses_largest_image(self):
        raw = {
            "id": "abc",
            "extractor_key": "Instagram",
            "formats": [],
            "thumbnails": [
                {"url": "https://cdn/small.jpg", "width": 150},
                {"url": "https://cdn/full.jpg", "width": 1080},
            ],
        }

        meta, ydl = self._extract(raw)

        assert meta.media_items == [MediaItem(url="https://cdn/full.jpg", is_video=False)]
        ydl.process_ie_result.assert_not_called()

    def test_carousel_keeps_order_and_picks_best_progressive_video(self):
        raw = {
            "_type": "playlist",
            "id": "abc",
            "extractor_key": "Instagram",
            "entries": [
                {"formats": [], "thumbnails": [{"url": "https://cdn/photo.jpg", "width": 1080}]},
                {
                    "formats": [
                        {"format_id": "dash-hd", "url": "https://cdn/dash.mp4", "height": 1920},
                        {"format_id": "101", "url": "https://cdn/720.mp4", "height": 720},
                        {"format_id": "102", "url": "https://cdn/1080.mp4", "height": 1080},
                    ],
                    "thumbnails": [{"url": "https://cdn/cover.jpg", "width": 1080}],
                },
            ],
        }

        meta, _ = self._extract(raw)

        assert meta.media_items == [
            MediaItem(url="https://cdn/photo.jpg", is_video=False),
            MediaItem(url="https://cdn/1080.mp4", is_video=True),
        ]

    def test_single_video_goes_through_normal_processing(self):
        raw = {
            "id": "abc",
            "extractor_key": "Instagram",
            "formats": [{"format_id": "101", "url": "https://cdn/v.mp4"}],
        }

        meta, _ = self._extract(raw, processed={**raw, "duration": 12})

        assert meta.media_items == []
        assert meta.duration == 12


class TestDownloadInstagramMediaSync:
    PHOTO = MediaItem(url="https://cdn/p.jpg", is_video=False)
    VIDEO = MediaItem(url="https://cdn/v.mp4", is_video=True)

    def _urlopen(self, bodies):
        def fake(req, timeout):
            body = bodies[req.full_url]
            if isinstance(body, Exception):
                raise body
            return io.BytesIO(body)

        return patch("bot.services.downloader.urllib.request.urlopen", side_effect=fake)

    def test_oversized_video_is_skipped(self, tmp_path):
        bodies = {self.PHOTO.url: b"photo", self.VIDEO.url: b"x" * 100}

        with self._urlopen(bodies):
            files = _download_instagram_media_sync(
                [self.PHOTO, self.VIDEO], str(tmp_path), max_bytes=50
            )

        assert [f.is_video for f in files] == [False]
        assert os.listdir(tmp_path) == [os.path.basename(files[0].path)]

    def test_only_oversized_videos_raises_too_large(self, tmp_path):
        with self._urlopen({self.VIDEO.url: b"x" * 100}), pytest.raises(VideoDownloadError) as exc:
            _download_instagram_media_sync([self.VIDEO], str(tmp_path), max_bytes=50)

        assert exc.value.error_type == ErrorType.TOO_LARGE
        assert os.listdir(tmp_path) == []

    def test_network_failure_removes_partial_files(self, tmp_path):
        bodies = {self.PHOTO.url: b"photo", self.VIDEO.url: urllib.error.URLError("boom")}

        with self._urlopen(bodies), pytest.raises(VideoDownloadError) as exc:
            _download_instagram_media_sync([self.PHOTO, self.VIDEO], str(tmp_path), max_bytes=1000)

        assert exc.value.error_type == ErrorType.DOWNLOAD_ERROR
        assert os.listdir(tmp_path) == []
