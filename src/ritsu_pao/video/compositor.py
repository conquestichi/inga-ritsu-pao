"""ffmpeg動画合成 -- テンプレ動画 + 差分注入 or フォールバック合成

YouTube Shorts仕様: 1080x1920 (9:16), 60秒以下

モード:
  1. テンプレモード: AE製テンプレ動画 + 差分テキスト + 音声 + 律クリップ
  2. フォールバック: 単色/画像背景 + テロップ + 音声 + 律クリップ
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
BG_COLOR = "#0a0a1a"
FONT_COLOR = "white"

# テンプレモード: テキスト注入座標
TEXT_LAYOUT = {
    "date":    {"x": "(w-text_w)/2", "y": 140, "size": 76, "color": "white"},
    "regime":  {"x": "(w-text_w)/2", "y": 220, "size": 68, "color": "#00ff88"},
    "ticker":  {"x": 80, "y": 330, "size": 110, "color": "white"},
    "score":   {"x": 80, "y": 420, "size": 80, "color": "#ffd700"},
    "reason1": {"x": 80, "y": 480, "size": 62, "color": "#cccccc"},
    "reason2": {"x": 80, "y": 520, "size": 62, "color": "#cccccc"},
    "reason3": {"x": 80, "y": 560, "size": 62, "color": "#cccccc"},
    "holding": {"x": 80, "y": 620, "size": 62, "color": "#88aaff"},
}

# フォールバックモード: テロップ設定
TELOP_FONT_SIZE = 88
TELOP_Y_START = 80


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _get_audio_duration(wav_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json", str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _escape_drawtext(text: str) -> str:
    return text.replace("'", "'\\''").replace(":", "\\:").replace("\\", "\\\\")


def _drawtext(
    text: str,
    x: int | str,
    y: int,
    size: int,
    color: str,
    font_path: str | None = None,
    border: int = 3,
) -> str:
    escaped = _escape_drawtext(text)
    font_opt = f":fontfile={font_path}" if font_path else ""
    return (
        f"drawtext=text='{escaped}'"
        f":fontsize={size}:fontcolor={color}"
        f":x={x}:y={y}"
        f":borderw={border}:bordercolor=black"
        f"{font_opt}"
    )


# ── テンプレモード ──


def _build_template_text_filters(
    script: dict,
    font_path: str | None = None,
) -> list[str]:
    """script_youtube.jsonからテンプレ用drawtext群を生成"""
    filters: list[str] = []
    lay = TEXT_LAYOUT

    # 日付
    as_of = script.get("as_of", "")
    if as_of:
        pos = lay["date"]
        filters.append(_drawtext(as_of, pos["x"], pos["y"], pos["size"], pos["color"], font_path))

    if script.get("status") != "trade":
        # no_trade
        filters.append(_drawtext(
            "本日はシグナル見送り", "(w-text_w)/2", 400, 56, "#ff6666", font_path,
        ))
        reason = script.get("rejection_reason", "")
        if reason:
            filters.append(_drawtext(reason, "(w-text_w)/2", 480, 36, "#cccccc", font_path))
        return filters

    # レジーム
    regime = script.get("regime", "")
    if regime:
        color = "#00ff88" if regime == "risk_on" else "#ff4444"
        label = "RISK ON" if regime == "risk_on" else "RISK OFF"
        pos = lay["regime"]
        filters.append(_drawtext(label, pos["x"], pos["y"], pos["size"], color, font_path))

    # 銘柄
    ticker = script.get("ticker_display", "")
    name = script.get("name", "")
    if ticker or name:
        pos = lay["ticker"]
        filters.append(_drawtext(
            f"{ticker}  {name}", pos["x"], pos["y"], pos["size"], pos["color"], font_path,
        ))

    # スコア
    score = script.get("score")
    if score is not None:
        pos = lay["score"]
        filters.append(_drawtext(
            f"Score: {score}", pos["x"], pos["y"], pos["size"], pos["color"], font_path,
        ))

    # 根拠 (最大3行)
    reasons = script.get("reasons_display", [])
    for i, reason in enumerate(reasons[:3]):
        key = f"reason{i + 1}"
        if key in lay:
            pos = lay[key]
            text = reason[:45] + "..." if len(reason) > 45 else reason
            filters.append(_drawtext(text, pos["x"], pos["y"], pos["size"], pos["color"], font_path))

    # 保有想定
    holding = script.get("holding_window", "")
    if holding:
        pos = lay["holding"]
        filters.append(_drawtext(
            f"想定保有: {holding}", pos["x"], pos["y"], pos["size"], pos["color"], font_path,
        ))

    return filters


def compose_shorts_template(
    template_path: Path,
    audio_path: Path,
    output_path: Path,
    script: dict,
    character_clip: Path | None = None,
    bgm_path: Path | None = None,
    font_path: str | None = None,
) -> Path:
    """テンプレ動画 + 差分注入で高品質Shorts生成"""
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg not found")

    duration = _get_audio_duration(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_parts: list[str] = []
    inputs: list[str] = []
    input_idx = 0

    # 入力0: テンプレ動画
    inputs.extend(["-stream_loop", "-1", "-i", str(template_path)])
    filter_parts.append(f"[{input_idx}:v]setsar=1[tmpl]")
    tmpl_audio_idx = input_idx
    input_idx += 1

    # 入力1: VOICEVOX音声
    inputs.extend(["-i", str(audio_path)])
    voice_idx = input_idx
    input_idx += 1

    # 入力2: BGM (任意)
    bgm_idx = None
    if bgm_path and bgm_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
        bgm_idx = input_idx
        input_idx += 1

    # キャラクターオーバーレイ
    current_layer = "tmpl"
    if character_clip and character_clip.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(character_clip)])
        char_idx = input_idx
        input_idx += 1
        if str(character_clip).endswith(".webm"):
            filter_parts.append(f"[{char_idx}:v]scale=-1:{int(SHORTS_HEIGHT * 0.75)}[char]")
        else:
            filter_parts.append(
                f"[{char_idx}:v]chromakey=0x00FF00:0.12:0.08,"
                f"scale=-1:{int(SHORTS_HEIGHT * 0.75)}[char]"
            )
        filter_parts.append(
            f"[{current_layer}][char]overlay=(W-w)/2:H-h:shortest=1[with_char]"
        )
        current_layer = "with_char"

    # テキスト注入
    text_filters = _build_template_text_filters(script, font_path)
    if text_filters:
        all_text = ",".join(text_filters)
        filter_parts.append(f"[{current_layer}]{all_text}[with_text]")
        current_layer = "with_text"

    # 音声ミックス: VOICEVOX + BGM(テンプレ内BGMまたは別ファイル)
    if bgm_idx is not None:
        # 外部BGM + VOICEVOX: BGM音量下げてミックス
        filter_parts.append(
            f"[{bgm_idx}:a]volume=0.15[bgm_low];"
            f"[{voice_idx}:a][bgm_low]amix=inputs=2:duration=first[audio_out]"
        )
        audio_map = "[audio_out]"
    elif template_path.suffix == ".mp4":
        # テンプレ内蔵BGM + VOICEVOX
        filter_parts.append(
            f"[{tmpl_audio_idx}:a]volume=0.15[tmpl_low];"
            f"[{voice_idx}:a][tmpl_low]amix=inputs=2:duration=first[audio_out]"
        )
        audio_map = "[audio_out]"
    else:
        audio_map = f"{voice_idx}:a"

    filter_complex = ";".join(filter_parts)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{current_layer}]", "-map", audio_map,
        "-t", str(duration + 1.0),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", "30",
        str(output_path),
    ]
    logger.info("Running ffmpeg (template mode)")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg failed:\n%s", result.stderr[-1000:])
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    logger.info("Video generated (template): %s (%.1fs)", output_path, duration)
    return output_path


# ── シーン切替モード (背景画像複数枚) ──


# ─── 固定字幕 (シーンごと切替) ───

SUBTITLE_Y = 420  # 字幕Y位置 (中央やや上)
SUBTITLE_FONT_SIZE = 56
SUBTITLE_BAND_HEIGHT = 220
SUBTITLE_MAX_CHARS = 20  # 1行最大文字数

# ─── 下腹部リロール (常時表示) ───

TICKER_TEXT = "AI  quants  因果律  学習システム  24時間稼働中  短期日本株  未来予測中  "
TICKER_Y_OFFSET = 160  # 画面下端からのオフセット
TICKER_FONT_SIZE = 52
TICKER_SPEED = 169  # px/sec
TICKER_BAND_HEIGHT = 78


def _scene_to_spoken_text(scene_key: str, script: dict) -> str:
    """シーンキーから読み上げテキストを取得"""
    if scene_key == "title_card":
        return ""
    if scene_key == "intro":
        return script.get("hook", "")
    if scene_key in ("ticker", "reason"):
        return script.get("body", "")
    if scene_key == "cta":
        return script.get("cta", "")
    if scene_key == "no_trade":
        return script.get("body", "")
    return ""


def _wrap_lines(text: str, max_chars: int = SUBTITLE_MAX_CHARS) -> list[str]:
    """長いテキストを句読点 or max_chars で複数行に分割"""
    import re
    # 句読点で分割
    parts = re.split(r"(?<=[。、．，])", text)
    lines: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current + part) > max_chars:
            lines.append(current)
            current = part
        else:
            current += part
    if current:
        lines.append(current)
    # max_chars超えの行をさらに折り返し
    result: list[str] = []
    for line in lines:
        while len(line) > max_chars:
            result.append(line[:max_chars])
            line = line[max_chars:]
        if line:
            result.append(line)
    return result[:3]  # 最大3行


def _build_fixed_subtitle(
    scenes: list[tuple[str, float, float]],
    script: dict,
    font_path: str | None,
) -> list[str]:
    """シーンごとに固定字幕を表示（切替式）"""
    filters: list[str] = []
    seen_texts: set[str] = set()

    for scene_key, start, end in scenes:
        text = _scene_to_spoken_text(scene_key, script)
        if not text:
            continue

        # body が ticker/reason で重複する場合は前半/後半に分割
        if scene_key == "ticker" and text == script.get("body", ""):
            mid = len(text) // 2
            cut = text.rfind("。", 0, mid + 10)
            if cut == -1:
                cut = text.rfind("、", 0, mid + 10)
            if cut == -1:
                cut = mid
            text = text[: cut + 1]
        elif scene_key == "reason" and text == script.get("body", ""):
            mid = len(text) // 2
            cut = text.rfind("。", 0, mid + 10)
            if cut == -1:
                cut = text.rfind("、", 0, mid + 10)
            if cut == -1:
                cut = mid
            text = text[cut + 1 :]

        text_key = f"{scene_key}:{text}"
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        enable = f"between(t\\,{start:.2f}\\,{end:.2f})"
        font_opt = f":fontfile={font_path}" if font_path else ""

        # 半透明帯
        band = (
            f"drawbox=x=0:y={SUBTITLE_Y - 10}"
            f":w=iw:h={SUBTITLE_BAND_HEIGHT}"
            f":color=black@0.5:t=fill"
            f":enable='{enable}'"
        )
        filters.append(band)

        # 行分割して中央寄せ固定表示
        lines = _wrap_lines(text)
        line_height = SUBTITLE_FONT_SIZE + 12
        for i, line in enumerate(lines):
            escaped = _escape_drawtext(line)
            y = SUBTITLE_Y + 4 + i * line_height
            dt = (
                f"drawtext=text='{escaped}'"
                f":fontsize={SUBTITLE_FONT_SIZE}:fontcolor=white"
                f":x=(w-text_w)/2:y={y}"
                f":borderw=2:bordercolor=black"
                f"{font_opt}"
                f":enable='{enable}'"
            )
            filters.append(dt)

    return filters


def _build_bottom_ticker(
    font_path: str | None,
    total_duration: float,
) -> list[str]:
    """画面下部の右スクロールリロール (常時表示)"""
    h = SHORTS_HEIGHT
    y = h - TICKER_Y_OFFSET
    escaped = _escape_drawtext(TICKER_TEXT * 3)  # 3回繰り返してループ感
    font_opt = f":fontfile={font_path}" if font_path else ""

    filters = []
    # 半透明帯
    band = (
        f"drawbox=x=0:y={y - 8}"
        f":w=iw:h={TICKER_BAND_HEIGHT}"
        f":color=black@0.4:t=fill"
    )
    filters.append(band)

    # 右スクロール: 左端から入って右端へ出る
    scroll = (
        f"drawtext=text='{escaped}'"
        f":fontsize={TICKER_FONT_SIZE}:fontcolor=#88ccff"
        f":x='mod(t*{TICKER_SPEED}\\,text_w+w)-text_w'"
        f":y={y}"
        f":borderw=1:bordercolor=black@0.6"
        f"{font_opt}"
    )
    filters.append(scroll)

    return filters


def _build_scene_text(
    scene_key: str,
    script: dict,
    font_path: str | None,
    enable_expr: str,
) -> list[str]:
    """シーンごとのdrawtextフィルタ群を生成（enable付き）"""
    filters: list[str] = []

    def _dt(text: str, x: int | str, y: int, size: int, color: str) -> str:
        escaped = _escape_drawtext(text)
        font_opt = f":fontfile={font_path}" if font_path else ""
        return (
            f"drawtext=text='{escaped}'"
            f":fontsize={size}:fontcolor={color}"
            f":x={x}:y={y}"
            f":borderw=3:bordercolor=black"
            f"{font_opt}"
            f":enable='{enable_expr}'"
        )

    if scene_key == "title_card":
        tc = script.get("title_card", {})
        text = tc.get("text", "明日上がる日本株")
        sub_text = tc.get("sub_text", "")
        tc_font_size = tc.get("font_size", 122)
        tc_sub_font_size = tc.get("sub_font_size", 62)
        filters.append(_dt(text, "(w-text_w)/2", 740, tc_font_size, "white"))
        if sub_text:
            filters.append(_dt(sub_text, "(w-text_w)/2", 920, tc_sub_font_size, "#aaaaaa"))

    elif scene_key == "intro":
        as_of = script.get("as_of", "")
        if as_of:
            filters.append(_dt(as_of, "(w-text_w)/2", 140, 88, "white"))
        filters.append(_dt("因果律", "(w-text_w)/2", 220, 122, "#00eeff"))
        regime = script.get("regime", "")
        if regime:
            color = "#00ff88" if regime == "risk_on" else "#ff4444"
            label = "RISK ON" if regime == "risk_on" else "RISK OFF"
            filters.append(_dt(label, "(w-text_w)/2", 340, 80, color))

    elif scene_key == "ticker":
        ticker = script.get("ticker_display", "")
        name = script.get("name", "")
        if ticker or name:
            filters.append(_dt(f"{ticker}  {name}", "(w-text_w)/2", 160, 114, "white"))
        score = script.get("score")
        if score is not None:
            filters.append(_dt(f"Score: {score}", "(w-text_w)/2", 270, 88, "#ffd700"))

    elif scene_key == "reason":
        reasons = script.get("reasons_display", [])
        for i, reason in enumerate(reasons[:3]):
            text = reason[:40] + "..." if len(reason) > 40 else reason
            filters.append(_dt(text, "(w-text_w)/2", 160 + i * 104, 68, "#cccccc"))
        holding = script.get("holding_window", "")
        if holding:
            filters.append(_dt(f"想定保有: {holding}", "(w-text_w)/2", 420, 68, "#88aaff"))

    elif scene_key == "cta":
        pass  # CTAテキストは音声で読み上げ。免責はプロフィール欄に掲載

    elif scene_key == "no_trade":
        filters.append(_dt("本日はシグナル見送り", "(w-text_w)/2", 200, 94, "#ff6666"))
        reason = script.get("rejection_reason", "")
        if reason:
            filters.append(_dt(reason, "(w-text_w)/2", 300, 62, "#cccccc"))

    return filters


def compose_shorts_scenes(
    audio_path: Path,
    audio_segments: dict[str, Path],
    output_path: Path,
    script: dict,
    scene_backgrounds: dict[str, Path],
    character_clip: Path | None = None,
    bgm_path: Path | None = None,
    font_path: str | None = None,
    title_card: dict | None = None,
) -> Path:
    """シーン切替合成: 背景画像をシーンごとに切替 + テキスト + 律 + BGM

    Args:
        audio_path: full.wav (全セグメント結合済み)
        audio_segments: {"hook": hook.wav, "body": body.wav, "cta": cta.wav}
        scene_backgrounds: {"intro": path, "ticker": path, "reason": path, "cta": path}
        title_card: {"text": str, "sub_text": str, "duration_sec": float, ...}
        ...
    """
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg not found")

    duration = _get_audio_duration(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = SHORTS_WIDTH, SHORTS_HEIGHT

    # タイトルカード時間
    tc_dur = 0.0
    if title_card:
        tc_dur = title_card.get("duration_sec", 1.5)

    # シーンタイミング計算
    seg_durations = {}
    for key, path in audio_segments.items():
        if path.exists():
            seg_durations[key] = _get_audio_duration(path)

    hook_dur = seg_durations.get("hook", duration * 0.2)
    body_dur = seg_durations.get("body", duration * 0.5)

    is_trade = script.get("status", "trade") == "trade"

    scenes: list[tuple[str, float, float]] = []

    # タイトルカードシーン (音声なし、黒背景)
    if title_card:
        scenes.append(("title_card", 0.0, tc_dur))

    if is_trade:
        scenes.extend([
            ("intro", tc_dur, tc_dur + hook_dur),
            ("ticker", tc_dur + hook_dur, tc_dur + hook_dur + body_dur * 0.5),
            ("reason", tc_dur + hook_dur + body_dur * 0.5, tc_dur + hook_dur + body_dur),
            ("cta", tc_dur + hook_dur + body_dur, tc_dur + duration + 0.5),
        ])
    else:
        scenes.append(("no_trade", tc_dur, tc_dur + duration + 0.5))

    total_duration = tc_dur + duration + 0.5

    # ffmpegコマンド組立
    inputs: list[str] = []
    filter_parts: list[str] = []
    input_idx = 0

    # タイトルカード背景 (黒色lavfi)
    tc_bg_idx = None
    if title_card:
        inputs.extend([
            "-f", "lavfi", "-i",
            f"color=c=black:s={w}x{h}:d={tc_dur}:r=30",
        ])
        tc_bg_idx = input_idx
        filter_parts.append(f"[{input_idx}:v]setsar=1[bg_title_card]")
        input_idx += 1

    # 背景画像を入力として追加
    bg_indices: dict[str, int] = {}
    for scene_key, _, _ in scenes:
        if scene_key == "title_card" or scene_key in bg_indices:
            continue
        bg_path = scene_backgrounds.get(scene_key)
        if bg_path and bg_path.exists():
            inputs.extend(["-loop", "1", "-i", str(bg_path)])
            bg_indices[scene_key] = input_idx
            filter_parts.append(
                f"[{input_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1[bg_{scene_key}]"
            )
            input_idx += 1

    # シーン切替: 各背景にtrim+setpts → concat
    concat_inputs = []
    for scene_key, start, end in scenes:
        scene_dur = end - start
        if scene_key == "title_card" and tc_bg_idx is not None:
            label = "scene_title_card"
            filter_parts.append(
                f"[bg_title_card]trim=duration={scene_dur:.2f},setpts=PTS-STARTPTS[{label}]"
            )
            concat_inputs.append(f"[{label}]")
        elif scene_key in bg_indices:
            label = f"scene_{scene_key}"
            filter_parts.append(
                f"[bg_{scene_key}]trim=duration={scene_dur:.2f},setpts=PTS-STARTPTS[{label}]"
            )
            concat_inputs.append(f"[{label}]")

    if concat_inputs:
        n = len(concat_inputs)
        concat_str = "".join(concat_inputs)
        filter_parts.append(f"{concat_str}concat=n={n}:v=1:a=0[bg_concat]")
        current_layer = "bg_concat"
    else:
        # フォールバック: 単色
        inputs.extend([
            "-f", "lavfi", "-i",
            f"color=c={BG_COLOR}:s={w}x{h}:d={duration}:r=30",
        ])
        filter_parts.append(f"[{input_idx}:v]setsar=1[bg_concat]")
        current_layer = "bg_concat"
        input_idx += 1

    # 音声入力
    inputs.extend(["-i", str(audio_path)])
    voice_idx = input_idx
    input_idx += 1

    # タイトルカードがある場合、音声を遅延
    if tc_dur > 0:
        delay_ms = int(tc_dur * 1000)
        filter_parts.append(
            f"[{voice_idx}:a]adelay={delay_ms}|{delay_ms}[voice_delayed]"
        )
        voice_label = "voice_delayed"
    else:
        voice_label = f"{voice_idx}:a"

    # BGM
    bgm_idx = None
    if bgm_path and bgm_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
        bgm_idx = input_idx
        input_idx += 1

    # キャラクターオーバーレイ
    if character_clip and character_clip.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(character_clip)])
        char_idx = input_idx
        input_idx += 1
        if str(character_clip).endswith(".webm"):
            filter_parts.append(f"[{char_idx}:v]scale=-1:{int(h * 0.75)}[char]")
        else:
            filter_parts.append(
                f"[{char_idx}:v]chromakey=0x00FF00:0.12:0.08,"
                f"scale=-1:{int(h * 0.75)}[char]"
            )
        filter_parts.append(
            f"[{current_layer}][char]overlay=(W-w)/2:H-h:shortest=1[with_char]"
        )
        current_layer = "with_char"

    # シーンごとのテキスト注入 (enable付き)
    all_text_filters: list[str] = []
    for scene_key, start, end in scenes:
        enable = f"between(t\\,{start:.2f}\\,{end:.2f})"
        scene_texts = _build_scene_text(scene_key, script, font_path, enable)
        all_text_filters.extend(scene_texts)

    if all_text_filters:
        text_chain = ",".join(all_text_filters)
        filter_parts.append(f"[{current_layer}]{text_chain}[with_text]")
        current_layer = "with_text"

    # 固定字幕 (シーンごと切替)
    sub_filters = _build_fixed_subtitle(scenes, script, font_path)
    if sub_filters:
        sub_chain = ",".join(sub_filters)
        filter_parts.append(f"[{current_layer}]{sub_chain}[with_scroll]")
        current_layer = "with_scroll"

    # 下腹部リロール (右スクロール、常時表示)
    ticker_filters = _build_bottom_ticker(font_path, total_duration)
    if ticker_filters:
        ticker_chain = ",".join(ticker_filters)
        filter_parts.append(f"[{current_layer}]{ticker_chain}[with_ticker]")
        current_layer = "with_ticker"

    # 最終レイヤー確定 (免責テロップは動画外 — プロフィール欄に掲載)
    filter_parts.append(f"[{current_layer}]null[final]")
    current_layer = "final"

    # 音声ミックス
    if bgm_idx is not None:
        filter_parts.append(
            f"[{bgm_idx}:a]volume=0.12[bgm_low];"
            f"[{voice_label}][bgm_low]amix=inputs=2:duration=first[audio_out]"
        )
        audio_map = "[audio_out]"
    else:
        audio_map = f"[{voice_label}]" if tc_dur > 0 else f"{voice_idx}:a"

    filter_complex = ";".join(filter_parts)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{current_layer}]", "-map", audio_map,
        "-t", str(total_duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", "30",
        str(output_path),
    ]
    logger.info("Running ffmpeg (scenes mode, %d scenes)", len(scenes))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg failed:\n%s", result.stderr[-1500:])
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    logger.info("Video generated (scenes): %s (%.1fs)", output_path, duration)
    return output_path


def _build_telop_filter(
    lines: list[str],
    font_path: str | None = None,
    font_size: int = TELOP_FONT_SIZE,
    y_start: int = TELOP_Y_START,
    line_height: int = 60,
) -> str:
    filters: list[str] = []
    font_opt = f":fontfile={font_path}" if font_path else ""
    for i, line in enumerate(lines):
        escaped = line.replace("'", "'\\''").replace(":", "\\:")
        y = y_start + i * line_height
        f = (
            f"drawtext=text='{escaped}'"
            f":fontsize={font_size}"
            f":fontcolor={FONT_COLOR}"
            f":x=(w-text_w)/2:y={y}"
            f":borderw=3:bordercolor=black"
            f"{font_opt}"
        )
        filters.append(f)
    return ",".join(filters)


def compose_shorts(
    audio_path: Path,
    output_path: Path,
    telop_lines: list[str],
    character_clip: Path | None = None,
    background_image: Path | None = None,
    font_path: str | None = None,
    video_config: dict[str, Any] | None = None,
) -> Path:
    """フォールバック: 単色/画像背景 + テロップ合成"""
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg not found")

    cfg = video_config or {}
    width = cfg.get("width", SHORTS_WIDTH)
    height = cfg.get("height", SHORTS_HEIGHT)
    bg_color = cfg.get("bg_color", BG_COLOR)
    duration = _get_audio_duration(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_parts: list[str] = []
    inputs: list[str] = []
    input_idx = 0

    if background_image and background_image.exists():
        inputs.extend(["-loop", "1", "-i", str(background_image)])
        filter_parts.append(
            f"[{input_idx}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[bg]"
        )
    else:
        inputs.extend([
            "-f", "lavfi", "-i",
            f"color=c={bg_color}:s={width}x{height}:d={duration}:r=30",
        ])
        filter_parts.append(f"[{input_idx}:v]setsar=1[bg]")
    input_idx += 1

    inputs.extend(["-i", str(audio_path)])
    audio_idx = input_idx
    input_idx += 1

    current_layer = "bg"
    if character_clip and character_clip.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(character_clip)])
        char_idx = input_idx
        input_idx += 1
        if str(character_clip).endswith(".webm"):
            filter_parts.append(f"[{char_idx}:v]scale=-1:{int(height * 0.75)}[char]")
        else:
            filter_parts.append(
                f"[{char_idx}:v]chromakey=0x00FF00:0.12:0.08,"
                f"scale=-1:{int(height * 0.75)}[char]"
            )
        filter_parts.append(
            f"[{current_layer}][char]overlay=(W-w)/2:H-h:shortest=1[with_char]"
        )
        current_layer = "with_char"

    if telop_lines:
        telop_filter = _build_telop_filter(telop_lines, font_path=font_path)
        filter_parts.append(f"[{current_layer}]{telop_filter}[final]")
        current_layer = "final"

    filter_complex = ";".join(filter_parts)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{current_layer}]", "-map", f"{audio_idx}:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", "30",
        str(output_path),
    ]
    logger.info("Running ffmpeg (fallback mode)")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg failed:\n%s", result.stderr[-1000:])
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    logger.info("Video generated (fallback): %s (%.1fs)", output_path, duration)
    return output_path


# ── テロップヘルパー ──


def build_telop_lines_from_script(script_youtube: dict) -> list[str]:
    """script_youtube.jsonからフォールバック用テロップ行を構築"""
    lines: list[str] = []
    status = script_youtube.get("status", "")
    if status == "trade":
        meta = script_youtube.get("upload_meta", {})
        title = meta.get("title", "")
        if title:
            if len(title) > 20:
                mid = len(title) // 2
                lines.extend([title[:mid], title[mid:]])
            else:
                lines.append(title)
        lines.append("")
        body = script_youtube.get("body", "")
        for raw_line in body.split("\n"):
            s = raw_line.strip()
            if s and len(s) < 40:
                lines.append(s)
            elif s:
                lines.append(s[:38] + "...")
    elif status == "no_trade":
        lines.append("本日はシグナル見送り")
    lines.extend(["", "!! 投資助言ではありません"])
    return lines[:12]
