"""X投稿 / YouTube アップロード CLIエントリ

Usage (X):
    python -m ritsu_pao.post.cli x \
        --publish-dir /srv/inga/output/publish/latest \
        --credentials /srv/inga/config/x_credentials.json \
        [--dry-run]

Usage (YouTube):
    python -m ritsu_pao.post.cli youtube \
        --publish-dir /srv/inga/output/publish/latest \
        --client-secret /srv/inga/config/client_secret.json \
        --token /srv/inga/config/youtube_token.json \
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_result(publish_dir: Path, filename: str, data: dict) -> None:
    path = publish_dir / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── X投稿 ───


def cmd_x(args: argparse.Namespace) -> int:
    from ritsu_pao.post.x_poster import XCredentials, post_tweet
    from ritsu_pao.schemas import MetaJson, ScriptXJson

    publish_dir: Path = args.publish_dir
    meta_path = publish_dir / "meta.json"
    script_path = publish_dir / "script_x.json"

    if not meta_path.exists():
        logger.error("meta.json not found: %s", meta_path)
        return 1
    if not script_path.exists():
        logger.error("script_x.json not found: %s", script_path)
        return 1
    if not args.credentials.exists():
        logger.error("credentials not found: %s", args.credentials)
        return 1

    meta = MetaJson(**_load_json(meta_path))
    script = ScriptXJson(**_load_json(script_path))
    creds = XCredentials.from_json(args.credentials)

    result = post_tweet(script, meta, creds, dry_run=args.dry_run)

    if result.success:
        logger.info("X post complete: tweet_id=%s, reply_id=%s", result.tweet_id, result.reply_id)
        _save_result(publish_dir, "x_post_result.json", {
            "success": result.success,
            "tweet_id": result.tweet_id,
            "reply_id": result.reply_id,
            "dry_run": args.dry_run,
        })
        return 0
    else:
        logger.error("X post failed: %s", result.error)
        return 1


# ─── YouTubeアップロード ───


def cmd_youtube(args: argparse.Namespace) -> int:
    from ritsu_pao.post.youtube_uploader import UploadMeta, YouTubeCredentials, upload_video

    publish_dir: Path = args.publish_dir
    meta_path = publish_dir / "meta.json"
    script_path = publish_dir / "script_youtube.json"
    video_path = publish_dir / "final.mp4"

    if not meta_path.exists():
        logger.error("meta.json not found: %s", meta_path)
        return 1

    meta_data = _load_json(meta_path)
    if meta_data.get("status") != "ok":
        logger.info("Skipping YouTube upload: meta.status=%s", meta_data.get("status"))
        return 0

    if not video_path.exists():
        logger.error("final.mp4 not found: %s", video_path)
        return 1
    if not script_path.exists():
        logger.error("script_youtube.json not found: %s", script_path)
        return 1
    if not args.client_secret.exists():
        logger.error("client_secret not found: %s", args.client_secret)
        return 1
    if not args.token.exists():
        logger.error("youtube_token not found: %s", args.token)
        return 1

    script = _load_json(script_path)
    upload_meta = UploadMeta.from_script(script)
    creds = YouTubeCredentials(
        client_secret_path=args.client_secret,
        token_path=args.token,
    )

    result = upload_video(video_path, upload_meta, creds, dry_run=args.dry_run)

    if result.success:
        logger.info("YouTube upload complete: %s", result.url)
        _save_result(publish_dir, "youtube_upload_result.json", {
            "success": result.success,
            "video_id": result.video_id,
            "url": result.url,
            "dry_run": args.dry_run,
        })
        return 0
    else:
        logger.error("YouTube upload failed: %s", result.error)
        return 1


# ─── メインパーサー ───


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="因果律 投稿CLI")
    subparsers = parser.add_subparsers(dest="command")

    # X subcommand
    p_x = subparsers.add_parser("x", help="X投稿")
    p_x.add_argument("--publish-dir", required=True, type=Path)
    p_x.add_argument("--credentials", required=True, type=Path)
    p_x.add_argument("--dry-run", action="store_true")
    p_x.set_defaults(func=cmd_x)

    # YouTube subcommand
    p_yt = subparsers.add_parser("youtube", help="YouTubeアップロード")
    p_yt.add_argument("--publish-dir", required=True, type=Path)
    p_yt.add_argument("--client-secret", required=True, type=Path)
    p_yt.add_argument("--token", required=True, type=Path)
    p_yt.add_argument("--dry-run", action="store_true")
    p_yt.set_defaults(func=cmd_youtube)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
