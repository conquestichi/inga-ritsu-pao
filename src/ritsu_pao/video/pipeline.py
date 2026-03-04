"""Video pipeline: script_youtube.json -> final.mp4"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ritsu_pao.video.voicevox import generate_audio_from_script
from ritsu_pao.video.compositor import (
    build_telop_lines_from_script,
    compose_shorts,
    compose_shorts_scenes,
    compose_shorts_template,
)

logger = logging.getLogger(__name__)

DEFAULT_ASSETS_DIR = Path("/srv/inga/assets")
DEFAULT_VIDEO_CONFIG = {
    "width": 1080,
    "height": 1920,
    "bg_color": "#1a1a2e",
    "voicevox_url": "http://127.0.0.1:50021",
    "voicevox_speaker_id": 0,
}


def load_video_config(config_path: Path | None = None) -> dict:
    if config_path and config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return DEFAULT_VIDEO_CONFIG.copy()


def run_video_pipeline(
    script_path: Path,
    output_path: Path,
    assets_dir: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    """script_youtube.json -> VOICEVOX -> ffmpeg -> final.mp4"""
    assets = assets_dir or DEFAULT_ASSETS_DIR
    cfg = load_video_config(config_path)

    script = json.loads(script_path.read_text(encoding="utf-8"))
    logger.info("Loaded script: %s status=%s", script_path, script.get("status"))

    work_dir = output_path.parent / "video_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # VOICEVOX audio
    audio_files = generate_audio_from_script(
        script, work_dir / "audio",
        base_url=cfg.get("voicevox_url", "http://127.0.0.1:50021"),
        speaker_id=cfg.get("voicevox_speaker_id", 0),
    )
    audio_path = audio_files.get("full")
    if not audio_path or not audio_path.exists():
        raise RuntimeError("Audio generation failed")

    # Assets lookup
    character_clip = None
    for ext in [".webm", ".mp4", ".mov"]:
        c = assets / f"ritsu_loop{ext}"
        if c.exists():
            character_clip = c
            break

    font_path = None
    for fp in [
        assets / "NotoSansJP-Bold.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ]:
        if fp.exists():
            font_path = str(fp)
            break

    bgm_path = None
    for ext in [".mp3", ".wav", ".m4a"]:
        c = assets / f"bgm_loop{ext}"
        if c.exists():
            bgm_path = c
            break

    # モード自動選択: テンプレ > シーン切替 > フォールバック
    status = script.get("status", "trade")
    template_key = "template_trade.mp4" if status == "trade" else "template_no_trade.mp4"
    template_path = assets / template_key

    # シーン背景の探索
    scene_bg_map = {
        "intro": assets / "bg_intro.png",
        "reason": assets / "bg_reason.png",
        "cta": assets / "bg_cta.png",
        "no_trade": assets / "bg_no_trade.png",
    }
    scene_backgrounds = {k: v for k, v in scene_bg_map.items() if v.exists()}

    if template_path.exists():
        # Mode 1: テンプレ動画
        logger.info("Template mode: %s", template_path)
        result = compose_shorts_template(
            template_path=template_path,
            audio_path=audio_path,
            output_path=output_path,
            script=script,
            character_clip=character_clip,
            bgm_path=bgm_path,
            font_path=font_path,
        )
    elif len(scene_backgrounds) >= 2:
        # Mode 2: シーン切替 (背景画像2枚以上)
        logger.info("Scenes mode: %d backgrounds", len(scene_backgrounds))
        result = compose_shorts_scenes(
            audio_path=audio_path,
            audio_segments=audio_files,
            output_path=output_path,
            script=script,
            scene_backgrounds=scene_backgrounds,
            character_clip=character_clip,
            bgm_path=bgm_path,
            font_path=font_path,
            title_card=script.get("title_card"),
        )
    else:
        # Mode 3: フォールバック
        logger.info("Fallback mode (no template or scenes)")
        background_image = None
        for ext in [".png", ".jpg"]:
            c = assets / f"background{ext}"
            if c.exists():
                background_image = c
                break

        telop_lines = build_telop_lines_from_script(script)
        result = compose_shorts(
            audio_path=audio_path,
            output_path=output_path,
            telop_lines=telop_lines,
            character_clip=character_clip,
            background_image=background_image,
            font_path=font_path,
            video_config=cfg,
        )
    logger.info("Video pipeline complete: %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Video pipeline")
    parser.add_argument("--script", type=Path,
        default=Path("/srv/inga/output/publish/latest/script_youtube.json"))
    parser.add_argument("--output", type=Path,
        default=Path("/srv/inga/output/publish/latest/final.mp4"))
    parser.add_argument("--assets", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = run_video_pipeline(
            args.script, args.output, args.assets, args.config
        )
        print(f"Generated: {result}")
    except Exception as e:
        logger.error("Video pipeline failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
