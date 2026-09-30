#!/usr/bin/env bash
# ==============================================================================
# Indy-Dots: 1-Click Hetzner VPS Bootstrap Script
# Tested on Ubuntu 22.04 / 24.04 LTS (Hetzner Cloud CX22, CPX11, CAX11)
# ==============================================================================
set -euo pipefail

echo "======================================================"
echo "    INDY-DOTS — HETZNER CLOUD PROVISIONER        "
echo "======================================================"

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root (or with sudo)."
  exit 1
fi

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
  echo "[!] No domain passed. Usage: ./setup-hetzner.sh <your-domain.com or IP>"
  read -p "Enter your domain or VPS public IP: " DOMAIN
fi

echo "[+] Updating apt repositories & upgrading packages..."
apt-get update -qq && apt-get upgrade -y -qq

echo "[+] Installing foundational packages (curl, git, ufw, jq, rsync)..."
apt-get install -y -qq curl git ufw jq rsync htop ca-certificates gnupg lsb-release

# 1. Setup 2GB Swap (Essential for $4-$6 VPS stability)
if [ ! -f /swapfile ]; then
  echo "[+] Setting up 2GB swap space for VPS stability..."
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile none swap' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl vm.swappiness=10
  grep -q '^vm.swappiness=10' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
else
  echo "[*] Swap file already present."
fi

# 2. Configure Firewall (UFW)
echo "[+] Configuring UFW firewall rules..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 3. Install Docker & Docker Compose Plugin
if ! command -v docker &> /dev/null; then
  echo "[+] Installing Docker Engine & Compose plugin..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable docker
  systemctl start docker
else
  echo "[*] Docker already installed."
fi

# 4. Provision Persistent Host Directories
echo "[+] Creating persistent Indy-Dots directories at /opt/data..."
mkdir -p /opt/data/{workspace,vault,profiles,google,handoffs,logs,backups}
# 755 (not 750): the gateway runs as an unprivileged UID inside the container
# and needs traversal; secrets are protected individually (e.g. .env is 600).
chmod -R 755 /opt/data

# 5. Generate Environment Configuration if absent
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "$REPO_DIR/.env" ]; then
  echo "[+] Generating production .env file with secure secrets..."
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  
  RANDOM_SECRET=$(openssl rand -hex 32)
  sed -i "s|change-me-to-a-secure-random-token-min-32-chars|$RANDOM_SECRET|g" "$REPO_DIR/.env"
  sed -i "s|ENVIRONMENT=development|ENVIRONMENT=production|g" "$REPO_DIR/.env"
  # Caddy reads {$DOMAIN} from the container environment (see env_file in
  # docker-compose.prod.yml) — never sed-edit Caddyfile per-host, just set it.
  grep -q '^DOMAIN=' "$REPO_DIR/.env" \
    && sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" "$REPO_DIR/.env" \
    || echo "DOMAIN=$DOMAIN" >> "$REPO_DIR/.env"

  chmod 600 "$REPO_DIR/.env"
  echo "[!] IMPORTANT: A secure AUTH_TOKEN was generated and written to $REPO_DIR/.env"
  echo "[!] (Never printed to stdout — read it from the file if needed.)"
  echo "[!] Please edit $REPO_DIR/.env to insert your primary model provider API key."
fi

# 6. Copy Seed Workspace files
echo "[+] Syncing initial workspace protocols and role profiles..."
rsync -av --checksum "$REPO_DIR/workspace-template/" "/opt/data/workspace/"
rsync -av --checksum "$REPO_DIR/profiles/" "/opt/data/profiles/"

echo "======================================================"
echo "[✓] HETZNER VPS PROVISIONING COMPLETE!"
echo ""
echo "Next steps:"
echo " 1. Edit .env:  nano $REPO_DIR/.env"
echo " 2. Start stack: cd $REPO_DIR && docker compose -f docker-compose.prod.yml up -d --build"
echo " 3. Access UI:  https://$DOMAIN"
echo "======================================================"
