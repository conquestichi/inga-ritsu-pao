"""ffmpeg動画合成 -- 背景 + 律クリップ + テロップ + 音声 -> Shorts MP4

YouTube Shorts仕様: 1080x1920 (9:16), 60秒以下
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
BG_COLOR = "#1a1a2e"
FONT_COLOR = "white"
TELOP_FONT_SIZE = 40
TELOP_Y_START = 100


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
    """YouTube Shorts動画を合成"""
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

    # 背景
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

    # 音声
    inputs.extend(["-i", str(audio_path)])
    audio_idx = input_idx
    input_idx += 1

    # キャラクターオーバーレイ
    current_layer = "bg"
    if character_clip and character_clip.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(character_clip)])
        char_idx = input_idx
        input_idx += 1
        if str(character_clip).endswith(".webm"):
            filter_parts.append(f"[{char_idx}:v]scale=-1:{int(height*0.5)}[char]")
        else:
            filter_parts.append(
                f"[{char_idx}:v]chromakey=0x00FF00:0.15:0.1,"
                f"scale=-1:{int(height*0.5)}[char]"
            )
        filter_parts.append(
            f"[{current_layer}][char]overlay=(W-w)/2:H-h:shortest=1[with_char]"
        )
        current_layer = "with_char"

    # テロップ
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
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", "30",
        str(output_path),
    ]
    logger.info("Running ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg failed:\n%s", result.stderr[-1000:])
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    logger.info("Video generated: %s (%.1fs)", output_path, duration)
    return output_path


def build_telop_lines_from_script(script_youtube: dict) -> list[str]:
    """script_youtube.jsonからテロップ行を構築"""
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
