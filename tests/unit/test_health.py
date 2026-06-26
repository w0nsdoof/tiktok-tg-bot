import time
from types import SimpleNamespace

from bot.health import HEARTBEAT_FILENAME, heartbeat_job, heartbeat_path, write_heartbeat


class TestWriteHeartbeat:
    def test_creates_file_with_recent_epoch(self, tmp_path):
        before = int(time.time())
        write_heartbeat(str(tmp_path))
        path = tmp_path / HEARTBEAT_FILENAME
        assert path.exists()
        written = int(path.read_text())
        assert written >= before

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / HEARTBEAT_FILENAME
        path.write_text("0")
        write_heartbeat(str(tmp_path))
        assert int(path.read_text()) > 0

    def test_heartbeat_path_joins_filename(self, tmp_path):
        assert heartbeat_path(str(tmp_path)) == tmp_path / HEARTBEAT_FILENAME


class TestHeartbeatJob:
    async def test_job_writes_via_settings_data_dir(self, tmp_path):
        ctx = SimpleNamespace(bot_data={"settings": SimpleNamespace(data_dir=str(tmp_path))})
        await heartbeat_job(ctx)
        assert (tmp_path / HEARTBEAT_FILENAME).exists()
