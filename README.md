# Sovereign-Dots ⚡
### Autonomous, Cost-Disciplined Alternative to OpenAI Dots & Open-Dots

> Built on the production-proven **Hetzner + Hermes** multi-tier orchestration architecture.
> Run your private AI operator on a $5/mo Hetzner VPS with zero token drain, self-hosted native MCPs, compounding memory, and deterministic safety gates.

---

## ⚡ The Core Problem with Open-Dots & OpenAI Dots

Projects like [Open-Dots](https://github.com/Anil-matcha/Open-Dots) and OpenAI Dots attempt to provide an AI workspace with tools and approvals. However, they suffer from four critical architectural flaws:

1. **Catastrophic Token Drain:** Monolithic model loops burn expensive reasoning tokens on simple, deterministic operations (sorting inbox messages, parsing URLs, filtering tables).
2. **Third-Party SaaS Lock-In (Composio):** Relying on third-party SaaS connectors introduces monthly subscription fees, high latency, data leakage, and fragile API breakages.
3. **Naive Governance:** Approval systems are often simple JavaScript modals that blindly trust LLM tool generation until human intervention is requested.
4. **Amnesiac Context:** State is stored in flat SQLite tables that fail to compound knowledge across sessions or sync with tools like Obsidian.

---

## 🏛️ How Sovereign-Dots Solves This (The Hetzner Hermes Approach)

```
┌─────────────────────────────────────────────────────────────────┐
│              Sovereign Access (Telegram / Web UI / TUI)         │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│             Chief of Staff Orchestrator (Atlas)                 │
│   - High-Reasoning Intent Classifier (Claude 3.7 / GLM-4)       │
│   - Verification Gate (DONE-WHEN check with 1-pass max bound)   │
└───────────────┬──────────────────────────────────┬──────────────┘
                │                                  │
┌───────────────▼──────────────┐   ┌───────────────▼──────────────┐
│  Specialized Role Workers    │   │  Zero-Token Pipeline (jev)   │
│  - Researcher (Web only)     │   │  - Mechanical sorting/regex  │
│  - Writer (File draft only)  │   │  - Static triage scripts     │
│  - SEO (Search Console)      │   │                              │
│  - Ops (Linear / GitHub)     │   │  * 0 LLM Tokens Burned *     │
│  * Free / Low-Cost Tier *    │   └──────────────────────────────┘
└───────────────┬──────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│                 Governed Action & Safety Engine                 │
│   - Red Lines: Automatic reject (rm -rf, DROP, private keys)    │
│   - Yellow Gate: Ledger-backed dry-run receipts & sign-off      │
│   - Native Self-Hosted MCP Suite (Workspace, Google, Linear)    │
│   - Compounding Brain: Markdown Vault + SQLite vector recall    │
└─────────────────────────────────────────────────────────────────┘
```

### Feature Comparison Matrix

| Capability | OpenAI Dots | Open-Dots (Anil Matcha) | **Sovereign-Dots (Your Stack)** |
| :--- | :--- | :--- | :--- |
| **Hosting Model** | Closed SaaS | Local PC / Prototype Docker | **Production Hetzner VPS ($4–$6/mo)** |
| **Model Cost Strategy** | Fixed OpenAI Pricing | Single model endpoint (expensive) | **Tiered Model Routing + Free Sub-Agents** |
| **Deterministic Tasks** | Burns LLM tokens | Burns LLM tokens | **Zero-Token Mechanical Scripts (`jev.py`)** |
| **Tool Integrations** | Proprietary OpenAI | Third-party **Composio** SaaS | **Native Self-Hosted MCP Servers** |
| **Safety Governance** | Platform filters | Basic deny-by-default prompts | **Two-Tier (Red Lines + Dry-Run Ledger Gate)** |
| **Verification Gate** | None (Blind trust) | None | **Enforced DONE-WHEN verification (1-pass cap)** |
| **Memory System** | Session memory | Flat SQLite rows | **Compounding Markdown Vault + Obsidian sync** |
| **Primary Interface** | Web App | Browser `localhost:3000` | **Telegram Companion + Fast Web Dashboard** |

---

## 🚀 Quick Start

### 1. One-Click Hetzner VPS Deployment

Provision a fresh Debian/Ubuntu VPS on Hetzner Cloud (e.g. CX22 or CPX11) and run:

```bash
# Clone the repository
git clone https://github.com/your-org/sovereign-dots.git /opt/sovereign-dots
cd /opt/sovereign-dots

# Run the 1-click bootstrap script
sudo ./scripts/setup-hetzner.sh your-domain.com
```

The setup script automatically:
- Installs Docker Engine & Docker Compose
- Configures 2GB swap space for low-memory VPS stability
- Sets up UFW firewall rules (SSH, HTTP, HTTPS)
- Generates secure cryptographic tokens and initializes `/opt/data`
- Provisions Caddy with automatic Let's Encrypt SSL certificates

### 2. Configure Environment

Edit `/opt/sovereign-dots/.env`:

```bash
# Set your primary orchestrator key (Claude 3.7, GLM-4, etc.)
PRIMARY_MODEL_PROVIDER=openrouter
PRIMARY_MODEL=anthropic/claude-3.7-sonnet
PRIMARY_MODEL_API_KEY=sk-or-v1-...

# Set your worker fleet key (Free DeepSeek, Nemotron Free, etc.)
WORKER_MODEL_PROVIDER=openrouter
WORKER_MODEL=deepseek/deepseek-chat
WORKER_MODEL_API_KEY=sk-or-v1-...

# (Optional) Add your Telegram Bot Token for mobile access
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_ALLOWED_USER_IDS=your_telegram_id
```

### 3. Launch Services

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Access your secure control plane at `https://your-domain.com`.

---

## 🛠️ Repository Architecture

- `scripts/`:
  - `setup-hetzner.sh`: Complete automated server bootstrap.
  - `deploy.sh`: GitOps deployment script using rsync checksums and zero-downtime reloads.
  - `mechanical_triage.py`: Deterministic zero-token task offloader.
  - `gate_runner.py`: Dry-run and ledger execution validation engine.
- `workspace-template/`:
  - `AGENTS.md`: Security red lines, yellow lines, intent routing, and verification gate rules.
  - `SOUL.md`: Chief of Staff identity, high agency, and token discipline ethos.
  - `TOOLS.md`: MCP server governance and tool execution boundaries.
- `profiles/`:
  - `atlas.yaml`: Chief of Staff orchestrator configuration.
  - `researcher.yaml`: Deep research worker (restricted to web search/browser).
  - `writer.yaml`: Content and technical documentation worker.
  - `seo.yaml`: Search Console worker.
  - `ops.yaml`: Linear / GitHub sprint operations worker.
- `server/`:
  - Python FastAPI async gateway with REST, SSE streaming, and MCP dispatching.
- `web/`:
  - React + Tailwind + Vite dark-mode dashboard for chat, approvals, fleet status, and memory browsing.

---

## 📜 License
MIT License. Sovereign, self-hostable, and inspectable.
