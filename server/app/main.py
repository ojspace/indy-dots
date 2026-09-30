from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import asyncio
import logging
import os
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .auth import enforce_production_token_safety, require_auth
from .profiles import load_profiles
from .orchestrator.chief_of_staff import chief_of_staff
from .gates.approval_manager import approval_manager
from .memory.vault import knowledge_vault
from .tools.web_search import governed_web_search
from .computer import COMPUTER_OPS, get_provider, governed_computer_action
from .memory import conversations as conversation_store

enforce_production_token_safety()

from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        await conversation_store.init_db()
    except Exception:
        pass
    try:
        await knowledge_vault.init_db()
    except Exception:
        pass
    # P5 routine scheduler: in-process only, default OFF (ROUTINES_ENABLED=1 to start).
    routine_task = None
    try:
        from .routines.scheduler import routines_enabled, start_routine_loop
        if routines_enabled():
            routine_task = start_routine_loop()
    except Exception:
        routine_task = None
    try:
        yield
    finally:
        if routine_task is not None:
            routine_task.cancel()
            try:
                await routine_task
            except (asyncio.CancelledError, Exception):
                pass

app = FastAPI(
    title="Indy-Dots API Gateway",
    description="Autonomous, cost-disciplined Dots competitor running on Hetzner Hermes architecture.",
    version="1.1.0",
    lifespan=_lifespan,
)

_logger = logging.getLogger(__name__)

def _safe_cors_origins() -> list:
    """Fail closed: never allow wildcard origin with credentials."""
    origins = list(settings.allowed_origins or [])
    if "*" in origins:
        _logger.error(
            "Refusing wildcard CORS origin with allow_credentials=True; "
            "falling back to localhost-only origins."
        )
        return ["http://127.0.0.1:3000"]
    return origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_safe_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

class ChatRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None

def _session_or_default(session_id: Optional[str]) -> str:
    sid = (session_id or "").strip()
    return sid[:128] if sid else "default"

def _final_text_from_events(events: List[Dict[str, Any]]) -> str:
    """Best-effort human-readable transcript of orchestrator events."""
    chunks: List[str] = []
    for ev in events:
        t = ev.get("type")
        if t == "content_chunk":
            chunks.append(str(ev.get("chunk", "")))
        elif t == "approval_required":
            chunks.append(
                f"Approval required (gate {ev.get('gate_id')}). "
                f"{ev.get('message', '')}"
            )
        elif t == "action_rejected":
            chunks.append(
                f"Rejected by Red Lines (gate {ev.get('gate_id')}). "
                f"{ev.get('message', '')}"
            )
        elif t == "model_error":
            chunks.append(f"Model call failed ({ev.get('model')}). {ev.get('error', '')}")
        elif t == "computer_result":
            res = ev.get("result", {}) or {}
            if res.get("ok"):
                chunks.append(f"Computer action done ({ev.get('action')}). {res.get('data', '')}")
            else:
                chunks.append(f"Computer action failed. {res.get('error', '')}")
    text = "".join(chunks).strip()
    if text:
        return text
    # Fallback: surface the last meaningful event so history is never empty.
    for ev in reversed(events):
        if ev.get("type") in ("verification_gate_result", "route_decision"):
            return json.dumps(ev)
    return json.dumps(events[-1]) if events else ""

async def _persist_turn(session_id: str, prompt: str, final_text: str) -> None:
    """Best-effort persistence: DB errors must never break a chat response."""
    try:
        await conversation_store.save_message(session_id, "user", prompt)
        await conversation_store.save_message(session_id, "assistant", final_text)
    except Exception:
        pass

class ApprovalResolutionRequest(BaseModel):
    gate_id: str
    approved: bool
    operator_note: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 5

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "indy-dots-gateway",
        "environment": settings.environment,
        "primary_model": settings.primary_model,
        "worker_model": settings.worker_model
    }

@app.post("/api/chat")
async def chat_interaction(req: ChatRequest, _auth: None = Depends(require_auth)):
    """
    Non-streaming chat endpoint returning aggregated orchestrator events.
    """
    events = []
    async for event in chief_of_staff.execute_task(req.prompt):
        events.append(event)
    sid = _session_or_default(req.session_id)
    await _persist_turn(sid, req.prompt, _final_text_from_events(events))
    return {"status": "completed", "events": events, "session_id": sid}

class StreamChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

