#!/usr/bin/env bash
# test_e2e_dryrun.sh — VPS実機 E2E dry-run テスト
#
# 実行: ssh root@160.251.167.44 'bash /srv/inga/inga-ritsu-pao/bin/test_e2e_dryrun.sh'
# または VPS上で直接: bash /srv/inga/inga-ritsu-pao/bin/test_e2e_dryrun.sh
#
set -euo pipefail

echo "============================================"
echo "  因果律 E2E dry-run テスト"
echo "  $(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M:%S JST')"
echo "============================================"
echo ""

PROJECT_DIR="/srv/inga/inga-ritsu-pao"
INGA_OUTPUT="/srv/inga/output/latest"
TEST_OUTPUT="/tmp/ritsu-pao-e2e-test-$(date +%s)"
ASSETS_DIR="/srv/inga/assets"

cd "$PROJECT_DIR"

# ─── Step 0: 環境チェック ───
echo "── Step 0: 環境チェック ──"

echo -n "  Git HEAD: "; git rev-parse --short HEAD
echo -n "  Python: "; python3 --version
echo -n "  pip ritsu-pao: "; pip show ritsu-pao 2>/dev/null | grep Version || echo "NOT INSTALLED"

# 依存パッケージ
for pkg in tweepy google-api-python-client google-auth-oauthlib httpx pydantic; do
    echo -n "  $pkg: "
    python3 -c "import importlib; m=importlib.import_module('$pkg'.replace('-','_').split('-')[0]); print(getattr(m,'__version__','OK'))" 2>/dev/null || echo "MISSING"
done

echo ""

# ─── Step 1: 入力データ確認 ───
echo "── Step 1: 入力データ確認 ──"

CANDIDATES="$INGA_OUTPUT/candidates.json"
GATES="$INGA_OUTPUT/gates_result.json"

if [[ -f "$CANDIDATES" ]]; then
    echo "  ✅ candidates.json found"
    echo -n "    as_of: "; python3 -c "import json; d=json.load(open('$CANDIDATES')); print(d['meta']['as_of'])"
    echo -n "    candidates数: "; python3 -c "import json; d=json.load(open('$CANDIDATES')); print(len(d['candidates']))"
    echo -n "    TOP1: "; python3 -c "import json; d=json.load(open('$CANDIDATES')); c=d['candidates'][0]; print(f\"{c['name']} ({c['ticker']}) score={c['score']}\")"
else
    echo "  ❌ candidates.json NOT FOUND at $CANDIDATES"
    echo "     → inga-quants を先に実行するか、テスト用データを配置してください"
    exit 1
fi

if [[ -f "$GATES" ]]; then
    echo "  ✅ gates_result.json found"
    echo -n "    all_passed: "; python3 -c "import json; print(json.load(open('$GATES'))['all_passed'])"
    echo -n "    regime: "; python3 -c "import json; print(json.load(open('$GATES'))['regime'])"
else
    echo "  ⚠️ gates_result.json not found (publisherがall_passed=Trueでフォールバック)"
fi

echo ""

# ─── Step 2: Publish（台本生成） ───
echo "── Step 2: Publish（台本生成） ──"

mkdir -p "$TEST_OUTPUT"
python3 -m ritsu_pao.publish.publisher \
    --candidates "$CANDIDATES" \
    --gates "$GATES" \
    --output "$TEST_OUTPUT" \
    --config "$PROJECT_DIR/config"

echo ""
echo "  生成ファイル:"
ls -la "$TEST_OUTPUT/" | grep -v "^total\|^d"
echo ""

# meta.json確認
META_STATUS=$(python3 -c "import json; print(json.load(open('$TEST_OUTPUT/meta.json'))['status'])")
echo "  meta.status = $META_STATUS"

if [[ "$META_STATUS" == "ok" ]]; then
    # script_x.json 内容表示
    echo ""
    echo "── Step 2a: X台本プレビュー ──"
    python3 -c "
