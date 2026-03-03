#!/usr/bin/env bash
set -euo pipefail
KEY_FILE="$HOME/.ssh/gh_deploy_ritsu_pao"

echo "=== 1. デプロイ用SSHキー生成 ==="
if [[ -f "$KEY_FILE" ]]; then
    echo "  既存キー検出 (スキップ)"
else
    ssh-keygen -t ed25519 -C "ritsu-pao-deploy" -f "$KEY_FILE" -N ""
fi

echo ""
echo "=== GitHub Secrets に登録 ==="
echo "https://github.com/conquestichi/inga-ritsu-pao/settings/secrets/actions"
echo ""
echo "VPS_HOST: 160.251.167.44"
echo "VPS_USER: $(whoami)"
echo ""
echo "VPS_SSH_KEY:"
cat "$KEY_FILE"
echo ""

PUB_KEY=$(cat "${KEY_FILE}.pub")
if ! grep -qF "$PUB_KEY" "$HOME/.ssh/authorized_keys" 2>/dev/null; then
    echo "$PUB_KEY" >> "$HOME/.ssh/authorized_keys"
    chmod 600 "$HOME/.ssh/authorized_keys"
    echo "authorized_keysに追加完了"
else
    echo "authorized_keys: 登録済み"
fi
