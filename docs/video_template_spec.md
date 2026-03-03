# YouTube Shorts テンプレ動画 仕様書

## アーキテクチャ

```
[手作業(1回)] AE/DaVinci -> template_trade.mp4 / template_no_trade.mp4
[毎日自動]   script -> VOICEVOX音声 -> ffmpeg(テンプレ+音声+差分テキスト+律) -> final.mp4
```

## 動画仕様
- 解像度: 1080x1920 (9:16)
- fps: 30
- 長さ: 60秒 (音声に合わせて自動トリム)
- コーデック: H.264 CRF 18 / AAC 128k

## テンプレ1: template_trade.mp4

### レイアウト
```
+---------------------------+
|  ロゴ 因果律 (左上)         |  Y:40
+---------------------------+
|  [日付]           <- 注入  |  Y:140
|  [レジーム]       <- 注入  |  Y:220
+---------------------------+
|  銘柄テロップ帯             |  Y:300-420 帯アニメ(AE) テキスト注入(ffmpeg)
|  スコア 根拠帯              |  Y:440-620 帯アニメ(AE) テキスト注入(ffmpeg)
+---------------------------+
|                           |
|   律キャラクター            |  画面下部75% ffmpegクロマキー合成
|                           |
+---------------------------+
|  免責帯(常時)               |  Y:1840
+---------------------------+
```

### AEに含めるもの
1. 背景: ダークグラデーション (#0a0a1a -> #1a1a3e) + パーティクル/グリッド
2. ロゴ: 因果律 (左上 常時)
3. テロップ帯アニメ: 半透明黒帯スライドイン (0.5s)
4. レジーム枠: 角丸フレーム
5. 免責帯: 最下部 常時半透明
6. BGM: Lo-Fi/Ambient 著作権フリー
7. SE: テロップ出現時 (任意)

### ffmpegで日次注入
- 日付 / レジーム / 銘柄名 / スコア / 根拠テキスト
- VOICEVOX音声
- 律クリップ

## テンプレ2: template_no_trade.mp4
- 本日はシグナル見送り 固定テロップ
- やや暗めトーン
- ffmpeg注入: 日付 停止理由 音声 律

## テキスト注入座標

| テキスト | X | Y | size | color |
|---------|---|---|------|-------|
| 日付 | center | 140 | 44 | white |
| レジーム | center | 220 | 40 | #00ff88 or #ff4444 |
| 銘柄コード+名 | 80 | 330 | 64 | white |
| スコア | 80 | 420 | 48 | #ffd700 |
| 根拠1 | 80 | 480 | 36 | #cccccc |
| 根拠2 | 80 | 520 | 36 | #cccccc |
| 根拠3 | 80 | 560 | 36 | #cccccc |
| 保有想定 | 80 | 620 | 36 | #88aaff |

## アセット配置 /srv/inga/assets/

```
assets/
  template_trade.mp4       <- AE作成
  template_no_trade.mp4    <- AE作成
  ritsu_loop.mp4           <- VMM録画 (済)
  bgm_loop.mp3             <- 著作権フリー
  NotoSansJP-Bold.ttf      <- フォント
  logo_inga.png            <- ロゴ (任意)
```

## BGM候補 (著作権フリー)
- DOVA-SYNDROME: https://dova-s.jp/
- 甘茶の音楽工房: https://amachamusic.chagasi.com/
- YouTube Audio Library (商用利用可)

推奨: Lo-Fi / Ambient / Corporate (金融ニュース風)

## 暫定対応 (AE完成前)
1. Canvaで静止画背景 -> background.png 配置
2. フリーBGM -> bgm_loop.mp3 配置
3. ffmpegで合成 (現行パイプライン対応可)
