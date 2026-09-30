"""Deterministic fake computer provider for dev/tests.

Inert by design: no browser, no network, no side effects. Outputs are a
pure function of the inputs so tests can assert exact behavior.
"""

import hashlib

from .base import ActionResult, ComputerProvider


class FakeComputerProvider(ComputerProvider):
    name = "fake"

    async def navigate(self, target: str = "", assistant: str = "default") -> ActionResult:
        t = (target or "").strip()
        if not t:
            return ActionResult(
                ok=False, provider=self.name, op="navigate",
                error="No navigation target provided.",
            )
        digest = hashlib.sha256(t.encode()).hexdigest()[:12]
        return ActionResult(
            ok=True,
            provider=self.name,
            op="navigate",
            data={
                "url": t,
                "title": f"Fake page for {t}",
                "snapshot_id": f"fake-{digest}",
            },
        )

    async def snapshot(self, assistant: str = "default") -> ActionResult:
        return ActionResult(
            ok=True,
            provider=self.name,
            op="snapshot",
            data={
                "viewport": {"width": 1280, "height": 800},
                "elements": [
                    {"role": "heading", "name": "Fake page"},
                    {"role": "button", "name": "Fake button"},
                ],
                "snapshot_id": "fake-snapshot-001",
            },
        )

    async def act(
        self, action: str = "", target: str = "", assistant: str = "default"
    ) -> ActionResult:
        a = (action or "").strip().lower() or "act"
        return ActionResult(
            ok=True,
            provider=self.name,
            op=a,
            data={
                "action": a,
                "target": (target or "").strip(),
                "snapshot_id": "fake-act-001",
            },
        )
