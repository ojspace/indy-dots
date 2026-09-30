from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import asyncio
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .auth import enforce_production_token_safety, require_auth
from .profiles import load_profiles
from .orchestrator.chief_of_staff import chief_of_staff
from .gates.approval_manager import approval_manager
from .memory.vault import knowledge_vault

enforce_production_token_safety()

app = FastAPI(
    title="Indy-Dots API Gateway",
    description="Autonomous, cost-disciplined Dots competitor running on Hetzner Hermes architecture.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

class ChatRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None

class ApprovalResolutionRequest(BaseModel):
    gate_id: str
    approved: bool
    operator_note: Optional[str] = None

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
    return {"status": "completed", "events": events}

class StreamChatRequest(BaseModel):
    prompt: str

@app.post("/api/chat/stream")
async def chat_stream(req: StreamChatRequest, _auth: None = Depends(require_auth)):
    """
    Real-time SSE stream of agent thoughts, tool dispatches, and verification.
    POST (not GET) so prompts never leak into proxy/access logs.
    """
    async def event_generator():
        async for event in chief_of_staff.execute_task(req.prompt):
            yield {"event": "agent_event", "data": json.dumps(event)}
    return EventSourceResponse(event_generator())

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
    notes = await knowledge_vault.query_notes(query, limit=limit)
    return {"notes": notes}

@app.get("/api/profiles")
async def list_profiles(_auth: None = Depends(require_auth)):
    """Fleet loaded from profiles/*.yaml (falls back to built-in fleet)."""
    return {"profiles": load_profiles()}

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
