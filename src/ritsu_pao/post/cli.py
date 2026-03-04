"""X投稿 CLIエントリ

Usage:
    python -m ritsu_pao.post.cli \
        --publish-dir /srv/inga/output/publish/latest \
        --credentials /srv/inga/config/x_credentials.json \
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ritsu_pao.post.x_poster import PostResult, XCredentials, post_tweet
from ritsu_pao.schemas import MetaJson, ScriptXJson

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="X投稿")
    parser.add_argument("--publish-dir", required=True, type=Path, help="publish出力ディレクトリ")
    parser.add_argument(
        "--credentials",
        required=True,
        type=Path,
        help="x_credentials.json のパス",
    )
    parser.add_argument("--dry-run", action="store_true", help="投稿せずログのみ")
    args = parser.parse_args(argv)

    publish_dir: Path = args.publish_dir
    creds_path: Path = args.credentials
    dry_run: bool = args.dry_run

    # ファイル存在チェック
    meta_path = publish_dir / "meta.json"
    script_path = publish_dir / "script_x.json"

    if not meta_path.exists():
        logger.error("meta.json not found: %s", meta_path)
        return 1

    if not script_path.exists():
        logger.error("script_x.json not found: %s", script_path)
        return 1

    if not creds_path.exists():
        logger.error("credentials not found: %s", creds_path)
        return 1

    # 読込
    meta = MetaJson(**_load_json(meta_path))
    script = ScriptXJson(**_load_json(script_path))
    creds = XCredentials.from_json(creds_path)

    # 投稿
    result: PostResult = post_tweet(script, meta, creds, dry_run=dry_run)

    if result.success:
        logger.info(
            "X post complete: tweet_id=%s, reply_id=%s",
            result.tweet_id,
            result.reply_id,
        )

        # 結果をJSONで保存（Slack通知用）
        result_path = publish_dir / "x_post_result.json"
        result_path.write_text(
            json.dumps(
                {
                    "success": result.success,
                    "tweet_id": result.tweet_id,
                    "reply_id": result.reply_id,
                    "dry_run": dry_run,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    else:
        logger.error("X post failed: %s", result.error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
