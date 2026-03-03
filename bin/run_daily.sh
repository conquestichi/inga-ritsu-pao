#!/usr/bin/env bash
# run_daily.sh — 因果律 ritsu-pao 日次パブリッシュパイプライン
#
# Usage: /srv/inga/inga-ritsu-pao/bin/run_daily.sh
# Cron:  0 19 * * 1-5  (Mon-Fri 19:00 JST, inga-quants 18:30完了後)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INGA_OUTPUT="/srv/inga/output/latest"
PUBLISH_OUTPUT="/srv/inga/output/publish/latest"

# ── 環境変数読込 ──
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

# ── JPXカレンダーチェック（非営業日はスキップ）──
if python3 -c "
from datetime import date
import json
from pathlib import Path
holidays_file = Path('/srv/inga/config/jpx_holidays.json')
if holidays_file.exists():
    holidays = set(json.loads(holidays_file.read_text()))
    today = date.today().isoformat()
    if today in holidays:
        exit(1)
    if date.today().weekday() >= 5:
        exit(1)
else:
    if date.today().weekday() >= 5:
        exit(1)
" 2>/dev/null; then
    echo "[ritsu-pao] Trading day confirmed"
else
    echo "[ritsu-pao] Non-trading day, skipping"
    exit 0
fi

# ── candidates.json存在チェック ──
CANDIDATES="$INGA_OUTPUT/candidates.json"
if [[ ! -f "$CANDIDATES" ]]; then
    echo "[ritsu-pao] ERROR: candidates.json not found at $CANDIDATES"
    exit 1
fi

# ── gates_result.json（ない場合もpublisherが対応） ──
GATES="$INGA_OUTPUT/gates_result.json"

# ── Publish実行 ──
echo "[ritsu-pao] Starting publish pipeline..."
cd "$PROJECT_DIR"
python3 -m ritsu_pao.publish.publisher \
    --candidates "$CANDIDATES" \
    --gates "$GATES" \
    --output "$PUBLISH_OUTPUT" \
    --config "$PROJECT_DIR/config"

# ── Slack通知 ──
echo "[ritsu-pao] Sending Slack notifications..."
python3 -m ritsu_pao.notify.cli \
    --publish-dir "$PUBLISH_OUTPUT"

echo "[ritsu-pao] Pipeline complete"
