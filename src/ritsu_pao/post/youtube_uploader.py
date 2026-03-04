"""YouTube Data API v3 アップロードモジュール

OAuth 2.0 (refresh_token) で認証し、Shorts動画をアップロード。
script_youtube.json の upload_meta からタイトル・説明・タグを自動生成。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


@dataclass(frozen=True)
class YouTubeCredentials:
    client_secret_path: Path
    token_path: Path

    def get_authenticated_service(self):
        """refresh_token付きCredentialsからYouTube APIサービスを構築"""
        token_data = json.loads(self.token_path.read_text(encoding="utf-8"))

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=SCOPES,
        )

        # トークン期限切れ時に自動リフレッシュ
        if creds.expired or not creds.valid:
            creds.refresh(Request())
            # リフレッシュ後のトークンを保存
            token_data["token"] = creds.token
            self.token_path.write_text(
                json.dumps(token_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("YouTube token refreshed and saved")

        return build("youtube", "v3", credentials=creds)


@dataclass
class UploadResult:
    """アップロード結果"""

    success: bool
    video_id: str | None = None
    url: str | None = None
    error: str | None = None


@dataclass
class UploadMeta:
    """アップロード用メタデータ"""

    title: str
    description: str
    tags: list[str]
    category_id: str = "22"  # People & Blogs
    privacy_status: str = "public"

    @classmethod
    def from_script(cls, script: dict) -> UploadMeta:
        """script_youtube.json の upload_meta から生成"""
        meta = script.get("upload_meta", {})
        return cls(
            title=meta.get("title", "因果律 AI シグナル"),
            description=meta.get("description", ""),
            tags=meta.get("tags", ["日本株", "AI", "因果律"]),
            category_id=meta.get("category_id", "22"),
            privacy_status=meta.get("privacy_status", "public"),
        )


def upload_video(
    video_path: Path,
    upload_meta: UploadMeta,
    creds: YouTubeCredentials,
    *,
    dry_run: bool = False,
) -> UploadResult:
    """YouTube Shorts に動画をアップロード

    Args:
        video_path: final.mp4 のパス
        upload_meta: タイトル・説明・タグ等
        creds: YouTube OAuth認証情報
        dry_run: Trueの場合は実際にアップロードせずログのみ

    Returns:
        UploadResult: アップロード結果
    """
    if not video_path.exists():
        return UploadResult(success=False, error=f"Video not found: {video_path}")

    # ファイルサイズチェック（Shorts: 60秒以内、通常は数MB）
    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    logger.info("Video file: %s (%.1f MB)", video_path, file_size_mb)

    if dry_run:
        logger.info("[DRY RUN] Would upload: %s", upload_meta.title)
        logger.info("[DRY RUN] Description: %s", upload_meta.description[:100])
        logger.info("[DRY RUN] Tags: %s", upload_meta.tags)
        logger.info("[DRY RUN] Privacy: %s", upload_meta.privacy_status)
        return UploadResult(success=True, video_id="dry_run", url="https://youtube.com/shorts/dry_run")

    try:
        youtube = creds.get_authenticated_service()

        body = {
            "snippet": {
                "title": upload_meta.title,
                "description": upload_meta.description,
                "tags": upload_meta.tags,
                "categoryId": upload_meta.category_id,
            },
            "status": {
                "privacyStatus": upload_meta.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        # resumableアップロード実行
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %d%%", int(status.progress() * 100))

        video_id = response["id"]
        url = f"https://youtube.com/shorts/{video_id}"
        logger.info("Upload complete: %s → %s", upload_meta.title, url)

        return UploadResult(success=True, video_id=video_id, url=url)

    except Exception as e:
        logger.error("YouTube upload error: %s", e)
        return UploadResult(success=False, error=str(e))
