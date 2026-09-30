#!/usr/bin/env bash
# ==============================================================================
# Indy-Dots: deploy.sh — GitOps Reconciliation & Zero-Downtime Sync
# Run after git pull. Safe to execute idempotently.
#
# Usage:
#   ./scripts/deploy.sh             # sync workspace/profiles + reconcile containers
#   REBUILD=1 ./scripts/deploy.sh   # also rebuild images (pick up code changes)
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

  if [ "${REBUILD_CONTAINERS:-0}" = "1" ] || [ "${REBUILD:-0}" = "1" ]; then
    echo "[deploy] rebuilding images (picking up code changes)..."
    docker compose -f "$COMPOSE_FILE" build
  fi

  if [ "${RELOAD_CONTAINERS:-1}" = "1" ]; then
    echo "[deploy] updating and reconciling running containers..."
    docker compose -f "$COMPOSE_FILE" up -d indy-gateway indy-web caddy
    echo "[deploy] services reconciled successfully"
  fi

  # 4. Post-deploy health probe
  echo "[deploy] probing gateway health..."
  for i in $(seq 1 12); do
    if curl -fsS http://127.0.0.1:8642/health >/dev/null 2>&1; then
      echo "[deploy] gateway healthy [✓]"
      break
    fi
    if [ "$i" = "12" ]; then
      echo "[deploy] WARNING: gateway did not become healthy within 60s" >&2
      exit 1
    fi
    sleep 5
  done
fi

echo "[deploy] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — deployment complete [✓]"
