"""台本生成モジュール — テンプレ80% + 差分20%

テンプレートからランダム選択し、candidates.jsonの差分データを注入。
律ペルソナに完全準拠。
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from ritsu_pao.schemas import (
    Candidate,
    CandidatesJson,
    GatesResult,
    MetaJson,
    PublishStatus,
    ScriptXJson,
    ScriptYoutubeJson,
)
from ritsu_pao.publish.sanitize import (
    build_reason_detail,
    build_reason_summary,
    format_risk_flags,
    ticker_display,
)

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick(templates: list[str]) -> str:
    """テンプレートリストからランダム選択"""
    return random.choice(templates)


def _fill(template: str, ctx: dict[str, Any]) -> str:
    """テンプレートにコンテキスト変数を注入"""
    result = template
    for key, val in ctx.items():
        result = result.replace(f"{{{key}}}", str(val))
    return result


def _build_context(
    candidate: Candidate | None,
    gates: GatesResult,
    as_of: str,
    templates_cfg: dict[str, Any],
) -> dict[str, Any]:
    """テンプレート注入用コンテキストを構築"""
    regime_labels = templates_cfg.get("regime_labels", {})
    regime_short = templates_cfg.get("regime_short", {})

    ctx: dict[str, Any] = {
        "date": as_of,
        "regime_label": regime_labels.get(gates.regime, gates.regime),
        "regime_short": regime_short.get(gates.regime, gates.regime),
    }

    if candidate:
        ctx.update(
            {
                "ticker_display": ticker_display(candidate.ticker),
                "name": candidate.name,
                "sector": candidate.sector,
                "score": f"{candidate.score:.1f}",
                "reason_summary": build_reason_summary(candidate),
                "reason_detail": build_reason_detail(candidate),
                "holding_window": candidate.holding_window,
                "risk_flags": format_risk_flags(candidate.risk_flags),
            }
        )

    if gates.rejection_reasons:
        ctx["rejection_reasons"] = "、".join(gates.rejection_reasons)

    return ctx


# ─── X台本生成 ───


def generate_script_x(
    candidates: CandidatesJson,
    gates: GatesResult,
    top1: Candidate | None,
    config_dir: Path | None = None,
) -> ScriptXJson:
    """X投稿用台本を生成"""
    cfg_dir = config_dir or CONFIG_DIR
    tmpl = _load_json(cfg_dir / "templates_x.json")
    as_of = candidates.meta.as_of
    ctx = _build_context(top1, gates, as_of, tmpl)

    if gates.all_passed and top1:
        tpl = tmpl["templates"]["daily_signal"]
        body = _fill(_pick(tpl["body"]), ctx)
        self_reply = _fill(_pick(tpl["self_reply"]), ctx)
        status = "trade"
    else:
        tpl = tmpl["templates"]["no_trade"]
        body = _fill(_pick(tpl["body"]), ctx)
        self_reply = ""
        status = "no_trade"

    return ScriptXJson(
        date=as_of,
        status=status,
        body=body,
        self_reply=self_reply,
        meta={
            "ticker": top1.ticker if top1 else None,
            "score": top1.score if top1 else None,
            "regime": gates.regime,
            "template_version": "v1",
        },
    )


# ─── YouTube台本生成 ───


def generate_script_youtube(
    candidates: CandidatesJson,
    gates: GatesResult,
    top1: Candidate | None,
    config_dir: Path | None = None,
) -> ScriptYoutubeJson:
    """YouTube Shorts用台本を生成"""
    cfg_dir = config_dir or CONFIG_DIR
    tmpl = _load_json(cfg_dir / "templates_youtube.json")
    as_of = candidates.meta.as_of
    ctx = _build_context(top1, gates, as_of, tmpl)

    if gates.all_passed and top1:
        tpl = tmpl["templates"]["daily_signal"]
        hook = _fill(_pick(tpl["hook"]), ctx)
        body = _fill(_pick(tpl["body"]), ctx)
        cta = _fill(_pick(tpl["cta"]), ctx)
        status = "trade"

        upload_meta_tmpl = tmpl.get("upload_meta", {})
        upload_meta = {
            "title": _fill(upload_meta_tmpl.get("title_template", ""), ctx),
            "description": _fill(upload_meta_tmpl.get("description_template", ""), ctx),
            "tags": upload_meta_tmpl.get("tags", []),
            "category_id": upload_meta_tmpl.get("category_id", "22"),
            "privacy_status": upload_meta_tmpl.get("privacy_status", "public"),
        }
    else:
        tpl = tmpl["templates"]["no_trade"]
        hook = _fill(_pick(tpl["hook"]), ctx)
        body = _fill(_pick(tpl["body"]), ctx)
        cta = _fill(_pick(tpl["cta"]), ctx)
        status = "no_trade"
        upload_meta = {}

    return ScriptYoutubeJson(
        date=as_of,
        status=status,
        hook=hook,
        body=body,
        cta=cta,
        voicepeak=tmpl.get("voicepeak", {}),
        upload_meta=upload_meta,
    )


# ─── note原稿生成 ───


def generate_note_md(
    candidates: CandidatesJson,
    gates: GatesResult,
    top1: Candidate | None,
) -> str:
    """note用Markdown原稿を生成（因果quants出力をそのままコピーに近い形式）"""
    as_of = candidates.meta.as_of
    regime_ja = "リスクオン" if gates.regime == "risk_on" else "リスクオフ"

    lines: list[str] = []
    lines.append(f"# 因果律シグナル {as_of}")
    lines.append("")
    lines.append(f"**レジーム**: {regime_ja}")
    lines.append("")

    if not gates.all_passed:
        lines.append("## 本日のシグナル")
        lines.append("")
        lines.append("品質ゲートを通過できなかったため、本日の推奨銘柄はありません。")
        lines.append("")
        lines.append(f"**停止理由**: {', '.join(gates.rejection_reasons)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "⚠️ これはクオンツシグナルの共有であり、投資助言ではありません。"
            "投資判断はご自身の責任でお願いします。"
        )
        return "\n".join(lines)

    lines.append("## 注目銘柄")
    lines.append("")

    for i, c in enumerate(candidates.candidates[:5]):
        td = ticker_display(c.ticker)
        rank = i + 1
        lines.append(f"### {rank}. {td} {c.name}（{c.sector}）")
        lines.append("")
        lines.append(f"- **スコア**: {c.score:.1f}")
        lines.append(f"- **保有想定**: {c.holding_window}")
        if c.risk_flags:
            lines.append(f"- **リスクフラグ**: {format_risk_flags(c.risk_flags)}")
        lines.append("")
        lines.append("**根拠**:")
        for r in c.reasons_top3:
            direction_ja = "強気" if r.direction == "bullish" else "弱気"
            lines.append(f"- {r.note}（{direction_ja}, z={r.z:.1f}）")
        if c.events:
            lines.append("")
            lines.append("**イベント**:")
            for e in c.events:
                lines.append(f"- {e.date}: {e.type}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "⚠️ これはクオンツシグナルの共有であり、投資助言ではありません。"
        "投資判断はご自身の責任でお願いします。"
    )
    return "\n".join(lines)


# ─── meta.json生成 ───


def generate_meta(
    candidates: CandidatesJson,
    gates: GatesResult,
) -> MetaJson:
    """meta.jsonを生成"""
    return MetaJson(
        date=candidates.meta.as_of,
        status=PublishStatus.OK if gates.all_passed else PublishStatus.NO_POST,
        generated_at=datetime.now().isoformat(),
        rejection_reasons=gates.rejection_reasons,
        quality_score=gates.wf_ic,
        run_id=candidates.meta.run_id,
        git_sha=candidates.meta.git_sha,
    )
