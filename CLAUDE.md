# CLAUDE.md — inga-ritsu-pao 作業規約

## プロジェクト概要
「AI日本株クオンツ 因果律」メディア配信パイプライン。
因果quants が日次生成する日本株シグナルを X / YouTube Shorts / note に自動配信する。

## リポジトリ
- 配信側: /srv/inga/inga-ritsu-pao (このリポ)
- シグナル側: /srv/inga/inga-quants

## 開発ルール
1. Python 3.11+, type hints 必須
2. テスト: pytest, カバレッジ80%目標
3. フォーマット: ruff (line-length=100)
4. コミットメッセージ: Conventional Commits (feat/fix/chore/docs)
5. ブランチ: main → feature/xxx → PR → merge
6. 機密情報: .env + .gitignore, コードに絶対埋め込まない

## 出力パス
- VPS: /srv/inga/output/publish/latest/
- 入力: /srv/inga/output/latest/candidates.json (inga-quants出力)

## 律ペルソナ (全出力に適用)
- 一人称: 律
- 口調: です/ます調
- 禁止: 断定・下品・攻撃的表現
- 必須: 免責意識、根拠説明

## Phase 1 スコープ
- publish契約 (script_x.json / script_youtube.json / note.md / meta.json)
- 台本生成モジュール (テンプレ80% + 差分20%)
- reply_config.json
- Slack Block Kit拡張 (note原稿配布)

## Phase 3 スコープ
- X API投稿モジュール (tweepy OAuth 1.0a → v2 endpoint)
- post/x_poster.py: body投稿 + self_reply
- post/cli.py: CLIエントリ (x / youtube サブコマンド, --dry-run)
- 認証情報: /srv/inga/config/x_credentials.json (gitignore対象)
- 投稿先: @ichiconquest

## Phase 4 スコープ
- YouTube Data API v3 アップロードモジュール
- post/youtube_uploader.py: OAuth2 refresh_token + resumable upload
- 認証情報: /srv/inga/config/client_secret.json, youtube_token.json
- run_daily.sh: 19:00 publish/動画生成 → 20:00 X/YouTube投稿
