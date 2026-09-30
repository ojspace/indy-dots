"""Opt-in computer runtime (P4) — governed browser/computer actions.

Default provider is the inert `fake` stub (deterministic, no browser, no
network), so the runtime is OFF unless the operator opts in via
COMPUTER_PROVIDER=docker|remote.

Governance contract (shared by the orchestrator stage 2.5b and the
POST /api/computer/act endpoint — one path, no forks):

- action_type is always COMPUTER_ACTION ("computer_navigate"), which is
  NEVER in ApprovalManager.SAFE_ACTIONS. The first pass therefore always
  pauses as PENDING_APPROVAL with a dry_run receipt, or hard-stops as
  REJECTED_RED_LINE when computer params trip policy.py red lines.
- Never execute on PENDING: the provider runs only when the gate returns
  approved=True. Provider errors surface as honest ok=False results.

Gateway + approver share one process (SECURITY.md), so this runtime stays
non-hardened and off by default. Not a sandbox for hostile web content.
"""

import os
import re
from typing import Any, Dict, Optional, Tuple

from ..config import settings
from .base import ActionResult, ComputerProvider

COMPUTER_ACTION = "computer_navigate"
COMPUTER_OPS = ("navigate", "snapshot", "click", "type", "browse")

# Narrow: only an explicit "computer <verb>" asks for the runtime.
# Never matches email, publish, deploy, or other generic mutations.
_COMPUTER_RE = re.compile(
    r"\bcomputer\s+(navigate|snapshot|click|type|browse)\b[^\S\n]*(?P<target>[^\n]{0,500})?",
    re.IGNORECASE,
)


def detect_computer_request(prompt: str) -> Optional[Dict[str, Any]]:
    """Return the governed computer request for a prompt, or None.

    The payload carries op/target/summary so check_red_lines (single
    source of truth in policy.py, enforced inside submit) rejects
    red-line content in computer params.
    """
    if not prompt or "computer" not in prompt.lower():
        return None
    m = _COMPUTER_RE.search(prompt)
    if not m:
        return None
    op = m.group(1).lower()
    target = ((m.group("target") or "").strip().strip("\"'"))[:500]
    return {
        "action_type": COMPUTER_ACTION,
        "op": op,
        "target": target,
        "payload": {
            "op": op,
            "target": target,
            "summary": prompt.strip()[:200],
        },
    }


def get_provider(name: Optional[str] = None) -> ComputerProvider:
    """Factory reading COMPUTER_PROVIDER (fake|docker|remote, default fake).

    Precedence: explicit arg > live COMPUTER_PROVIDER env > settings >
    fake. Unknown values fall back to fake (fail-safe default).
    """
    raw = (
        (name or "").strip()
        or (os.getenv("COMPUTER_PROVIDER", "") or "").strip()
        or (getattr(settings, "computer_provider", "") or "").strip()
        or "fake"
    )
    key = raw.lower()
    if key == "docker":
        from .docker import DockerComputerProvider

        return DockerComputerProvider()
    if key == "remote":
        from .remote import RemoteComputerProvider

        return RemoteComputerProvider()
    from .fake import FakeComputerProvider

    return FakeComputerProvider()


async def governed_computer_action(
    op: str,
    target: str = "",
    caller: str = "orchestrator",
    assistant: str = "default",
    provider: Optional[ComputerProvider] = None,
) -> Tuple[Dict[str, Any], Optional[ActionResult]]:
    """Shared governed path: submit COMPUTER_ACTION, execute only if approved.

    Returns (gate, result-or-None). result is None when the gate pauses
    (PENDING_APPROVAL) or hard-stops (REJECTED_RED_LINE) — the caller must
    NOT execute in that case. Provider failures return ok=False results,
    never raise.
    """
    from ..gates.approval_manager import approval_manager

    op = (op or "").strip().lower() or "navigate"
    gate = approval_manager.submit_action_for_governance(
        action_type=COMPUTER_ACTION,
        payload={
            "op": op,
            "target": (target or "")[:500],
            "assistant": (assistant or "default")[:64],
            "summary": f"computer {op} {(target or '').strip()[:200]}",
        },
        caller=caller,
    )
    if not gate.get("approved"):
        return gate, None
    prov = provider or get_provider()
    try:
        if op in ("navigate", "browse"):
            result = await prov.navigate(target or "", assistant=assistant)
        elif op == "snapshot":
            result = await prov.snapshot(assistant=assistant)
        else:
            result = await prov.act(op, target or "", assistant=assistant)
    except Exception as e:
        result = ActionResult(
            ok=False,
            provider=getattr(prov, "name", "unknown"),
            op=op,
            error=f"Computer runtime failed: {str(e)[:200]}",
        )
    return gate, result


__all__ = [
    "ActionResult",
    "COMPUTER_ACTION",
    "COMPUTER_OPS",
    "ComputerProvider",
    "detect_computer_request",
    "get_provider",
    "governed_computer_action",
]
