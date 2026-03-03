"""Slack Block Kit通知 — note原稿配布 + 日次publish結果通知"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

from ritsu_pao.schemas import MetaJson, ScriptXJson

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def _post_blocks(blocks: list[dict[str, Any]], text: str = "") -> bool:
    """Slack Webhookにブロックを送信"""
    if not WEBHOOK_URL:
        logger.error("SLACK_WEBHOOK_URL not set")
        return False

    payload = {"text": text or "因果律 ritsu-pao 通知", "blocks": blocks}
    try:
        resp = httpx.post(WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack notification sent")
        return True
    except httpx.HTTPError as e:
        logger.error("Slack notification failed: %s", e)
        return False


# ─── Block Kit builders ───


def _header_block(text: str) -> dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section_block(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _divider() -> dict[str, Any]:
    return {"type": "divider"}


def _context_block(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


# ─── note原稿配布ブロック ───


def build_note_distribution_blocks(
    note_md: str,
    meta: MetaJson,
) -> list[dict[str, Any]]:
    """note原稿をSlack Block Kit形式で配布"""
    blocks: list[dict[str, Any]] = []

    status_emoji = "✅" if meta.status == "ok" else "🚫"
    blocks.append(_header_block(f"{status_emoji} 因果律 note原稿 {meta.date}"))
    blocks.append(_divider())

    if meta.status == "no_post":
        blocks.append(
            _section_block(
                f"*ステータス*: NO_POST\n"
                f"*停止理由*: {', '.join(meta.rejection_reasons)}\n\n"
                "本日のnote投稿はスキップします。"
            )
        )
        return blocks

    # note原稿をSlackブロックに展開（3000文字制限対応）
    MAX_BLOCK_LEN = 2900
    chunks: list[str] = []
    current = ""
    for line in note_md.split("\n"):
        if len(current) + len(line) + 1 > MAX_BLOCK_LEN:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        blocks.append(_section_block(chunk))

    blocks.append(_divider())
    blocks.append(
        _context_block(
            f"run_id: {meta.run_id} | "
            f"generated_at: {meta.generated_at} | "
            f"quality_score: {meta.quality_score or 'N/A'}"
        )
    )

    return blocks


# ─── publish結果通知ブロック ───


def build_publish_report_blocks(
    meta: MetaJson,
    script_x: ScriptXJson | None = None,
    files: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """日次publish結果をSlack Block Kit形式で通知"""
    blocks: list[dict[str, Any]] = []

    status_emoji = "✅" if meta.status == "ok" else "🚫"
    blocks.append(_header_block(f"{status_emoji} ritsu-pao Publish Report {meta.date}"))
    blocks.append(_divider())

    # ステータス
    status_text = f"*ステータス*: {meta.status.value.upper()}"
    if meta.rejection_reasons:
        status_text += f"\n*停止理由*: {', '.join(meta.rejection_reasons)}"
    if meta.quality_score is not None:
        status_text += f"\n*WF IC*: {meta.quality_score:.4f}"
    blocks.append(_section_block(status_text))

    # X投稿プレビュー
    if script_x and script_x.status == "trade":
        blocks.append(_divider())
        blocks.append(_section_block(f"*📱 X投稿プレビュー*\n```{script_x.body[:500]}```"))
        if script_x.self_reply:
            blocks.append(
                _section_block(f"*↩️ 自己リプ*\n```{script_x.self_reply[:300]}```")
            )

    # 生成ファイル一覧
    if files:
        file_list = "\n".join(f"• `{k}`: {v}" for k, v in files.items())
        blocks.append(_divider())
        blocks.append(_section_block(f"*📁 生成ファイル*\n{file_list}"))

    blocks.append(_divider())
    blocks.append(
        _context_block(f"run_id: {meta.run_id} | generated_at: {meta.generated_at}")
    )

    return blocks


# ─── 送信ヘルパー ───


def notify_publish_result(
    meta: MetaJson,
    script_x: ScriptXJson | None = None,
    files: dict[str, Path] | None = None,
) -> bool:
    """publish結果をSlack通知"""
    blocks = build_publish_report_blocks(meta, script_x, files)
    return _post_blocks(blocks, f"ritsu-pao publish {meta.date}: {meta.status.value}")


def notify_note_distribution(
    note_md: str,
    meta: MetaJson,
) -> bool:
    """note原稿をSlack配布"""
    blocks = build_note_distribution_blocks(note_md, meta)
    return _post_blocks(blocks, f"因果律 note原稿 {meta.date}")
