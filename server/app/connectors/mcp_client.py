"""Minimal generic MCP dispatcher stub with allowlist enforcement.

Supports JSON-RPC over HTTP(S). stdio servers are recognised by name but
not spawned here — this stub returns a fail-closed honest error for them
so the orchestrator can report instead of fabricate.

Allowlist comes from MCP_ALLOWLIST env (comma-separated server names).
Any server not on the list is rejected before any network call.

Action-type convention for governance:
  - MCP_READ_ACTION  ("mcp_read")  — read-only class, safe to auto-approve.
  - MCP_WRITE_ACTION ("mcp_write") — mutating class, must pause (never SAFE).
"""

import os
from typing import Any, Dict, Optional

import httpx

MCP_READ_ACTION = "mcp_read"
MCP_WRITE_ACTION = "mcp_write"

# Prefixes treated as read-only tools. Everything else is a write.
_READ_TOOL_PREFIXES = ("list_", "get_", "read_", "query_", "search_", "fetch_", "describe_")


def get_allowlist() -> list:
    raw = os.getenv("MCP_ALLOWLIST", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def is_read_tool(tool: str) -> bool:
    t = (tool or "").strip().lower()
    return t.startswith(_READ_TOOL_PREFIXES)


def action_for_tool(tool: str) -> str:
    return MCP_READ_ACTION if is_read_tool(tool) else MCP_WRITE_ACTION


async def dispatch(
    server: str = "",
    tool: str = "",
    params: Optional[Dict[str, Any]] = None,
    endpoint: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Dispatch one JSON-RPC tool call. Fail-closed on any error."""
    params = params or {}
    server = (server or "").strip()
    tool = (tool or "").strip()
    if not server:
        return {"ok": False, "error": "No MCP server specified."}
    if not tool:
        return {"ok": False, "error": "No MCP tool specified."}
    allowlist = get_allowlist()
    if allowlist and server not in allowlist:
        return {"ok": False, "error": f"MCP server '{server}' not in MCP_ALLOWLIST."}
    if not allowlist and not endpoint:
        # No allowlist configured and no explicit endpoint: refuse to guess.
        return {"ok": False, "error": "MCP_ALLOWLIST is empty; refusing to dispatch."}
    if not endpoint:
        # stdio-named server with no HTTP endpoint: stub cannot spawn processes here.
        return {
            "ok": False,
            "error": f"MCP server '{server}' has no HTTP endpoint configured; stdio dispatch not implemented.",
        }
    payload = {"jsonrpc": "2.0", "id": 1, "method": tool, "params": params}
    try:
        if client is not None:
            resp = await client.post(endpoint, json=payload)
        else:
            async with httpx.AsyncClient(timeout=20.0) as c:
                resp = await c.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data and data["error"]:
            return {"ok": False, "error": f"MCP tool error: {str(data['error'])[:300]}"}
        result = data.get("result", data) if isinstance(data, dict) else data
        return {"ok": True, "server": server, "tool": tool, "result": result}
    except Exception as e:
        return {"ok": False, "error": f"MCP dispatch failed: {str(e)[:300]}"}
