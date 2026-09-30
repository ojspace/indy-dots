# TOOLS.md — Native Model Context Protocol (MCP) Governance

Indy-Dots uses self-hosted native MCP servers rather than external third-party middleware.

### 1. `mcp-workspace` (Local Host & Container Tools)
- `file_read`: Read files up to 100,000 chars.
- `file_write`: Write files safely to `/opt/data/` or designated project dirs.
- `file_search`: Fast ripgrep search respecting `.gitignore`.
- `terminal_run`: Execute sandboxed shell commands.

### 2. `mcp-google` (Workspace Suite)
- `gmail_list`, `gmail_read`: Read messages. Sending goes through the approval gate.
- `calendar_list_events`: Check schedules.
- `drive_search`: Query documents.
- `search_console_query`: Fetch site search impressions and ranking queries.

### 3. `mcp-linear` (Task & Sprint Tracking)
- `linear_list_issues`, `linear_get_issue`: Inspect tickets.
- `linear_create_issue`, `linear_update_issue`: Create and modify work items.
- *Notice:* Delete/archive operations are hard-blocked at the gateway.

### 4. `mcp-browser` (Sandboxed Headless Playwright)
- `browser_navigate`, `browser_screenshot`, `browser_extract_text`: Inspect live web pages securely without executing untrusted external binary payloads.
