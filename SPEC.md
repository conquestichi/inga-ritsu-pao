# SPEC.md — inga-ritsu-pao 実装仕様書

## 概要

因果quants (`inga-quants`) が日次生成する日本株シグナル (`candidates.json`) を、
X / YouTube Shorts / note 向けの台本・原稿に整形し、Slack配布するパイプライン。

## 入力契約

### candidates.json

inga-quants の `/srv/inga/output/latest/candidates.json` を入力とする。
スキーマは `src/ritsu_pao/schemas.py` の `CandidatesJson` で定義。

- `meta.as_of`: 対象日 (YYYY-MM-DD)
- `meta.run_id`: 実行ID
- `candidates[]`: スコア降順ソート済みの銘柄リスト (TOP 20)
  - `ticker`: 5桁ティッカー (表示時は4桁変換)
  - `score`: 総合スコア
  - `reasons_top3[]`: 根拠TOP3 (feature, z値, direction, note)
  - `risk_flags[]`: リスクフラグ
  - `events[]`: 直近イベント
  - `holding_window`: 保有想定期間

### gates_result.json

inga-quants の品質ゲート結果。`GatesResult` で定義。

- `all_passed`: 全ゲート通過フラグ
- `rejection_reasons[]`: 停止理由
- `regime`: `risk_on` / `risk_off`
- `wf_ic`: Walk-forward IC

## 出力契約 (publish/latest/)

### meta.json (常に生成)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| date | str | 対象日 |
| status | "ok" / "no_post" | ステータス |
| generated_at | str | 生成日時 (ISO8601) |
| rejection_reasons | list[str] | 停止理由 (no_post時) |
| quality_score | float? | WF IC |
| run_id | str | 実行ID |
| git_sha | str | gitコミット |

`status == "no_post"` の場合、meta.json のみ生成。他ファイルは生成しない。

### script_x.json (status=ok時)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| date | str | 対象日 |
| status | "trade" / "no_trade" | 判定 |
| body | str | X投稿本文 |
| self_reply | str | 自己リプ (免責+補足) |
| image | str? | 画像パス (V2) |
| meta | dict | ticker/score/regime等 |
| v2_experiment | dict? | A/B実験データ (V2) |

### script_youtube.json (status=ok時)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| date | str | 対象日 |
| status | "trade" / "no_trade" | 判定 |
| hook | str | 冒頭 (導入) |
| body | str | 本編 (レジーム+銘柄+根拠) |
| cta | str | 締め (免責+CTA) |
| voicepeak | dict | Voicepeak設定 (speaker/speed/pitch) |
| upload_meta | dict | YouTube API用メタ (title/description/tags) |
| v2_experiment | dict? | A/B実験データ (V2) |

### note.md (status=ok時)

因果quants出力をMarkdown形式で整形。TOP5銘柄のスコア・根拠・リスクフラグ・イベントを含む。
末尾に免責文を配置。

### candidates.json (status=ok時)

入力candidates.jsonのサニタイズ済みコピー。

### reply_config.json (status=ok時)

config/reply_config.json のコピー。自動返信モジュール (Phase 3) が参照。

## 台本生成ロジック

### テンプレ80% + 差分20%

- テンプレート: `config/templates_x.json`, `config/templates_youtube.json`
- ランダム選択で自然なバリエーション
- `{ticker_display}`, `{name}`, `{score}`, `{reason_summary}` 等の変数注入で差分を生成
- 律ペルソナに完全準拠 (一人称「僕」、です/ます調、断定禁止)

### 禁止ワードチェック

`reply_config.json` の `banned_words` でテンプレート出力を検証 (テストで保証)。

## Slack通知

### publish結果通知

`build_publish_report_blocks()`: ステータス、WF IC、X投稿プレビュー、生成ファイル一覧。

### note原稿配布

`build_note_distribution_blocks()`: note.mdの内容をBlock Kit形式で配布。
3000文字超は自動分割。

## パイプライン実行

```
bin/run_daily.sh
  → JPXカレンダーチェック (非営業日スキップ)
  → candidates.json存在チェック
  → python -m ritsu_pao.publish.publisher (全ファイル生成)
  → python -m ritsu_pao.notify.cli (Slack通知)
```

systemd timer: 平日19:00 JST (inga-quants 18:30完了後)

## Phase対応表

| Phase | 実装範囲 |
|-------|---------|
| Phase 1 | publish契約 + 台本生成 + Slack配布 ← **本SPEC** |
| Phase 2 | 動画制作 (Voicepeak + ffmpeg) |
| Phase 3 | X全自動化 (X API投稿 + Claude API返信) |
| Phase 4 | YouTube全自動化 (Data API + コメント返信) |
| Phase 5 | 監査/品質強化 |
