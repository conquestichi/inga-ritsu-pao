"""candidates.json → 公開用サニタイズ済みデータ抽出"""

from __future__ import annotations

from ritsu_pao.schemas import Candidate, CandidatesJson


def ticker_display(ticker: str) -> str:
    """5桁ティッカーを4桁表示に変換 (例: 72030 → 7203)"""
    if len(ticker) == 5 and ticker.endswith("0"):
        return ticker[:4]
    return ticker


def extract_top1(candidates: CandidatesJson) -> Candidate | None:
    """TOP1銘柄を抽出（scoreでソート済み前提、candidates[0]）"""
    if not candidates.candidates:
        return None
    return candidates.candidates[0]


def build_reason_summary(candidate: Candidate, max_reasons: int = 3) -> str:
    """reasons_top3から日本語要約テキストを生成"""
    lines: list[str] = []
    for r in candidate.reasons_top3[:max_reasons]:
        direction_ja = "強気" if r.direction == "bullish" else "弱気"
        lines.append(f"・{r.note}（{direction_ja}, z={r.z:.1f}）")
    return "\n".join(lines)


def build_reason_detail(candidate: Candidate) -> str:
    """YouTube台本用の詳細な理由説明"""
    parts: list[str] = []
    for i, r in enumerate(candidate.reasons_top3):
        direction_ja = "強気" if r.direction == "bullish" else "弱気"
        if i == 0:
            parts.append(f"主な根拠は{r.note}で、{direction_ja}方向のシグナルが出ています。")
        else:
            parts.append(f"加えて、{r.note}も{direction_ja}シグナルです。")
    return "\n".join(parts)


def format_risk_flags(flags: list[str]) -> str:
    """リスクフラグを日本語表示"""
    flag_map = {
        "high_volatility": "高ボラティリティ",
        "low_liquidity": "低流動性",
        "earnings_soon": "決算間近",
        "sector_risk": "セクターリスク",
    }
    if not flags:
        return "なし"
    return "、".join(flag_map.get(f, f) for f in flags)
