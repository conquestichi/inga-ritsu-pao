"""videoモジュールのテスト"""

from __future__ import annotations
from unittest.mock import MagicMock, patch
from ritsu_pao.video.compositor import build_telop_lines_from_script
from ritsu_pao.video.compositor import _build_telop_filter
from ritsu_pao.video.voicevox import VoicevoxClient


class TestBuildTelopLines:
    def test_trade_script(self):
        script = {"status": "trade", "upload_meta": {"title": "test"}, "body": "l1"}
        lines = build_telop_lines_from_script(script)
        assert len(lines) > 0

    def test_no_trade(self):
        script = {"status": "no_trade", "body": ""}
        lines = build_telop_lines_from_script(script)
        assert any("見送り" in ln for ln in lines)

    def test_max_12(self):
        body = "\n".join("line" + str(i) for i in range(20))
        script = {"status": "trade", "upload_meta": {"title": "t"}, "body": body}
        assert len(build_telop_lines_from_script(script)) <= 12


class TestTelopFilter:
    def test_single(self):
        assert "drawtext" in _build_telop_filter(["hello"])

    def test_multi(self):
        assert _build_telop_filter(["a", "b"]).count("drawtext") == 2

    def test_empty(self):
        assert _build_telop_filter([]) == ""


class TestVoicevoxClient:
    def test_unavailable(self):
        c = VoicevoxClient(base_url="http://localhost:99999")
        assert c.is_available() is False

    @patch("ritsu_pao.video.voicevox.httpx.get")
    def test_available(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="0.21")
        mock_get.return_value.raise_for_status = MagicMock()
        assert VoicevoxClient().is_available() is True
