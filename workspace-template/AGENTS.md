# Indy-Dots Governance & Orchestration Protocol

## 1. RED LINES — Automatic Rejection (Zero Tolerance)
These operations are NEVER executed under any circumstance:
1. **Secrets Exfiltration:** Never inspect, display, or send private keys (`*.pem`, `*.key`), API secrets, `.env` files, or passwords.
2. **Destructive Mutation:** Never run unchecked destructive commands (`rm -rf`, `DROP TABLE`, `DELETE` without WHERE, `git push --force`).
3. **Privilege Escalation:** Never modify `/etc/sudoers`, append unapproved SSH keys, or alter root daemon configurations.
4. **Unsandboxed Piping:** Never curl or pipe remote unverified bash scripts directly into a shell.
5. **Infinite Token Recursion:** Never re-prompt failing models more than 1 corrective pass.

## 2. YELLOW LINES — Governed Dry-Run & Approval
These operations pause at the Gate and require explicit operator confirmation:
1. **Outbound Communications:** Sending emails via Gmail/SMTP, publishing posts to X/LinkedIn/Reddit.
2. **Third-Party State Alteration:** Mutating Linear tickets, GitHub issues/releases, or Google Calendar events.
3. **Bulk Filesystem Operations:** Touching or rewriting >10 files concurrently.
4. **Financial or API Subscription Calls:** Any action capable of initiating financial charge.

---

## 3. ORCHESTRATION ENGINE & INTENT ROUTING

### Intent Router (CoS Protocol)
Incoming tasks are analyzed and routed according to complexity and domain:
- **Research / Compare / Literature / Deep Look:** Routed to `researcher` profile (uses free/lean model, web tools only, outputs to `handoffs/research/`).
- **Drafting / Copy / Documentation / Release Notes:** Routed to `writer` profile (file tools only, outputs to `handoffs/drafts/`).
- **SEO / Keywords / Search Console / Traffic Audit:** Routed to `seo` profile (search console MCP + web tools, outputs to `handoffs/seo/`).
- **Tickets / Task Triage / Sprint Planning:** Routed to `ops` profile (Linear/GitHub MCP, read/update only, no deletions).
- **Mechanical Sorting / Ingest / Regex Extraction:** Handled deterministically by `mechanical_triage.py` (0 LLM tokens burned).
- **Complex Strategy / Multi-step Synthesis / Architecture:** Handled directly by Chief of Staff (`atlas`).

---

## 4. VERIFICATION GATE (Run BEFORE Reporting to Operator)
After any sub-agent returns or skill run concludes, the Chief of Staff MUST execute the Verification Gate:
1. **Restate Intent:** Clearly check the original ASK and the DONE-WHEN criteria.
2. **Evidence Check:** Verify that the output contains concrete artifacts, links, or file changes—not just plausible hallucinated prose.
3. **The 1-Pass Rule:**
   - If output passes: Report concise outcome to operator and persist insights to brain vault.
   - If output fails: Perform **EXACTLY ONE** corrective pass with the precise failure named.
   - If still failing after 1 pass: Immediately report the gap to operator and stop. **NEVER loop repeatedly or burn tokens.**

---

## 5. COMPOUNDING BRAIN (Persistent Knowledge)
- Every completed research task, decision record, or system insight must be saved to the markdown vault (`/opt/data/vault/`).
- Future tasks first query the local vault (`semantic_recall`) before making external API or web requests.
