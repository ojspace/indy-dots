# Indy-Dots ⚡
### Self-Hosted AI Teammates — the open, cost-disciplined counterpart to OpenAI's Dot & xAI's Grok Bot

<p align="center">
  <img src="web/public/brand/hero.png" alt="Indy-Dots — governed orchestrator with specialized agent fleet on a self-hosted VPS" width="820" />
</p>

> Run a private AI operator on a $5/mo Hetzner VPS: tiered model routing, zero-token
> mechanical triage, ledger-backed safety gates, and a compounding Markdown vault.
> No SaaS connectors. No fabricated dashboards. MIT licensed.

---

## 🙏 Credits: the products that defined this category

Indy-Dots exists because two closed products proved that AI teammates — not chatbots —
are how this technology should work:

- **[Grok Bot](https://grok.com) (xAI)** — the blueprint for bot teams. Bots that sign
  in to your tools once and use them like you do, work in parallel 24/7, learn routines
  by watching you do a task once, and — the part we admire most — **pause for operator
  approval before anything goes out** ("36 drafts queued · 0 sent"). Its fleet even
  ships a **Chief of Staff** coordinating the specialists; our `atlas` profile is a
  direct homage to that design.
- **OpenAI's Dot bot** — for mainstreaming the "dots" vision: many small, specialized
  agents orbiting one orchestrator, doing real work in your tools instead of chatting
  about it.

*(and to [Open-Dots](https://github.com/Anil-matcha/Open-Dots) for showing an open
implementation of the idea was possible.)*

Both Grok Bot and Dot are brilliant. Both are also closed SaaS: seat pricing, their
cloud, their guardrails, their definition of "safe". **Indy-Dots takes the same vision
and inverts the trade: you own the loop.**

### What self-hosting changes

| Concern | Grok Bot / Dot (SaaS) | Indy-Dots (self-hosted) |
| :--- | :--- | :--- |
| **Hosting** | Their cloud | Your $4–6/mo Hetzner VPS — nothing leaves your box except model calls you choose |
| **Price** | $20–$40/seat/mo | VPS + your own model keys; free/cheap worker tiers for specialists |
| **Cost discipline** | Opaque usage limits | Zero-token mechanical routing + tiered fleet; every dispatch is visible |
| **Approval gates** | Bots pause for your OK (a great idea!) | Same pattern, but enforced in code: append-only JSONL ledger, dry-run receipts, red lines you define in one file |
| **Verification** | Trust the bot's report | Evidence-based gate: outputs must cite links/paths/data or they fail; fail-closed; 1 corrective pass |
| **Secrets** | Handled inside their platform | Auto-rejected at the gate with a ledger trail — even read-style requests |
| **Memory** | On their servers | Your Markdown vault + SQLite index — exportable, Obsidian-friendly, compounds across restarts |
| **License** | Closed | MIT — inspect it, fork it, run it anywhere |

If you want the polished SaaS experience and accept the trade, pay them — they're good.
If you want the same teammate pattern running under **your** keys on a **$5** VPS with
**auditable** governance, keep reading.

---

## What Indy-Dots actually does (and doesn't) do today

**Working:**
- **Two-tier model routing** — a zero-token mechanical classifier routes every task
  (`/research`, `/write`, `/seo`, `/ops`, `/code`, or natural language) to a free/cheap
  worker model or the primary reasoning model. Classification never costs tokens.
- **Governed action gates** — mutating requests (publish, email, ticket writes, deletes,
  deploys) pause as `PENDING_APPROVAL` with a dry-run receipt in an append-only JSONL
  ledger. Red-line content (`.env`, `id_rsa`, `rm -rf`, `DROP TABLE`, force-push,
  pipe-to-shell) is auto-rejected — even for "read" requests.
- **Fail-closed verification gate** — outputs must contain concrete evidence (links,
  paths, code, data). On failure: exactly one corrective pass, then halt and report.
  If the verifier itself is unreachable, the output is marked unverified — never passed.
- **Compounding vault** — verified research outputs persist as Obsidian-style Markdown
  + a SQLite index, and are recalled into future task context.
- **Real dashboard** — chat, approvals queue, live fleet from `profiles/*.yaml`, vault
  browser, and metrics computed from the actual ledger (no placeholder numbers).
- **One-command Hetzner bootstrap** — swap, UFW, Docker, secrets generation, HTTPS via Caddy.

**Not yet (tracked as roadmap):**
- Tool execution behind the gate (Linear/Gmail/GitHub MCP dispatchers) — the gate
  records and pauses actions today; the MCP executors are the next milestone.
- Telegram companion, embeddings-based vault recall, multi-user auth.

---

## Architecture

```
<p align="center">
  <img src="web/public/brand/architecture.png" alt="Indy-Dots architecture: dashboard → orchestrator core (gates + vault) → Docker services on the VPS" width="720" />
</p>

```

---

## Quick Start

### 1. One-command Hetzner deployment

Provision a fresh Ubuntu 22.04/24.04 VPS (CX22/CPX11/CAX11) pointed at your domain, then:

```bash
git clone https://github.com/your-org/indy-dots.git /opt/indy-dots
cd /opt/indy-dots
sudo ./scripts/setup-hetzner.sh your-domain.com
```

The bootstrap script installs Docker + Compose, configures 2GB swap and UFW,
generates a 64-hex `AUTH_TOKEN` into `.env` (`chmod 600`, never printed to stdout),
and syncs workspace protocols and role profiles to `/opt/data`.

### 2. Configure models

```bash
nano /opt/indy-dots/.env
```

```bash
# Primary reasoning model (Chief of Staff, coder, verification)
PRIMARY_MODEL=anthropic/claude-3.7-sonnet
PRIMARY_MODEL_API_KEY=sk-or-v1-...

# Worker fleet (researcher, writer, seo, ops) — free/cheap tier
WORKER_MODEL=deepseek/deepseek-chat
WORKER_MODEL_API_KEY=sk-or-v1-...
```

Any OpenAI-compatible endpoint works (OpenRouter, Nebius, Groq, DeepSeek, Ollama).
With **no API key configured, the gateway still runs** — routing and gates work,
the model step reports honestly that it is not configured.

### 3. Launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Open `https://your-domain.com`, click **Set token**, paste your `AUTH_TOKEN`.

> The web build can also bake the token at build time via `VITE_AUTH_TOKEN`
> (see `docker-compose.prod.yml`). The server enforces the same token on every
> route either way.

### Local development

```bash
# Backend
cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8642   # AUTH_TOKEN=test-token-abcdef123456 for dev

# Frontend
cd web && npm install && npm run dev        # proxies /api via nginx in Docker;
                                            # for `npm run dev`, set VITE_GATEWAY_URL=http://localhost:8642

# Tests
cd server && pytest tests/ -q
```

---

## Repository Layout

```
server/
  app/
    main.py                 # FastAPI gateway (auth on every /api route)
    auth.py                 # Bearer auth + production boot guard
    config.py               # Env settings
    policy.py               # ★ Single source of truth: red lines + mutation intents
    profiles.py             # Loads profiles/*.yaml into the fleet
    mechanical_triage.py    # ★ Zero-token intent classifier (canonical)
    orchestrator/
      chief_of_staff.py     # Task pipeline: route → recall → gate → dispatch → verify → vault
      verification_gate.py  # Evidence check, fail-closed, 1-pass corrective
    gates/
      approval_manager.py   # Yellow-gate ledger + approval resolution
    memory/vault.py         # Markdown + SQLite compounding memory
  tests/                    # 71 tests: policy, triage, gates, API, boot guard
profiles/                   # Role definitions (atlas, researcher, writer, seo, ops, coder)
workspace-template/         # AGENTS.md / SOUL.md / TOOLS.md protocols synced to the VPS
scripts/
  setup-hetzner.sh          # 1-command VPS bootstrap
  deploy.sh                 # GitOps sync; REBUILD=1 picks up code changes
  gate_runner.py            # Standalone CLI gate (same policy module as the server)
web/                        # React dashboard: chat, approvals, fleet, vault, metrics
web/public/brand/           # Logo, hero, architecture visuals
```

---

## Safety model

See [SECURITY.md](SECURITY.md) for the full model and the hardened-deployment
checklist. Short version:

- **Red lines** auto-reject: secrets access, destructive commands, privilege escalation,
  remote script execution — logged, never executed.
- **Yellow lines** pause for operator sign-off with a dry-run receipt in the ledger.
- Production refuses to boot without a strong `AUTH_TOKEN`.
- Gateway and web bind to loopback in prod; Caddy terminates public HTTPS.

## Contributing

PRs welcome. `pytest tests/ -q` and `npm run build` must pass (CI enforces both).
If you touch safety behavior, `server/app/policy.py` is the single place to change —
both the gateway and the CLI runner consume it, and its tests enumerate every rule.

## License

MIT — see [LICENSE](LICENSE).
