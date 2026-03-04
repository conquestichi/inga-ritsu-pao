"""test_youtube_uploader.py — YouTubeアップロードモジュールのテスト"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ritsu_pao.post.youtube_uploader import (
    UploadMeta,
    YouTubeCredentials,
    upload_video,
)


@pytest.fixture
def yt_creds(tmp_path: Path) -> YouTubeCredentials:
    secret = tmp_path / "client_secret.json"
    secret.write_text(json.dumps({"installed": {"client_id": "cid"}}))
    token = tmp_path / "youtube_token.json"
    token.write_text(json.dumps({
        "token": "access_tok",
        "refresh_token": "refresh_tok",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid",
        "client_secret": "csec",
    }))
    return YouTubeCredentials(client_secret_path=secret, token_path=token)


@pytest.fixture
def upload_meta() -> UploadMeta:
    return UploadMeta(
        title="明日上がる日本株｜2026-03-04｜因果律",
        description="学習AI 因果quantsが1800銘柄から選出",
        tags=["日本株", "AI", "因果律"],
        category_id="22",
        privacy_status="public",
    )


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    p = tmp_path / "final.mp4"
    p.write_bytes(b"\x00" * 1024)
    return p


class TestUploadMeta:
    def test_from_script(self) -> None:
        script = {
            "upload_meta": {
                "title": "テストタイトル",
                "description": "テスト説明",
                "tags": ["tag1", "tag2"],
                "category_id": "22",
                "privacy_status": "unlisted",
            }
        }
        meta = UploadMeta.from_script(script)
        assert meta.title == "テストタイトル"
        assert meta.privacy_status == "unlisted"
        assert len(meta.tags) == 2

    def test_from_script_defaults(self) -> None:
        meta = UploadMeta.from_script({})
        assert meta.title == "因果律 AI シグナル"
        assert meta.category_id == "22"
        assert meta.privacy_status == "public"


class TestUploadVideo:
    def test_missing_video(
        self, tmp_path: Path, upload_meta: UploadMeta, yt_creds: YouTubeCredentials
    ) -> None:
        missing = tmp_path / "nonexistent.mp4"
        result = upload_video(missing, upload_meta, yt_creds)
        assert result.success is False
        assert "not found" in (result.error or "")

    def test_dry_run(
        self, video_file: Path, upload_meta: UploadMeta, yt_creds: YouTubeCredentials
    ) -> None:
        result = upload_video(video_file, upload_meta, yt_creds, dry_run=True)
        assert result.success is True
        assert result.video_id == "dry_run"
        assert "youtube.com" in (result.url or "")

    @patch("ritsu_pao.post.youtube_uploader.build")
    @patch("ritsu_pao.post.youtube_uploader.Credentials")
    def test_upload_success(
        self,
        mock_creds_cls: MagicMock,
        mock_build: MagicMock,
        video_file: Path,
        upload_meta: UploadMeta,
        yt_creds: YouTubeCredentials,
    ) -> None:
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.valid = True
        mock_creds_cls.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "abc123"})
        mock_service.videos.return_value.insert.return_value = mock_request

        result = upload_video(video_file, upload_meta, yt_creds)
        assert result.success is True
        assert result.video_id == "abc123"
        assert result.url == "https://youtube.com/shorts/abc123"

    @patch("ritsu_pao.post.youtube_uploader.build")
    @patch("ritsu_pao.post.youtube_uploader.Credentials")
    def test_upload_api_error(
        self,
        mock_creds_cls: MagicMock,
        mock_build: MagicMock,
        video_file: Path,
        upload_meta: UploadMeta,
        yt_creds: YouTubeCredentials,
    ) -> None:
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.valid = True
        mock_creds_cls.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.videos.return_value.insert.side_effect = Exception("quota exceeded")

        result = upload_video(video_file, upload_meta, yt_creds)
        assert result.success is False
        assert "quota exceeded" in (result.error or "")


class TestCliYouTube:
    def test_cli_youtube_dry_run(self, tmp_path: Path) -> None:
        from ritsu_pao.post.cli import main

        pub = tmp_path / "publish"
        pub.mkdir()
        (pub / "meta.json").write_text(json.dumps({
            "date": "2026-03-04", "status": "ok",
            "generated_at": "2026-03-04T19:00:00", "run_id": "t1",
        }))
        (pub / "script_youtube.json").write_text(json.dumps({
            "status": "trade",
            "upload_meta": {
                "title": "test", "description": "desc",
                "tags": ["t1"], "category_id": "22", "privacy_status": "public",
            },
        }))
        (pub / "final.mp4").write_bytes(b"\x00" * 1024)

        secret = tmp_path / "client_secret.json"
        secret.write_text(json.dumps({"installed": {"client_id": "cid"}}))
        token = tmp_path / "youtube_token.json"
        token.write_text(json.dumps({
            "token": "t", "refresh_token": "r",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid", "client_secret": "csec",
        }))

        rc = main([
            "youtube", "--publish-dir", str(pub),
            "--client-secret", str(secret), "--token", str(token),
            "--dry-run",
        ])
        assert rc == 0
        assert (pub / "youtube_upload_result.json").exists()

    def test_cli_youtube_skip_no_post(self, tmp_path: Path) -> None:
        from ritsu_pao.post.cli import main

        pub = tmp_path / "publish"
        pub.mkdir()
        (pub / "meta.json").write_text(json.dumps({
            "date": "2026-03-04", "status": "no_post",
            "generated_at": "2026-03-04T19:00:00", "run_id": "t1",
        }))

        secret = tmp_path / "cs.json"
        secret.write_text("{}")
        token = tmp_path / "yt.json"
        token.write_text("{}")

        rc = main([
            "youtube", "--publish-dir", str(pub),
            "--client-secret", str(secret), "--token", str(token),
        ])
        assert rc == 0  # skip, not error

    def test_cli_youtube_missing_video(self, tmp_path: Path) -> None:
        from ritsu_pao.post.cli import main

        pub = tmp_path / "publish"
        pub.mkdir()
        (pub / "meta.json").write_text(json.dumps({
            "date": "2026-03-04", "status": "ok",
            "generated_at": "2026-03-04T19:00:00", "run_id": "t1",
        }))

        secret = tmp_path / "cs.json"
        secret.write_text("{}")
        token = tmp_path / "yt.json"
        token.write_text("{}")

        rc = main([
            "youtube", "--publish-dir", str(pub),
            "--client-secret", str(secret), "--token", str(token),
        ])
        assert rc == 1  # missing final.mp4
