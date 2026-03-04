"""テスト用fixtures"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_candidates_data() -> dict:
    return {
        "meta": {
            "run_id": "test-run-001",
            "as_of": "2026-03-03",
            "timezone": "Asia/Tokyo",
            "git_sha": "abc1234",
            "inputs_digest": "sha256:test",
            "universe_size": 1800,
            "eligible_size": 200,
            "generated_at": "2026-03-03T18:30:00+09:00",
        },
        "candidates": [
            {
                "ticker": "72030",
                "name": "TDK",
                "sector": "電気機器",
                "score": 85.3,
                "reasons_top3": [
                    {"feature": "minute_vwap_dev", "value": 0.023, "z": 1.8, "direction": "bullish", "note": "VWAP乖離+0.023"},
                    {"feature": "momentum_20d", "value": 0.045, "z": 1.5, "direction": "bullish", "note": "20日モメンタム+4.5%"},
                    {"feature": "volume_ratio", "value": 1.8, "z": 1.2, "direction": "bullish", "note": "出来高比率1.8倍"},
                ],
                "risk_flags": ["high_volatility"],
                "events": [{"date": "2026-03-14", "type": "earnings"}],
                "holding_window": "1-5d",
            },
            {
                "ticker": "68610",
                "name": "キーエンス",
                "sector": "電気機器",
                "score": 78.1,
                "reasons_top3": [
                    {"feature": "short_interest_change", "value": -0.02, "z": 1.6, "direction": "bullish", "note": "空売り残減少-2%"},
                ],
                "risk_flags": [],
                "events": [],
                "holding_window": "1-5d",
            },
        ],
    }


@pytest.fixture
def sample_gates_passed() -> dict:
    return {"all_passed": True, "rejection_reasons": [], "regime": "risk_on", "wf_ic": 0.042}


@pytest.fixture
def sample_gates_failed() -> dict:
    return {
        "all_passed": False,
        "rejection_reasons": ["walk_forward_ic_low", "param_stability_failed"],
        "regime": "risk_off",
        "wf_ic": 0.008,
    }


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    src_config = Path(__file__).resolve().parents[1] / "config"
    for fname in ["templates_x.json", "templates_youtube.json", "reply_config.json"]:
        src = src_config / fname
        if src.exists():
            (config_dir / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return config_dir
