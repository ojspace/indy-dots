"""Governed connectors: external tool dispatch behind the approval gate.

Every connector action MUST go through
approval_manager.submit_action_for_governance first (which enforces
policy.check_red_lines as the single source of truth). Never execute on
PENDING. Fail closed on network/config error with an honest error dict.
"""

from .github import list_issues, create_issue, READ_ACTIONS, WRITE_ACTIONS
from .mcp_client import dispatch as mcp_dispatch, is_read_tool, MCP_READ_ACTION, MCP_WRITE_ACTION

__all__ = [
    "list_issues",
    "create_issue",
    "mcp_dispatch",
    "is_read_tool",
    "READ_ACTIONS",
    "WRITE_ACTIONS",
    "MCP_READ_ACTION",
    "MCP_WRITE_ACTION",
]
