"""publisher — candidates.json読込 → 全publishファイル生成・書出し

Usage:
    python -m ritsu_pao.publish.publisher \
        --candidates /srv/inga/output/latest/candidates.json \
        --gates /srv/inga/output/latest/gates_result.json \
        --output /srv/inga/output/publish/latest/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ritsu_pao.schemas import CandidatesJson, GatesResult
from ritsu_pao.publish.sanitize import extract_top1
from ritsu_pao.publish.script_gen import (
    generate_meta,
    generate_note_md,
    generate_script_x,
    generate_script_youtube,
)

logger = logging.getLogger(__name__)


def load_candidates(path: Path) -> CandidatesJson:
    """candidates.jsonを読み込み・バリデーション"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return CandidatesJson.model_validate(data)


def load_gates(path: Path) -> GatesResult:
    """gates_result.json or decision_card_*.json を読み込み。

    decision_card形式の場合は自動変換:
      action: "TRADE"/"NO_TRADE" → all_passed
      no_trade_reasons → rejection_reasons
      key_metrics.wf_ic → wf_ic
    """
    if not path.exists():
        logger.warning("gates file not found, assuming all_passed=True")
        return GatesResult(all_passed=True, regime="risk_on")

    data = json.loads(path.read_text(encoding="utf-8"))

    # decision_card形式の検出 (action フィールドがある)
    if "action" in data:
        logger.info("Detected decision_card format, converting to GatesResult")
        all_passed = data.get("action") == "TRADE"
        rejection_reasons = data.get("no_trade_reasons", [])
        key_metrics = data.get("key_metrics", {})
        wf_ic = key_metrics.get("wf_ic")

        # regime: decision_cardに無い場合、short_candidatesから推定するか
        # またはmanifest.jsonから取得。無ければdefault
        regime = data.get("regime")
        if not regime:
            # 同ディレクトリのmanifest.jsonからregime取得を試行
            manifest_path = path.parent / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    regime = manifest.get("regime", "risk_on")
                except Exception:
                    regime = "risk_on"
            else:
                regime = "risk_on"

        return GatesResult(
            all_passed=all_passed,
            rejection_reasons=rejection_reasons,
            regime=regime,
            wf_ic=wf_ic,
        )

    # 標準形式 (gates_result.json)
    return GatesResult.model_validate(data)


def publish(
    candidates_path: Path,
    gates_path: Path,
    output_dir: Path,
    config_dir: Path | None = None,
) -> dict[str, Path]:
    """メインパブリッシュ処理

    Returns:
        生成ファイルのパス辞書
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 入力読込
    candidates = load_candidates(candidates_path)
    gates = load_gates(gates_path)
    top1 = extract_top1(candidates) if gates.all_passed else None

    # meta.json は常に生成
    meta = generate_meta(candidates, gates)
    meta_path = output_dir / "meta.json"
    meta_path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Generated: %s (status=%s)", meta_path, meta.status)

    result: dict[str, Path] = {"meta": meta_path}

    # NO_POST時はmeta.jsonのみ
    if meta.status == "no_post":
        logger.info("NO_POST — skipping script/note generation")
        return result

    # script_x.json
    script_x = generate_script_x(candidates, gates, top1, config_dir)
    sx_path = output_dir / "script_x.json"
    sx_path.write_text(script_x.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Generated: %s", sx_path)
    result["script_x"] = sx_path

    # script_youtube.json
    script_yt = generate_script_youtube(candidates, gates, top1, config_dir)
    sy_path = output_dir / "script_youtube.json"
    sy_path.write_text(script_yt.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Generated: %s", sy_path)
    result["script_youtube"] = sy_path

    # note.md
    note_md = generate_note_md(candidates, gates, top1)
    note_path = output_dir / "note.md"
    note_path.write_text(note_md, encoding="utf-8")
    logger.info("Generated: %s", note_path)
    result["note"] = note_path

    # candidates.json (サニタイズ版コピー)
    cand_path = output_dir / "candidates.json"
    cand_path.write_text(candidates.model_dump_json(indent=2), encoding="utf-8")
    result["candidates"] = cand_path

    # reply_config.json コピー
    cfg_dir = config_dir or (Path(__file__).resolve().parents[3] / "config")
    reply_cfg_src = cfg_dir / "reply_config.json"
    if reply_cfg_src.exists():
        reply_path = output_dir / "reply_config.json"
        reply_path.write_text(reply_cfg_src.read_text(encoding="utf-8"), encoding="utf-8")
        result["reply_config"] = reply_path

    logger.info("Publish complete: %d files", len(result))
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="因果律 publish pipeline")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("/srv/inga/output/latest/candidates.json"),
        help="candidates.json path",
    )
    parser.add_argument(
        "--gates",
        type=Path,
        default=Path("/srv/inga/output/latest/gates_result.json"),
        help="gates_result.json path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/srv/inga/output/publish/latest"),
        help="Output directory",
    )
    parser.add_argument("--config", type=Path, default=None, help="Config directory")
    args = parser.parse_args()

    try:
        result = publish(args.candidates, args.gates, args.output, args.config)
        print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))
    except Exception as e:
        logger.error("Publish failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
