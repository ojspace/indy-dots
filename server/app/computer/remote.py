"""Remote computer provider stub (opt-in, off by default).

Delegates to an external computer-runtime service via COMPUTER_REMOTE_URL
(+ optional COMPUTER_REMOTE_TOKEN bearer). Fail-closed: when the endpoint
is not configured, or on any network/protocol error, returns ok=False —
never raises, never fabricates. The token is never logged or returned.
"""

import os
from typing import Any, Dict

import httpx

from .base import ActionResult, ComputerProvider

TIMEOUT_SECONDS = 30.0


def _eff_url() -> str:
    url = (os.getenv("COMPUTER_REMOTE_URL", "") or "").strip()
    if url:
        return url
    try:
        from ..config import settings

        return (getattr(settings, "computer_remote_url", "") or "").strip()
    except Exception:
        return ""


def _eff_token() -> str:
    token = (os.getenv("COMPUTER_REMOTE_TOKEN", "") or "").strip()
    if token:
        return token
    try:
        from ..config import settings

        return (getattr(settings, "computer_remote_token", "") or "").strip()
    except Exception:
        return ""


class RemoteComputerProvider(ComputerProvider):
    name = "remote"

    async def _call(self, op: str, payload: Dict[str, Any]) -> ActionResult:
        url = _eff_url().rstrip("/")
        if not url:
            return ActionResult(
                ok=False, provider=self.name, op=op,
                error="COMPUTER_REMOTE_URL not configured; remote computer runtime fails closed.",
            )
        headers = {"Content-Type": "application/json"}
        token = _eff_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                resp = await client.post(url + "/act", json={"op": op, **payload}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return ActionResult(
                ok=False, provider=self.name, op=op,
                error=f"Remote computer call failed: {str(e)[:200]}",
            )
        if not isinstance(data, dict) or "ok" not in data:
            return ActionResult(
                ok=False, provider=self.name, op=op,
                error="Remote computer returned unexpected response; fails closed.",
            )
        if data.get("ok"):
            result_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
            return ActionResult(ok=True, provider=self.name, op=op, data=result_data)
        return ActionResult(
            ok=False, provider=self.name, op=op,
            error=str(data.get("error", "Remote computer action failed."))[:300],
        )

    async def navigate(self, target: str = "", assistant: str = "default") -> ActionResult:
        t = (target or "").strip()
        if not t:
            return ActionResult(
                ok=False, provider=self.name, op="navigate",
                error="No navigation target provided.",
            )
        return await self._call("navigate", {"target": t, "assistant": assistant})

    async def snapshot(self, assistant: str = "default") -> ActionResult:
        return await self._call("snapshot", {"assistant": assistant})

    async def act(
        self, action: str = "", target: str = "", assistant: str = "default"
    ) -> ActionResult:
        return await self._call(
            (action or "").strip().lower() or "act",
            {"action": action, "target": (target or "").strip(), "assistant": assistant},
        )