@app.post("/api/chat/stream")
async def chat_stream(req: StreamChatRequest, _auth: None = Depends(require_auth)):
    """
    Real-time SSE stream of agent thoughts, tool dispatches, and verification.
    POST (not GET) so prompts never leak into proxy/access logs.
    """
    sid = _session_or_default(req.session_id)
    prompt = req.prompt
    async def event_generator():
        collected: List[Dict[str, Any]] = []
        async for event in chief_of_staff.execute_task(prompt):
            collected.append(event)
            yield {"event": "agent_event", "data": json.dumps(event)}
        await _persist_turn(sid, prompt, _final_text_from_events(collected))
    return EventSourceResponse(event_generator())

@app.get("/api/conversations")
async def get_conversations(
    session_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_auth),
):
    sid = _session_or_default(session_id)
    try:
        messages = await conversation_store.list_history(sid, limit=limit)
    except Exception:
        messages = []
    return {"session_id": sid, "messages": messages}

@app.delete("/api/conversations")
async def delete_conversations(
    session_id: str = "",
    _auth: None = Depends(require_auth),
):
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id query param is required")
    try:
        deleted = await conversation_store.clear_history(sid[:128])
    except Exception:
        deleted = 0
    return {"session_id": sid[:128], "deleted": deleted}

@app.get("/api/approvals")
async def list_approvals(_auth: None = Depends(require_auth)):
    return {"pending": approval_manager.get_pending_approvals()}

@app.post("/api/approvals/resolve")
async def resolve_approval(req: ApprovalResolutionRequest, _auth: None = Depends(require_auth)):
    res = approval_manager.resolve_approval(req.gate_id, req.approved, req.operator_note)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res

@app.get("/api/vault")
async def search_vault(query: str = "", limit: int = 10, _auth: None = Depends(require_auth)):
    notes = await knowledge_vault.query_notes(query[:500], limit=limit)
    return {"notes": notes}

@app.post("/api/search")
async def web_search_endpoint(req: SearchRequest, _auth: None = Depends(require_auth)):
    """
    Governed read-only web search (P2: /search). Reuses governed_web_search
    so every run submits action_type "search_web" (SAFE_ACTIONS) and writes
    a ledger entry. Fails closed — never fabricates results.
    """
    limit = max(1, min(int(req.limit or 5), 10))
    gate, result = await governed_web_search(req.query, caller="api", num_results=limit)
    return {
        "gate_id": gate.get("gate_id", ""),
        "status": gate.get("status", ""),
        "ok": result.get("ok", False),
        "profile": result.get("profile", "unknown"),
        "results": result.get("results", []),
        **({"error": result["error"]} if "error" in result else {}),
    }

@app.get("/api/profiles")
async def list_profiles(_auth: None = Depends(require_auth)):
    """Fleet loaded from profiles/*.yaml (falls back to built-in fleet)."""
    return {"profiles": load_profiles()}

class ComputerActRequest(BaseModel):
    op: str = "navigate"
    target: str = ""
    assistant: str = "default"

@app.post("/api/computer/act")
async def computer_act(req: ComputerActRequest, _auth: None = Depends(require_auth)):
    """
    Opt-in computer runtime (P4). Reuses governed_computer_action — the same
    governed path as orchestrator stage 2.5b: action_type
    "computer_navigate" (never SAFE) pauses as PENDING_APPROVAL with a
    dry-run receipt, or hard-stops on red lines. Never executes on PENDING.
    """
    op = (req.op or "").strip().lower()
    if op not in COMPUTER_OPS:
        raise HTTPException(
            status_code=400,
            detail=f"op must be one of {'|'.join(COMPUTER_OPS)}",
        )
    assistant = (req.assistant or "default").strip()[:64] or "default"
    gate, result = await governed_computer_action(
        op=op, target=req.target or "", caller="api", assistant=assistant
    )
    if result is None:
        # Paused or rejected: no provider execution happened.
        return {
            "gate_id": gate.get("gate_id", ""),
            "status": gate.get("status", ""),
            "approved": False,
            "message": gate.get("message") or gate.get("detail", ""),
        }
    body = {
        "gate_id": gate.get("gate_id", ""),
        "status": gate.get("status", ""),
        "approved": True,
        "ok": result.ok,
        "result": result.to_dict(),
    }
    if not result.ok:
        body["error"] = result.error
    return body

