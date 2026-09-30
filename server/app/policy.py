"""
policy.py — Single source of truth for Indy-Dots safety policy.

Both the API gateway (approval_manager) and the standalone CLI runner
(gate_runner) MUST evaluate actions through this module so red-line rules
can never drift between enforcement points.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

# --- RED LINES: hard rejection, never executed, no override ---------------
# (pattern, human-readable reason). Matched against the JSON-serialized
# action payload.
RED_LINES: List[Tuple[str, str]] = [
    ("rm -rf", "Irreversible destructive filesystem action"),
    ("git push --force", "History rewriting on remote"),
    ("DROP TABLE", "Database destruction"),
    ("DELETE FROM", "Bulk database destruction"),
    ("id_rsa", "Private credential exposure"),
    (".env", "Environment secret file access"),
    ("eval(", "Dynamic code execution"),
    ("/etc/sudoers", "Privilege escalation"),
    ("authorized_keys", "SSH key injection"),
    ("| sh", "Unsandboxed remote script execution"),
    ("|bash", "Unsandboxed remote script execution"),
    ("| bash", "Unsandboxed remote script execution"),
]

# --- YELLOW LINES: mutating intents that pause for operator sign-off ------
MUTATION_INTENTS: Tuple[str, ...] = (
    "send email", "send an email", "post to", "publish", "tweet",
    "create issue", "create ticket", "update issue", "update ticket",
    "close issue", "close ticket", "assign ticket", "assign issue",
    "delete", "remove", "archive", "deploy", "restart",
)


def check_red_lines(payload: Any) -> Optional[Tuple[str, str]]:
    """
    Return (pattern, reason) for the first red-line hit inside `payload`,
    or None if clean. `payload` may be any JSON-serializable value.
    """
    try:
        payload_str = json.dumps(payload)
    except (TypeError, ValueError):
        payload_str = str(payload)
    for pattern, reason in RED_LINES:
        if pattern.lower() in payload_str.lower():
            return pattern, reason
    return None
