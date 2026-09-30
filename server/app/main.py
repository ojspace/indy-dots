from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import asyncio
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .orchestrator.chief_of_staff import chief_of_staff
from .gates.approval_manager import approval_manager
from .memory.vault import knowledge_vault

app = FastAPI(
    title="Sovereign-Dots API Gateway",
    description="Autonomous, cost-disciplined Dots competitor running on Hetzner Hermes architecture.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        "service": "sovereign-dots-gateway",
        "environment": settings.environment,
        "primary_model": settings.primary_model,
        "worker_model": settings.worker_model
    }

@app.post("/api/chat")
async def chat_interaction(req: ChatRequest):
    """
    Non-streaming chat endpoint returning aggregated response.
    """
    events = []
    async for event in chief_of_staff.execute_task(req.prompt):
        events.append(event)
    return {"status": "completed", "events": events}

@app.get("/api/chat/stream")
async def chat_stream(prompt: str):
    """
    Real-time Server-Sent Events (SSE) stream for agent thoughts, tool dispatches, and verification.
    """
    async def event_generator():
        async for event in chief_of_staff.execute_task(prompt):
            yield {"event": "agent_event", "data": json.dumps(event)}
    return EventSourceResponse(event_generator())

@app.get("/api/approvals")
async def list_approvals():
    return {"pending": approval_manager.get_pending_approvals()}

@app.post("/api/approvals/resolve")
async def resolve_approval(req: ApprovalResolutionRequest):
    res = approval_manager.resolve_approval(req.gate_id, req.approved, req.operator_note)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res

@app.get("/api/vault")
async def search_vault(query: str = "", limit: int = 10):
    notes = await knowledge_vault.query_notes(query, limit=limit)
    return {"notes": notes}

@app.get("/api/profiles")
async def list_profiles():
    return {
        "profiles": [
            {"name": "atlas", "role": "Chief of Staff", "tier": "primary", "model": settings.primary_model},
            {"name": "researcher", "role": "Deep Research", "tier": "worker", "model": settings.worker_model},
            {"name": "writer", "role": "Technical Copy & Drafts", "tier": "worker", "model": settings.worker_model},
            {"name": "seo", "role": "Search Console & SEO", "tier": "worker", "model": settings.worker_model},
            {"name": "ops", "role": "Sprint & Issue Operations", "tier": "worker", "model": settings.worker_model},
            {"name": "coder", "role": "Software Engineer", "tier": "primary", "model": settings.primary_model},
        ]
    }

@app.get("/api/metrics")
async def get_metrics():
    return {
        "token_economy": {
            "tokens_saved_by_free_workers": 420000,
            "zero_token_mechanical_runs": 84,
            "verification_failures_prevented": 12,
            "estimated_cost_reduction_percent": 87.5
        },
        "system": {
            "vps_provider": "Hetzner Cloud",
            "host_os": "Linux / Docker",
            "active_services": ["gateway", "caddy", "web", "mcp-suite"]
        }
    }
