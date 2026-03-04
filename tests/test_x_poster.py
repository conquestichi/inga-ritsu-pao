"""test_x_poster.py — X投稿モジュールのテスト"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ritsu_pao.post.x_poster import XCredentials, post_tweet
from ritsu_pao.schemas import MetaJson, PublishStatus, ScriptXJson


@pytest.fixture
def creds(tmp_path: Path) -> XCredentials:
    creds_data = {
        "consumer_key": "test_ck",
        "consumer_secret": "test_cs",
        "access_token": "test_at",
        "access_token_secret": "test_ats",
    }
    path = tmp_path / "x_credentials.json"
    path.write_text(json.dumps(creds_data), encoding="utf-8")
    return XCredentials.from_json(path)


@pytest.fixture
def meta_ok() -> MetaJson:
    return MetaJson(
        date="2026-03-04",
        status=PublishStatus.OK,
        generated_at="2026-03-04T19:00:00+09:00",
        run_id="test-001",
    )


@pytest.fixture
def meta_no_post() -> MetaJson:
    return MetaJson(
        date="2026-03-04",
        status=PublishStatus.NO_POST,
        generated_at="2026-03-04T19:00:00+09:00",
        run_id="test-001",
        rejection_reasons=["walk_forward_ic_low"],
    )


@pytest.fixture
def script_trade() -> ScriptXJson:
    return ScriptXJson(
        date="2026-03-04",
        status="trade",
        body="📊 因果律（2026-03-04）\n学習AI 因果quantsが1800銘柄から選出\n\n律の注目 → TDK（7203）",
        self_reply="律の撤退ライン：VWAP乖離が反転なら手を出しません。",
        meta={"ticker": "72030", "score": 85.3, "regime": "risk_on", "pattern": "A_number_hook"},
    )


@pytest.fixture
def script_no_trade() -> ScriptXJson:
    return ScriptXJson(
        date="2026-03-04",
        status="no_trade",
        body="⛔ 因果律（2026-03-04）\nレジーム：リスクオフ\n今日の律の結論 → 見送り",
        self_reply="",
        meta={"regime": "risk_off", "pattern": "D_warning"},
    )


class TestXCredentials:
    def test_from_json(self, tmp_path: Path) -> None:
        data = {
            "consumer_key": "ck",
            "consumer_secret": "cs",
            "access_token": "at",
            "access_token_secret": "ats",
        }
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        creds = XCredentials.from_json(path)
        assert creds.consumer_key == "ck"
        assert creds.consumer_secret == "cs"
        assert creds.access_token == "at"
        assert creds.access_token_secret == "ats"

    def test_from_json_missing_key(self, tmp_path: Path) -> None:
        data = {"consumer_key": "ck"}
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(KeyError):
            XCredentials.from_json(path)


class TestPostTweet:
    def test_skip_no_post(
        self, script_trade: ScriptXJson, meta_no_post: MetaJson, creds: XCredentials
    ) -> None:
        result = post_tweet(script_trade, meta_no_post, creds)
        assert result.success is True
        assert result.error == "skipped: no_post"
        assert result.tweet_id is None

    def test_dry_run(
        self, script_trade: ScriptXJson, meta_ok: MetaJson, creds: XCredentials
    ) -> None:
        result = post_tweet(script_trade, meta_ok, creds, dry_run=True)
        assert result.success is True
        assert result.tweet_id == "dry_run"
        assert result.reply_id == "dry_run"

    def test_dry_run_no_self_reply(
        self, script_no_trade: ScriptXJson, meta_ok: MetaJson, creds: XCredentials
    ) -> None:
        result = post_tweet(script_no_trade, meta_ok, creds, dry_run=True)
        assert result.success is True
        assert result.tweet_id == "dry_run"

    def test_empty_body(self, meta_ok: MetaJson, creds: XCredentials) -> None:
        script = ScriptXJson(date="2026-03-04", status="trade", body="", self_reply="")
        result = post_tweet(script, meta_ok, creds)
        assert result.success is False
        assert result.error == "empty body"

    @patch("ritsu_pao.post.x_poster._build_client")
    def test_post_with_reply(
        self,
        mock_build: MagicMock,
        script_trade: ScriptXJson,
        meta_ok: MetaJson,
        creds: XCredentials,
    ) -> None:
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        mock_client.create_tweet.side_effect = [
            MagicMock(data={"id": "111"}),
            MagicMock(data={"id": "222"}),
        ]

        result = post_tweet(script_trade, meta_ok, creds)
        assert result.success is True
        assert result.tweet_id == "111"
        assert result.reply_id == "222"
        assert mock_client.create_tweet.call_count == 2

        _, kwargs = mock_client.create_tweet.call_args_list[1]
        assert kwargs["in_reply_to_tweet_id"] == "111"

    @patch("ritsu_pao.post.x_poster._build_client")
    def test_post_no_self_reply(
        self,
        mock_build: MagicMock,
        script_no_trade: ScriptXJson,
        meta_ok: MetaJson,
        creds: XCredentials,
    ) -> None:
        mock_client = MagicMock()
        mock_build.return_value = mock_client
        mock_client.create_tweet.return_value = MagicMock(data={"id": "333"})

        result = post_tweet(script_no_trade, meta_ok, creds)
        assert result.success is True
        assert result.tweet_id == "333"
        assert result.reply_id is None
        assert mock_client.create_tweet.call_count == 1

    @patch("ritsu_pao.post.x_poster._build_client")
    def test_api_error(
        self,
        mock_build: MagicMock,
        script_trade: ScriptXJson,
        meta_ok: MetaJson,
        creds: XCredentials,
    ) -> None:
        import tweepy

        mock_client = MagicMock()
        mock_build.return_value = mock_client
        mock_client.create_tweet.side_effect = tweepy.TweepyException("rate limit")

        result = post_tweet(script_trade, meta_ok, creds)
        assert result.success is False
        assert "rate limit" in (result.error or "")


class TestCli:
    def test_cli_x_dry_run(self, tmp_path: Path) -> None:
        from ritsu_pao.post.cli import main

        pub = tmp_path / "publish"
        pub.mkdir()
        (pub / "meta.json").write_text(
            json.dumps({
                "date": "2026-03-04", "status": "ok",
                "generated_at": "2026-03-04T19:00:00", "run_id": "t1",
            })
        )
        (pub / "script_x.json").write_text(
            json.dumps({
                "date": "2026-03-04", "status": "trade",
                "body": "test tweet", "self_reply": "",
            })
        )

        creds = tmp_path / "creds.json"
        creds.write_text(
            json.dumps({
                "consumer_key": "ck", "consumer_secret": "cs",
                "access_token": "at", "access_token_secret": "ats",
            })
        )

        rc = main(["x", "--publish-dir", str(pub), "--credentials", str(creds), "--dry-run"])
        assert rc == 0
        assert (pub / "x_post_result.json").exists()

    def test_cli_x_missing_meta(self, tmp_path: Path) -> None:
        from ritsu_pao.post.cli import main

        pub = tmp_path / "publish"
        pub.mkdir()
        creds = tmp_path / "creds.json"
        creds.write_text("{}")

        rc = main(["x", "--publish-dir", str(pub), "--credentials", str(creds)])
        assert rc == 1
