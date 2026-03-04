"""VOICEVOX Engine APIクライアント — テキスト → 音声WAV生成

VPS上のVOICEVOX Engine (Docker) にHTTPリクエストを送信。
Docker: docker run --rm -p 50021:50021 voicevox/voicevox_engine:latest
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:50021"
DEFAULT_SPEAKER_ID = 0  # 四国めたん(あまあま) — 律のデフォルト


class VoicevoxClient:
    """VOICEVOX Engine HTTP APIクライアント"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        speaker_id: int = DEFAULT_SPEAKER_ID,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.speaker_id = speaker_id
        self.timeout = timeout

    def is_available(self) -> bool:
        """VOICEVOX Engineが起動しているか確認"""
        try:
            resp = httpx.get(f"{self.base_url}/version", timeout=5)
            resp.raise_for_status()
            logger.info("VOICEVOX Engine version: %s", resp.text)
            return True
        except (httpx.HTTPError, httpx.ConnectError):
            logger.error("VOICEVOX Engine not available at %s", self.base_url)
            return False

    def synthesize(self, text: str, output_path: Path) -> Path:
        """テキスト → WAV音声生成 (audio_query + synthesis)"""
        query_resp = httpx.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": self.speaker_id},
            timeout=self.timeout,
        )
        query_resp.raise_for_status()
        audio_query = query_resp.json()

        audio_query["speedScale"] = 1.0
        audio_query["pitchScale"] = 0.0
        audio_query["volumeScale"] = 1.0
        audio_query["intonationScale"] = 1.0

        synth_resp = httpx.post(
            f"{self.base_url}/synthesis",
            params={"speaker": self.speaker_id},
            json=audio_query,
            timeout=self.timeout,
        )
        synth_resp.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(synth_resp.content)
        logger.info("Generated audio: %s (%d bytes)", output_path, len(synth_resp.content))
        return output_path


def generate_audio_from_script(
    script_youtube: dict,
    output_dir: Path,
    base_url: str = DEFAULT_BASE_URL,
    speaker_id: int = DEFAULT_SPEAKER_ID,
) -> dict[str, Path]:
    """script_youtube.jsonから音声一括生成 → {segment: wav_path}"""
    client = VoicevoxClient(base_url=base_url, speaker_id=speaker_id)
    if not client.is_available():
        raise ConnectionError("VOICEVOX Engine is not available")

    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    for key in ["hook", "body", "cta"]:
        text = script_youtube.get(key, "")
        if not text.strip():
            continue
        wav_path = output_dir / f"{key}.wav"
        client.synthesize(text, wav_path)
        # CTA末尾に1秒の「ため」（無音）を追加 → revealへの余韻
        if key == "cta":
            _pad_silence(wav_path, 1.0)
        result[key] = wav_path

    full_text = " ".join(
        script_youtube.get(k, "") for k in ["hook", "body", "cta"]
        if script_youtube.get(k)
    )
    if full_text.strip():
        # full.wav = 個別wavを結合（タイミング一致保証）
        segment_paths = [result[k] for k in ["hook", "body", "cta"] if k in result]
        full_path = output_dir / "full.wav"
        if len(segment_paths) >= 2:
            _concat_wavs(segment_paths, full_path)
        elif len(segment_paths) == 1:
            import shutil
            shutil.copy2(segment_paths[0], full_path)
        else:
            client.synthesize(full_text, full_path)
        result["full"] = full_path

    logger.info("Audio generation complete: %d files", len(result))
    return result


def _pad_silence(wav_path: Path, seconds: float) -> None:
    """wavファイル末尾に無音を追加（上書き）"""
    import subprocess

    padded = wav_path.parent / f"{wav_path.stem}_padded.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-af", f"apad=pad_dur={seconds}",
        str(padded),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    padded.replace(wav_path)


def _concat_wavs(inputs: list[Path], output: Path) -> None:
    """ffmpegで複数wavを無音なし結合"""
    import subprocess

    list_file = output.parent / "_concat_list.txt"
    with open(list_file, "w") as f:
        for p in inputs:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(output),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    list_file.unlink(missing_ok=True)
