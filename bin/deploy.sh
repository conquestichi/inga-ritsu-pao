#!/usr/bin/env bash
# deploy.sh — VPS上で手動デプロイ
# Usage: /srv/inga/inga-ritsu-pao/bin/deploy.sh [branch]
set -euo pipefail

REPO_DIR="/srv/inga/inga-ritsu-pao"
BRANCH="${1:-main}"

cd "$REPO_DIR"
echo "[deploy] Fetching origin/$BRANCH ..."
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
pip install -e . --break-system-packages -q
echo "[deploy] $(date '+%Y-%m-%d %H:%M:%S') — deployed $(git rev-parse --short HEAD)"
