"""ComputerProvider ABC — opt-in computer runtime (P4).

All providers expose three async verbs returning ActionResult:

- navigate(target): point the runtime at a URL / target.
- snapshot(): capture current viewport / element state.
- act(action, target): click / type / other interactions.

Results are honest: ok=True carries data, ok=False carries error.
Providers MUST fail closed (never raise, never fabricate).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ActionResult:
    ok: bool
    provider: str = ""
    op: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "ok": self.ok,
            "provider": self.provider,
            "op": self.op,
            "data": dict(self.data),
        }
        if not self.ok and self.error:
            out["error"] = self.error
        return out


class ComputerProvider(ABC):
    """Abstract computer runtime. Default selection is the fake stub."""

    name: str = "base"

    @abstractmethod
    async def navigate(self, target: str = "", assistant: str = "default") -> ActionResult:
        """Point the runtime at a URL / target."""
        raise NotImplementedError

    @abstractmethod
    async def snapshot(self, assistant: str = "default") -> ActionResult:
        """Capture current viewport / element state."""
        raise NotImplementedError

    @abstractmethod
    async def act(
        self, action: str = "", target: str = "", assistant: str = "default"
    ) -> ActionResult:
        """Perform an interaction (click, type, ...)."""
        raise NotImplementedError