@app.get("/api/computer/status")
async def computer_status(_auth: None = Depends(require_auth)):
    """
    Runtime config snapshot. Reports capability as booleans/names only —
    never secrets (no tokens, no remote credentials).
    """
    provider = get_provider()
    name = getattr(provider, "name", "unknown")
    return {
        "provider": name,
        "opt_in": name != "fake",
        "docker_image": settings.computer_docker_image,
        "workspace_root": settings.workspace_root,
        "sandbox_hardened": False,
        "note": (
            "Opt-in runtime, off by default (fake = inert stub). Gateway and "
            "approver share one process: not a hardened sandbox for hostile web."
        ),
    }

@app.get("/api/metrics")
async def get_metrics(_auth: None = Depends(require_auth)):
    """
    Real numbers computed from the gate ledger and vault index.
    No fabricated data: when the system has done nothing, this says so.
    """
    ledger = approval_manager.get_ledger_entries(limit=1000)
    red_lines = sum(1 for e in ledger if e.get("status") == "REJECTED_RED_LINE")
    approved = sum(1 for e in ledger if e.get("status") == "APPROVED")
    denied = sum(1 for e in ledger if e.get("status") == "DENIED")
    pending = sum(1 for e in ledger if e.get("status") == "PENDING_APPROVAL")
    auto = sum(1 for e in ledger if e.get("status") == "AUTO_APPROVED")

    total_actions = len(ledger)
    # Zero-token runs: read-only actions auto-approved without any model call.
    zero_token_runs = auto

    try:
        vault_notes = len(await knowledge_vault.query_notes("", limit=1000))
    except Exception:
        vault_notes = 0

    return {
        "token_economy": {
            "zero_token_mechanical_runs": zero_token_runs,
            "model_dispatched_tasks": max(total_actions - auto - red_lines, 0),
            "verification_failures_prevented": red_lines,
            "note": (
                "Counted from the live gate ledger. Routing is zero-token "
                "(mechanical classifier); cost savings depend on your model mix."
            ),
        },
        "governance": {
            "total_gate_actions": total_actions,
            "red_lines_rejected": red_lines,
            "operator_approved": approved,
            "operator_denied": denied,
            "pending_approval": pending,
            "auto_approved_safe": auto,
        },
        "memory": {
            "vault_notes": vault_notes,
            "vault_dir": settings.vault_dir,
        },
        "system": {
            "vps_provider": "Hetzner Cloud",
            "host_os": "Linux / Docker",
            "active_services": ["gateway", "caddy", "web", "mcp-suite"],
            "environment": settings.environment,
        }
    }


# --- P5: encrypted provider keys -------------------------------------------

class ProviderKeyRequest(BaseModel):
    name: str
    key: str = ""


@app.get("/api/settings/keys")
async def list_provider_keys(_auth: None = Depends(require_auth)):
    """Which provider keys are configured. Names + bools only — never secrets."""
    from .security.credential_store import list_provider_status
    return {"keys": list_provider_status()}


@app.post("/api/settings/keys")
async def save_provider_key_endpoint(
    req: ProviderKeyRequest, _auth: None = Depends(require_auth)
):
    """Store a provider key encrypted at rest. Blank preserves the stored value."""
    from .security.credential_store import save_provider_key
    try:
        result = save_provider_key(req.name, req.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **result}


# --- P5: routine scheduler ---------------------------------------------------

class RoutineCreateRequest(BaseModel):
    name: str
    prompt: str
    cron: str


class RoutinePatchRequest(BaseModel):
    enabled: bool


def _routine_store():
    from .routines.store import RoutineStore
    return RoutineStore()


@app.get("/api/routines")
async def list_routines(_auth: None = Depends(require_auth)):
    return {"routines": _routine_store().list()}


@app.post("/api/routines")
async def create_routine(req: RoutineCreateRequest, _auth: None = Depends(require_auth)):
    try:
        routine = _routine_store().create(req.name, req.prompt, req.cron)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"routine": routine}


@app.patch("/api/routines/{routine_id}")
async def patch_routine(
    routine_id: str, req: RoutinePatchRequest, _auth: None = Depends(require_auth)
):
    routine = _routine_store().set_enabled(routine_id, req.enabled)
    if routine is None:
        raise HTTPException(status_code=404, detail=f"Routine {routine_id} not found.")
    return {"routine": routine}


@app.delete("/api/routines/{routine_id}")
async def delete_routine(routine_id: str, _auth: None = Depends(require_auth)):
    if not _routine_store().delete(routine_id):
        raise HTTPException(status_code=404, detail=f"Routine {routine_id} not found.")
    return {"ok": True, "deleted": routine_id}
