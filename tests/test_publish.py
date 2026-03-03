"""publishモジュールのテスト"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ritsu_pao.schemas import CandidatesJson, GatesResult
from ritsu_pao.publish.sanitize import (
    build_reason_detail, build_reason_summary, extract_top1, format_risk_flags, ticker_display,
)
from ritsu_pao.publish.script_gen import (
    generate_meta, generate_note_md, generate_script_x, generate_script_youtube,
)
from ritsu_pao.publish.publisher import publish


class TestTickerDisplay:
    def test_5digit_to_4digit(self):
        assert ticker_display("72030") == "7203"

    def test_4digit_unchanged(self):
        assert ticker_display("7203") == "7203"

    def test_5digit_no_trailing_zero(self):
        assert ticker_display("72031") == "72031"


class TestExtractTop1:
    def test_returns_first_candidate(self, sample_candidates_data):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        top1 = extract_top1(candidates)
        assert top1 is not None
        assert top1.ticker == "72030"

    def test_empty_candidates(self, sample_candidates_data):
        sample_candidates_data["candidates"] = []
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        assert extract_top1(candidates) is None


class TestReasonSummary:
    def test_generates_summary(self, sample_candidates_data):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        summary = build_reason_summary(candidates.candidates[0])
        assert "VWAP乖離" in summary
        assert "強気" in summary

    def test_reason_detail(self, sample_candidates_data):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        detail = build_reason_detail(candidates.candidates[0])
        assert "主な根拠は" in detail


class TestRiskFlags:
    def test_known_flag(self):
        assert "高ボラティリティ" in format_risk_flags(["high_volatility"])

    def test_empty(self):
        assert format_risk_flags([]) == "なし"

    def test_unknown_flag(self):
        assert format_risk_flags(["unknown"]) == "unknown"


class TestGenerateScriptX:
    def test_trade_signal(self, sample_candidates_data, sample_gates_passed, tmp_config):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_passed)
        top1 = extract_top1(candidates)
        script = generate_script_x(candidates, gates, top1, tmp_config)
        assert script.status == "trade"
        assert "7203" in script.body
        assert len(script.self_reply) > 0

    def test_no_trade(self, sample_candidates_data, sample_gates_failed, tmp_config):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_failed)
        script = generate_script_x(candidates, gates, None, tmp_config)
        assert script.status == "no_trade"
        assert script.self_reply == ""

    def test_banned_words_not_in_template(self, sample_candidates_data, sample_gates_passed, tmp_config):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_passed)
        top1 = extract_top1(candidates)
        cfg = json.loads((tmp_config / "reply_config.json").read_text(encoding="utf-8"))
        banned = cfg["banned_words"]
        script = generate_script_x(candidates, gates, top1, tmp_config)
        for word in banned:
            assert word not in script.body
            assert word not in script.self_reply


class TestGenerateScriptYoutube:
    def test_trade_signal(self, sample_candidates_data, sample_gates_passed, tmp_config):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_passed)
        top1 = extract_top1(candidates)
        script = generate_script_youtube(candidates, gates, top1, tmp_config)
        assert script.status == "trade"
        assert "title" in script.upload_meta

    def test_no_trade(self, sample_candidates_data, sample_gates_failed, tmp_config):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_failed)
        script = generate_script_youtube(candidates, gates, None, tmp_config)
        assert script.status == "no_trade"


class TestGenerateNoteMd:
    def test_trade_note(self, sample_candidates_data, sample_gates_passed):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_passed)
        top1 = extract_top1(candidates)
        note = generate_note_md(candidates, gates, top1)
        assert "# 因果律シグナル" in note
        assert "7203" in note
        assert "投資助言ではありません" in note

    def test_no_trade_note(self, sample_candidates_data, sample_gates_failed):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_failed)
        note = generate_note_md(candidates, gates, None)
        assert "品質ゲートを通過できなかった" in note


class TestGenerateMeta:
    def test_ok(self, sample_candidates_data, sample_gates_passed):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_passed)
        meta = generate_meta(candidates, gates)
        assert meta.status.value == "ok"

    def test_no_post(self, sample_candidates_data, sample_gates_failed):
        candidates = CandidatesJson.model_validate(sample_candidates_data)
        gates = GatesResult.model_validate(sample_gates_failed)
        meta = generate_meta(candidates, gates)
        assert meta.status.value == "no_post"


class TestPublisher:
    def test_full_publish_trade(self, tmp_path, sample_candidates_data, sample_gates_passed, tmp_config):
        cand_path = tmp_path / "candidates.json"
        cand_path.write_text(json.dumps(sample_candidates_data), encoding="utf-8")
        gates_path = tmp_path / "gates_result.json"
        gates_path.write_text(json.dumps(sample_gates_passed), encoding="utf-8")
        output_dir = tmp_path / "publish"
        result = publish(cand_path, gates_path, output_dir, tmp_config)
        assert "meta" in result
        assert "script_x" in result
        assert "script_youtube" in result
        assert "note" in result
        meta = json.loads((output_dir / "meta.json").read_text())
        assert meta["status"] == "ok"

    def test_full_publish_no_trade(self, tmp_path, sample_candidates_data, sample_gates_failed, tmp_config):
        cand_path = tmp_path / "candidates.json"
        cand_path.write_text(json.dumps(sample_candidates_data), encoding="utf-8")
        gates_path = tmp_path / "gates_result.json"
        gates_path.write_text(json.dumps(sample_gates_failed), encoding="utf-8")
        output_dir = tmp_path / "publish"
        result = publish(cand_path, gates_path, output_dir, tmp_config)
        assert "meta" in result
        assert "script_x" not in result

    def test_missing_gates_defaults_to_passed(self, tmp_path, sample_candidates_data, tmp_config):
        cand_path = tmp_path / "candidates.json"
        cand_path.write_text(json.dumps(sample_candidates_data), encoding="utf-8")
        gates_path = tmp_path / "nonexistent_gates.json"
        output_dir = tmp_path / "publish"
        result = publish(cand_path, gates_path, output_dir, tmp_config)
        assert "script_x" in result
