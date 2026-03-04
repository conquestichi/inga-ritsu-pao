"""台本生成モジュール — パターンA/D/F + レジーム連動選択

テンプレートからレジームに応じたパターンを選択し、
candidates.jsonの差分データを注入。律ペルソナに完全準拠。
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

# ローテーション状態（プロセス内。日次1回実行なので十分）
_rotation_index: dict[str, int] = {}

# 特徴量名 → 日本語ラベル（専門用語キープ＋すごそう感）
_FEATURE_LABELS: dict[str, str] = {
    "minute_vwap_dev": "VWAP乖離",
    "momentum_5d": "5日モメンタム",
    "momentum_10d": "10日モメンタム",
    "momentum_20d": "20日モメンタム",
    "volume_ratio": "出来高レシオ",
    "volume_breakout": "出来高ブレイクアウト",
    "short_interest_change": "空売り残変動",
    "short_interest_ratio": "貸借倍率",
    "margin_buy_change": "信用買い残変動",
    "margin_sell_change": "信用売り残変動",
    "rsi_14d": "RSI(14日)",
    "bb_position": "ボリンジャーバンド位置",
    "macd_signal": "MACDクロス",
    "cross_asset_usdjpy": "ドル円連動",
    "cross_asset_vix": "VIX恐怖指数",
    "earnings_surprise": "決算サプライズ",
    "tdnet_disclosure": "適時開示シグナル",
}


def _feature_label(feature_name: str) -> str:
    """特徴量名を日本語ラベルに変換"""
    return _FEATURE_LABELS.get(feature_name, feature_name)


def _simplify_reason(note: str, feature: str, direction: str) -> str:
    """reason noteを方向付きで表示（専門用語＋数値キープ）"""
    arrow = "↑" if direction == "bullish" else "↓"
    return f"{arrow} {note}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fill(template: str, ctx: dict[str, Any]) -> str:
    """テンプレートにコンテキスト変数を注入 + 空行・空弾丸の後処理"""
    result = template
    for key, val in ctx.items():
        result = result.replace(f"{{{key}}}", str(val))
    # 後処理: 空の弾丸行を除去（「・」だけの行）
    lines = result.split("\n")
    lines = [ln for ln in lines if ln.strip() not in ("・", "・ ", "・  ")]
    result = "\n".join(lines)
    # 連続空行を1つに圧縮
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    # 末尾セパレータ（｜）の除去
    lines = result.split("\n")
    lines = [ln.rstrip("｜").rstrip() for ln in lines]
    return "\n".join(lines).strip()


def _select_pattern(
    patterns: dict[str, Any],
    selection_rule: dict[str, Any],
    regime: str,
    channel: str,
) -> tuple[str, dict[str, Any]]:
    """レジームに応じたパターンを選択（alternate or random）"""
    candidates_keys = selection_rule.get(regime, [])
    if not candidates_keys:
        candidates_keys = selection_rule.get("risk_on", list(patterns.keys())[:1])

    rotation = selection_rule.get("rotation", "random")
    rot_key = f"{channel}_{regime}"

    if rotation == "alternate":
        idx = _rotation_index.get(rot_key, 0)
        key = candidates_keys[idx % len(candidates_keys)]
        _rotation_index[rot_key] = idx + 1
    else:
        key = random.choice(candidates_keys)

    return key, patterns[key]


def _build_context(
    candidate: Candidate | None,
    gates: GatesResult,
    as_of: str,
    meta_universe_size: int = 1800,
) -> dict[str, Any]:
    """テンプレート注入用コンテキストを構築"""
    ctx: dict[str, Any] = {
        "as_of": as_of,
        "date": as_of,
        "universe_size": str(meta_universe_size),
        "regime_label": "リスクオン" if gates.regime == "risk_on" else "リスクオフ",
        "regime_short": "リスクオン" if gates.regime == "risk_on" else "リスクオフ",
    }

    # 品質ゲート情報（学習モデル感＋数値）
    if gates.all_passed:
        ctx["gate_status"] = "全5項目クリア ✅"
    else:
        ctx["gate_status"] = "基準未達 ⛔"
    # IC → 予測精度スコア（基準比較で高低がわかるように）
    if gates.wf_ic is not None:
        ctx["wf_ic"] = f"{gates.wf_ic:.3f}"
        # IC 0.02以上が実用基準という前提
        if gates.wf_ic >= 0.04:
            ctx["ic_display"] = f"予測精度 {gates.wf_ic:.3f}（基準の{gates.wf_ic / 0.02:.1f}倍）"
        elif gates.wf_ic >= 0.02:
            ctx["ic_display"] = f"予測精度 {gates.wf_ic:.3f}（基準クリア）"
        else:
            ctx["ic_display"] = f"予測精度 {gates.wf_ic:.3f}（基準未達）"
    else:
        ctx["wf_ic"] = "N/A"
        ctx["ic_display"] = ""
    if gates.rejection_reasons:
        # 技術的な理由を素人向けに変換
        reason_map: dict[str, str] = {
            "walk_forward_ic_low": "学習モデルの予測精度が基準未達",
            "param_stability_failed": "モデルパラメータの安定性不足",
            "cost_test_failed": "手数料込みで利益が出ない",
            "leak_detection": "学習データの漏洩検知",
            "ticker_split_cv_failed": "銘柄間の検証で偏り検出",
        }
        ctx["rejection_reasons"] = "、".join(
            reason_map.get(r, r) for r in gates.rejection_reasons
        )
        ctx["fail_reason"] = reason_map.get(
            gates.rejection_reasons[0], gates.rejection_reasons[0]
        )
    else:
        ctx["rejection_reasons"] = ""
        ctx["fail_reason"] = "なし"

    if candidate:
        ctx.update(
            {
                "ticker_display": ticker_display(candidate.ticker),
                "name": candidate.name,
                "sector": candidate.sector,
                "score": f"{candidate.score:.1f}",
                "holding_window": candidate.holding_window,
                "reason_summary": build_reason_summary(candidate),
                "reason_detail": build_reason_detail(candidate),
                "risk_flags": format_risk_flags(candidate.risk_flags),
            }
        )
        # reason_1/2/3（3つ未満の場合はデフォルト値）
        for i in range(3):
            if i < len(candidate.reasons_top3):
                r = candidate.reasons_top3[i]
                ctx[f"reason_{i + 1}"] = _simplify_reason(r.note, r.feature, r.direction)
            else:
                ctx[f"reason_{i + 1}"] = ""

        # 反証条件・観測指標（トップ理由から生成）
        top = candidate.reasons_top3[0] if candidate.reasons_top3 else None
        if top:
            feature_label = _feature_label(top.feature)
            if top.direction == "bullish":
                ctx["condition_a"] = f"{feature_label}が強気継続"
                ctx["condition_b"] = f"{feature_label}が反転"
            else:
                ctx["condition_a"] = f"{feature_label}が弱気継続"
                ctx["condition_b"] = f"{feature_label}が反転上昇"
            ctx["watch"] = feature_label
        else:
            ctx["condition_a"] = "シグナル継続"
            ctx["condition_b"] = "シグナル反転"
            ctx["watch"] = ctx.get("regime_label", "レジーム")

    else:
        ctx["condition_a"] = "レジーム回復"
        ctx["condition_b"] = "リスクオフ継続"
        ctx["watch"] = ctx.get("regime_label", "レジーム")

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
    universe_size = candidates.meta.universe_size or 1800
    ctx = _build_context(top1, gates, as_of, universe_size)

    patterns = tmpl["patterns"]
    selection_rule = tmpl["selection_rule"]

    if gates.all_passed and top1:
        regime = gates.regime
        _key, pattern = _select_pattern(patterns, selection_rule, regime, "x")
        body = _fill(pattern["body"], ctx)
        self_reply = _fill(pattern.get("self_reply", ""), ctx)
        status = "trade"
    else:
        _key, pattern = _select_pattern(patterns, selection_rule, "risk_off", "x")
        body = _fill(pattern["body"], ctx)
        self_reply = _fill(pattern.get("self_reply", ""), ctx)
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
            "pattern": _key,
            "template_version": "v2",
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
    universe_size = candidates.meta.universe_size or 1800
    ctx = _build_context(top1, gates, as_of, universe_size)

    patterns = tmpl["patterns"]
    selection_rule = tmpl["selection_rule"]

    # タイトルカード
    title_card_cfg = tmpl.get("title_card", {})
    title_card = {
        "text": title_card_cfg.get("text", "明日上がる日本株"),
        "sub_text": _fill(title_card_cfg.get("sub_text", "{as_of}"), ctx),
        "duration_sec": title_card_cfg.get("duration_sec", 1.5),
        "bg": title_card_cfg.get("bg", "black"),
        "font_size": title_card_cfg.get("font_size", 72),
        "sub_font_size": title_card_cfg.get("sub_font_size", 36),
    }

    if gates.all_passed and top1:
        regime = gates.regime
        _key, pattern = _select_pattern(patterns, selection_rule, regime, "youtube")
        hook = _fill(pattern["hook"], ctx)
        body = _fill(pattern["body"], ctx)
        cta = _fill(pattern["cta"], ctx)
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
        _key, pattern = _select_pattern(patterns, selection_rule, "risk_off", "youtube")
        hook = _fill(pattern["hook"], ctx)
        body = _fill(pattern["body"], ctx)
        cta = _fill(pattern["cta"], ctx)
        status = "no_trade"
        upload_meta = {}

    return ScriptYoutubeJson(
        date=as_of,
        status=status,
        hook=hook,
        body=body,
        cta=cta,
        title_card=title_card,
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
