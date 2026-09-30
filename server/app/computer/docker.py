"""Docker-backed computer provider (opt-in, off by default).

Runs a caller-supplied Playwright image (COMPUTER_DOCKER_IMAGE) with a
hardened `docker run` profile applied to EVERY launch:

- --read-only (read-only rootfs) + --tmpfs /tmp (rw,noexec,nosuid,64m)
- --cap-drop=ALL + --security-opt=no-new-privileges (no escalation)
- --memory=512m --cpus=1.0 --pids-limit=256 (resource limits)
- --network=bridge (never --network=host)
- No --privileged, no docker.sock mount.
- Per-assistant workspace mounted at /workspace:
  WORKSPACE_ROOT/computers/<assistant>

Container protocol: `docker run ... <image> <op> <payload-json>` must print
a JSON object with an "ok" boolean on stdout. Anything else fails closed.

Fails closed: missing binary/daemon/image, non-zero exit, bad JSON, or any
exception all return ok=False — never raise, never fabricate.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .base import ActionResult, ComputerProvider


def _eff_image() -> str:
    img = (os.getenv("COMPUTER_DOCKER_IMAGE", "") or "").strip()
    if img:
        return img
    try:
        from ..config import settings

        return (getattr(settings, "computer_docker_image", "") or "").strip()
    except Exception:
        return ""


def _eff_workspace_root() -> str:
    root = (os.getenv("WORKSPACE_ROOT", "") or "").strip()
    if root:
        return root
    try:
        from ..config import settings

        return (getattr(settings, "workspace_root", "") or "").strip()
    except Exception:
        return ""


def sanitize_assistant(name: str) -> str:
    """Confine the assistant label to a safe single path segment."""
    clean = re.sub(r"[^A-Za-z0-9_.-]", "_", (name or "").strip())[:64]
    return clean or "default"


def assistant_workspace(name: str = "default") -> Path:
    """Per-assistant workspace: WORKSPACE_ROOT/computers/<assistant>."""
    root = _eff_workspace_root() or "/tmp/indy-workspaces"
    return Path(root) / "computers" / sanitize_assistant(name)


def _preflight_error_sync(image: str) -> Optional[str]:
    if shutil.which("docker") is None:
        return "Docker not available (no 'docker' binary); computer runtime fails closed."
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=15
        )
    except Exception as e:
        return f"Docker daemon check failed ({str(e)[:100]}); computer runtime fails closed."
    if proc.returncode != 0:
        return "Docker daemon unreachable; computer runtime fails closed."
    if not image:
        return "COMPUTER_DOCKER_IMAGE not configured; computer runtime fails closed."
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=15
        )
    except Exception as e:
        return f"Docker image check failed ({str(e)[:100]}); computer runtime fails closed."
    if proc.returncode != 0:
        return (
            f"Docker image '{image}' not found locally; computer runtime fails "
            "closed (pull or configure COMPUTER_DOCKER_IMAGE)."
        )
    return None


def _run_container_sync(image: str, workspace: Path, op: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"Cannot create computer workspace: {str(e)[:200]}"}
    cmd = [
        "docker", "run", "--rm",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=512m",
        "--cpus=1.0",
        "--pids-limit=256",
        "--network=bridge",
        "-v", f"{workspace}:/workspace:rw",
        "-w", "/workspace",
        image, op, json.dumps(payload),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=90, text=True)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Computer container timed out; fails closed."}
    except Exception as e:
        return {"ok": False, "error": f"Computer container launch failed: {str(e)[:200]}"}
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        hint = tail[-1][:200] if tail else f"exit {proc.returncode}"
        return {"ok": False, "error": f"Computer container failed ({hint}); fails closed."}
    try:
        data = json.loads((proc.stdout or "").strip())
    except Exception:
        return {"ok": False, "error": "Computer container returned non-JSON output; fails closed."}
    if not isinstance(data, dict) or "ok" not in data:
        return {"ok": False, "error": "Computer container returned unexpected output; fails closed."}
    return data


class DockerComputerProvider(ComputerProvider):
    name = "docker"

    async def _dispatch(self, op: str, payload: Dict[str, Any], assistant: str) -> ActionResult:
        image = _eff_image()
        err = await asyncio.to_thread(_preflight_error_sync, image)
        if err:
            return ActionResult(ok=False, provider=self.name, op=op, error=err)
        data = await asyncio.to_thread(
            _run_container_sync, image, assistant_workspace(assistant), op, payload
        )
        if data.get("ok"):
            result_data = data.get("data", data) if isinstance(data.get("data"), dict) else {
                k: v for k, v in data.items() if k != "ok"
            }
            return ActionResult(ok=True, provider=self.name, op=op, data=result_data)
        return ActionResult(
            ok=False, provider=self.name, op=op,
            error=str(data.get("error", "Computer action failed."))[:300],
        )

    async def navigate(self, target: str = "", assistant: str = "default") -> ActionResult:
        t = (target or "").strip()
        if not t:
            return ActionResult(
                ok=False, provider=self.name, op="navigate",
                error="No navigation target provided.",
            )
        return await self._dispatch("navigate", {"target": t}, assistant)

    async def snapshot(self, assistant: str = "default") -> ActionResult:
        return await self._dispatch("snapshot", {}, assistant)

    async def act(
        self, action: str = "", target: str = "", assistant: str = "default"
    ) -> ActionResult:
        return await self._dispatch(
            (action or "").strip().lower() or "act",
            {"action": action, "target": (target or "").strip()},
            assistant,
        )
