"""Slack通知モジュールのテスト"""

from __future__ import annotations

from ritsu_pao.schemas import MetaJson, PublishStatus, ScriptXJson
from ritsu_pao.notify.slack import build_note_distribution_blocks, build_publish_report_blocks


class TestNoteDistributionBlocks:
    def test_ok_status(self):
        meta = MetaJson(date="2026-03-03", status=PublishStatus.OK, generated_at="2026-03-03T19:00:00", run_id="test-001", quality_score=0.042)
        note_md = "# 因果律シグナル 2026-03-03\n\nテスト内容"
        blocks = build_note_distribution_blocks(note_md, meta)
        assert len(blocks) >= 3
        assert "✅" in blocks[0]["text"]["text"]

    def test_no_post_status(self):
        meta = MetaJson(date="2026-03-03", status=PublishStatus.NO_POST, generated_at="2026-03-03T19:00:00", rejection_reasons=["walk_forward_ic_low"], run_id="test-002")
        blocks = build_note_distribution_blocks("", meta)
        assert "🚫" in blocks[0]["text"]["text"]

    def test_long_note_chunking(self):
        meta = MetaJson(date="2026-03-03", status=PublishStatus.OK, generated_at="2026-03-03T19:00:00", run_id="test-003")
        long_note = "テスト行\n" * 500
        blocks = build_note_distribution_blocks(long_note, meta)
        section_blocks = [b for b in blocks if b["type"] == "section"]
        assert len(section_blocks) >= 1


class TestPublishReportBlocks:
    def test_trade_report(self):
        meta = MetaJson(date="2026-03-03", status=PublishStatus.OK, generated_at="2026-03-03T19:00:00", run_id="test-001", quality_score=0.042)
        script_x = ScriptXJson(date="2026-03-03", status="trade", body="テスト投稿", self_reply="テスト返信")
        blocks = build_publish_report_blocks(meta, script_x)
        assert len(blocks) >= 4

    def test_no_trade_report(self):
        meta = MetaJson(date="2026-03-03", status=PublishStatus.NO_POST, generated_at="2026-03-03T19:00:00", rejection_reasons=["param_stability_failed"], run_id="test-002")
        blocks = build_publish_report_blocks(meta)
        has_reason = any("param_stability_failed" in b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section")
        assert has_reason
