# Security Policy

## Reporting a vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Open a private security advisory via GitHub (**Security → Advisories → New draft security advisory**), or contact the maintainers directly. You should get a response within 72 hours.

## Security model

Indy-Dots is a self-hosted control plane holding real credentials (LLM API keys) and a governance ledger. Its posture:

### Authentication
- Every operator route (`/api/*`) requires `Authorization: Bearer <AUTH_TOKEN>`. Only `/health` is open (for container healthchecks).
- In `ENVIRONMENT=production` the gateway **refuses to boot** with a missing, default, or short (<32 char) token.
- The web dashboard holds the token in `localStorage` (build-time `VITE_AUTH_TOKEN` or user-entered). Treat the dashboard as bearing the token's authority.

### Network
- In production, `indy-gateway` and `indy-web` bind to `127.0.0.1` only — all public traffic terminates at Caddy with automatic HTTPS.
- UFW is configured during bootstrap, but note: **Docker bypasses UFW for published ports**. The loopback binds above are the actual protection — do not change them to `0.0.0.0`.
- CORS is restricted to `ALLOWED_ORIGINS` (no wildcard + credentials).

### Governance (application layer)
- **Red Lines** (`.env` access, `id_rsa`, `rm -rf`, `DROP TABLE`, force-push, pipe-to-shell, sudoers/authorized_keys tampering) are auto-rejected with a ledger entry — including for "read" requests.
- **Yellow Lines** (publishing, emailing, ticket mutations, deletions, deploys) pause as `PENDING_APPROVAL` with a dry-run receipt until an operator resolves them via the API/UI.
- The ledger (`gate_ledger.jsonl`) is append-only and auditable; a single shared policy module (`server/app/policy.py`) backs both the gateway and the CLI runner so rules cannot drift.

### Secrets at rest
- Provider keys resolve **env var > encrypted store > ""**. Keys saved via
  `POST /api/settings/keys` are Fernet-encrypted (`APP_ENCRYPTION_KEY`, or a
  generated `DATA_DIR/.encryption_key`) into `DATA_DIR/.provider_keys.json`.
  Both files are `chmod 600`. Plaintext keys are never logged or echoed —
  `GET /api/settings/keys` returns names + `configured` bools only, and a
  blank save preserves the stored value.
- Threat model: anyone with the box (or `APP_ENCRYPTION_KEY`) can decrypt the
  store. This protects backups and casual file reads, not a root compromise.

### Known limitations (read before exposing beyond localhost)
- Single static bearer token — no per-user identity, rotation, or rate limiting yet.
- The approval API and the orchestrator run in the same process; an RCE in the gateway bypasses the gate.
- The opt-in computer runtime (P4) is **not a hardened sandbox for hostile web**:
  the gateway and approver share one process (see above), the docker profile's
  read-only rootfs + dropped caps + resource limits are containment intent, not a
  browser-exploit boundary, and the default `fake` provider is inert. Only point
  it at untrusted pages from an isolated host you can afford to lose.
- The verification gate calls your configured LLM; prompt-injection resistance of that verifier is not guaranteed.
- SSE endpoint is POST-based; ensure proxies in front do not cache it.
- The routine scheduler runs **in-process only** (no multi-worker/durable queue):
  do not scale the gateway past one replica with `ROUTINES_ENABLED=1`, or
  routines will run once per replica. It is OFF by default.

## Hardened deployment checklist
1. `scripts/setup-hetzner.sh <domain>` (generates a 64-hex token into `.env` with `chmod 600`, never printed)
2. Put real model API keys in `.env`; keep `ENVIRONMENT=production`
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. Confirm `curl http://127.0.0.1:8642/api/profiles` returns **401** from the VPS itself
5. Confirm `https://<domain>/api/approvals` returns **401** without a token
