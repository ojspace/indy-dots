#!/usr/bin/env bash
# ==============================================================================
# Sovereign-Dots: deploy.sh — GitOps Reconciliation & Zero-Downtime Sync
# Run after git pull. Safe to execute idempotently.
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${DATA_DIR:-/opt/data}"
WORKSPACE_DIR="$DATA_DIR/workspace"
PROFILES_DIR="$DATA_DIR/profiles"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"

echo "[deploy] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — starting reconciliation"

# 1. Sync Workspace Protocols (AGENTS.md, SOUL.md, TOOLS.md, USER.md)
if [ -d "$REPO_DIR/workspace-template" ]; then
  rsync -av --checksum "$REPO_DIR/workspace-template/" "$WORKSPACE_DIR/"
  echo "[deploy] workspace protocols synced"
fi

# 2. Sync Role Profiles (Chief of Staff + Worker Fleet)
if [ -d "$REPO_DIR/profiles" ]; then
  rsync -av --checksum "$REPO_DIR/profiles/" "$PROFILES_DIR/"
  echo "[deploy] agent profiles synced"
fi

# 3. Health & Config Verification
if [ -f "$COMPOSE_FILE" ]; then
  echo "[deploy] verifying docker-compose configuration..."
  docker compose -f "$COMPOSE_FILE" config >/dev/null
  
  if [ "${RELOAD_CONTAINERS:-1}" = "1" ]; then
    echo "[deploy] updating and reconciling running containers..."
    docker compose -f "$COMPOSE_FILE" up -d --no-build sovereign-gateway sovereign-web caddy
    echo "[deploy] services reconciled successfully"
  fi
fi

echo "[deploy] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — deployment complete [✓]"
