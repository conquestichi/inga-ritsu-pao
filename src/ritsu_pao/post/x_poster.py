"""X API投稿モジュール — OAuth 1.0a + v2 endpoint

tweepy.Client で @ichiconquest に投稿。
script_x.json の body → メインツイート、self_reply → リプライ。
meta.json status != "ok" の場合はスキップ。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import tweepy

from ritsu_pao.schemas import MetaJson, ScriptXJson

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class XCredentials:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str

    @classmethod
    def from_json(cls, path: Path) -> XCredentials:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            consumer_key=data["consumer_key"],
            consumer_secret=data["consumer_secret"],
            access_token=data["access_token"],
            access_token_secret=data["access_token_secret"],
        )


@dataclass
class PostResult:
    """投稿結果"""

    success: bool
    tweet_id: str | None = None
    reply_id: str | None = None
    error: str | None = None


def _build_client(creds: XCredentials) -> tweepy.Client:
    """tweepy v2 Client を構築"""
    return tweepy.Client(
        consumer_key=creds.consumer_key,
        consumer_secret=creds.consumer_secret,
        access_token=creds.access_token,
        access_token_secret=creds.access_token_secret,
        wait_on_rate_limit=True,
    )


def post_tweet(
    script: ScriptXJson,
    meta: MetaJson,
    creds: XCredentials,
    *,
    dry_run: bool = False,
) -> PostResult:
    """X にツイート + 自己リプライを投稿

    Args:
        script: X投稿用台本 (script_x.json)
        meta: メタ情報 (meta.json)
        creds: X API認証情報
        dry_run: Trueの場合は実際に投稿せずログのみ

    Returns:
        PostResult: 投稿結果
    """
    # NO_POST チェック
    if meta.status != "ok":
        logger.info("Skipping X post: meta.status=%s", meta.status)
        return PostResult(success=True, error="skipped: no_post")

    # no_trade でも D パターンは投稿する
    body = script.body
    if not body or not body.strip():
        logger.warning("Empty body in script_x, skipping")
        return PostResult(success=False, error="empty body")

    if dry_run:
        logger.info("[DRY RUN] Tweet body (%d chars):\n%s", len(body), body)
        if script.self_reply:
            logger.info("[DRY RUN] Self-reply:\n%s", script.self_reply)
        return PostResult(success=True, tweet_id="dry_run", reply_id="dry_run")

    try:
        client = _build_client(creds)

        # メインツイート
        resp = client.create_tweet(text=body)
        tweet_id = str(resp.data["id"])
        logger.info("Posted tweet: id=%s, chars=%d", tweet_id, len(body))

        # 自己リプライ
        reply_id = None
        if script.self_reply and script.self_reply.strip():
            resp_reply = client.create_tweet(
                text=script.self_reply,
                in_reply_to_tweet_id=tweet_id,
            )
            reply_id = str(resp_reply.data["id"])
            logger.info("Posted self-reply: id=%s", reply_id)

        return PostResult(success=True, tweet_id=tweet_id, reply_id=reply_id)

    except tweepy.TweepyException as e:
        logger.error("X API error: %s", e)
        return PostResult(success=False, error=str(e))
    except Exception as e:
        logger.error("Unexpected error posting to X: %s", e)
        return PostResult(success=False, error=str(e))