import json
s = json.load(open('$TEST_OUTPUT/script_x.json'))
print(f\"  パターン: {s['meta'].get('pattern', '?')}\")
print(f\"  文字数: {len(s['body'])}\")
print()
print('  ─── body ───')
for line in s['body'].split('\n'):
    print(f'  {line}')
print()
if s.get('self_reply'):
    print('  ─── self_reply ───')
    for line in s['self_reply'].split('\n'):
        print(f'  {line}')
"

    # script_youtube.json 内容表示
    echo ""
    echo "── Step 2b: YouTube台本プレビュー ──"
    python3 -c "
import json
s = json.load(open('$TEST_OUTPUT/script_youtube.json'))
print(f\"  status: {s['status']}\")
print()
print('  ─── hook ───')
print(f\"  {s['hook']}\")
print('  ─── body ───')
print(f\"  {s['body']}\")
print('  ─── cta ───')
print(f\"  {s['cta']}\")
if s.get('upload_meta'):
    print()
    print(f\"  title: {s['upload_meta'].get('title', '')}\")
"
fi

echo ""

# ─── Step 3: VOICEVOX確認 ───
echo "── Step 3: VOICEVOX確認 ──"
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:50021/version | grep -q "200"; then
    VOICEVOX_VER=$(curl -s http://127.0.0.1:50021/version)
    echo "  ✅ VOICEVOX Engine running (v$VOICEVOX_VER)"
else
    echo "  ❌ VOICEVOX Engine not responding on :50021"
    echo "     → docker start voicevox"
fi

echo ""

# ─── Step 4: 動画生成テスト ───
echo "── Step 4: 動画生成テスト ──"

if [[ "$META_STATUS" == "ok" && -f "$TEST_OUTPUT/script_youtube.json" ]]; then
    echo "  アセット確認:"
    for f in ritsu_loop.mp4 bg_intro.png bg_ticker.png bg_reason.png bg_cta.png bgm_loop.mp3; do
        if [[ -f "$ASSETS_DIR/$f" ]]; then
            echo "    ✅ $f"
        else
            echo "    ❌ $f MISSING"
        fi
    done
    echo ""

    echo "  動画生成中..."
    if python3 -m ritsu_pao.video.pipeline \
        --script "$TEST_OUTPUT/script_youtube.json" \
        --output "$TEST_OUTPUT/final.mp4" \
        --assets "$ASSETS_DIR" \
        --config "$PROJECT_DIR/config/video_config.json" 2>&1; then
        if [[ -f "$TEST_OUTPUT/final.mp4" ]]; then
            SIZE=$(du -h "$TEST_OUTPUT/final.mp4" | cut -f1)
            DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$TEST_OUTPUT/final.mp4" 2>/dev/null | cut -d. -f1)
            echo "  ✅ final.mp4 生成成功 (${SIZE}, ${DURATION}秒)"
        fi
    else
        echo "  ❌ 動画生成失敗"
    fi
else
    echo "  ⏭️ スキップ (meta.status=$META_STATUS)"
fi

echo ""

# ─── Step 5: X投稿 dry-run ───
echo "── Step 5: X投稿 dry-run ──"

X_CREDS="/srv/inga/config/x_credentials.json"
if [[ -f "$X_CREDS" && "$META_STATUS" == "ok" ]]; then
    python3 -m ritsu_pao.post.cli x \
        --publish-dir "$TEST_OUTPUT" \
        --credentials "$X_CREDS" \
        --dry-run
    echo "  ✅ X dry-run 完了"
else
    echo "  ⏭️ スキップ (creds=$([[ -f "$X_CREDS" ]] && echo 'found' || echo 'missing'), status=$META_STATUS)"
fi

echo ""

# ─── Step 6: YouTube dry-run ───
echo "── Step 6: YouTube dry-run ──"

YT_SECRET="/srv/inga/config/client_secret.json"
YT_TOKEN="/srv/inga/config/youtube_token.json"
if [[ -f "$YT_SECRET" && -f "$YT_TOKEN" && -f "$TEST_OUTPUT/final.mp4" && "$META_STATUS" == "ok" ]]; then
    python3 -m ritsu_pao.post.cli youtube \
        --publish-dir "$TEST_OUTPUT" \
        --client-secret "$YT_SECRET" \
        --token "$YT_TOKEN" \
        --dry-run
    echo "  ✅ YouTube dry-run 完了"
else
    echo "  ⏭️ スキップ (secret=$([[ -f "$YT_SECRET" ]] && echo 'found' || echo 'missing'), token=$([[ -f "$YT_TOKEN" ]] && echo 'found' || echo 'missing'), video=$([[ -f "$TEST_OUTPUT/final.mp4" ]] && echo 'found' || echo 'missing'), status=$META_STATUS)"
fi

echo ""

# ─── Step 7: 禁止表現チェック ───
echo "── Step 7: 禁止表現チェック ──"
python3 -c "
import json, sys
banned = json.load(open('$PROJECT_DIR/config/reply_config.json'))['banned_words']
errors = []
for fname in ['script_x.json', 'script_youtube.json', 'note.md']:
    path = '$TEST_OUTPUT/' + fname
    try:
        text = open(path).read()
        for w in banned:
            if w in text:
                errors.append(f'{fname}: 禁止語「{w}」検出')
    except FileNotFoundError:
        pass
if errors:
    for e in errors:
        print(f'  ❌ {e}')
    sys.exit(1)
else:
    print('  ✅ 全出力ファイルで禁止表現なし')
"

echo ""

# ─── 結果サマリー ───
echo "============================================"
echo "  E2E dry-run テスト完了"
echo "  出力: $TEST_OUTPUT/"
echo "============================================"
echo ""
echo "生成ファイル一覧:"
ls -la "$TEST_OUTPUT/"
echo ""
echo "次のステップ:"
echo "  1. 上記のX台本/YouTube台本を目視確認"
echo "  2. final.mp4 を再生して動画品質確認"
echo "  3. 問題なければ --dry-run を外して本番投稿テスト"
