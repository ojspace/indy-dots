import json
import os
import re
import httpx
from typing import AsyncGenerator, Dict, Any, Optional

from ..config import settings
from ..mechanical_triage import classify_incoming_intent
from ..policy import MUTATION_INTENTS, check_red_lines
from .verification_gate import verification_gate
from ..gates.approval_manager import approval_manager
from ..memory.vault import knowledge_vault
from ..connectors import github as github_connector
from ..connectors import mcp_client
from ..computer import COMPUTER_ACTION, detect_computer_request, governed_computer_action


def _parse_repo(prompt: str) -> str:
    """Extract owner/repo from prompt, else GITHUB_REPO env, else ''."""
    m = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", prompt)
    if m:
        candidate = m.group(1)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", candidate):
            return os.getenv("GITHUB_REPO", "")
        # Reject over-matches embedded in a longer slash-path (e.g. a/b/c).
        start, end = m.span(1)
        before = prompt[start - 1] if start > 0 else ""
        after = prompt[end] if end < len(prompt) else ""
        if before == "/" or after == "/":
            return os.getenv("GITHUB_REPO", "")
        return candidate
    return os.getenv("GITHUB_REPO", "")


def _parse_mcp_server(prompt: str) -> str:
    m = re.search(r"mcp[:\s@]+([a-z0-9_-]+)", prompt.strip().lower())
    if m:
        return m.group(1)
    allow = mcp_client.get_allowlist()
    if allow:
        return allow[0]
    return "default"


def _detect_connector_request(prompt: str) -> Optional[Dict[str, Any]]:
    """Narrow deterministic detection for governed connector actions.

    Returns None when the prompt needs no connector. Never matches email,
    publish, deploy, or other generic mutations — those stay on the generic gate.
    """
    low = prompt.strip().lower()
    if re.search(r"create\s+(a\s+|an\s+|new\s+|github\s+)?(issue|ticket)\b", low):
        repo = _parse_repo(prompt)
        return {
            "action_type": "create_issue",
            "kind": "github",
            "payload": {
                "repo": repo,
                "title": prompt.strip()[:120],
                "body": prompt.strip()[:500],
                "summary": prompt.strip()[:200],
            },
        }
    if re.search(r"\b(list|show|get|fetch)\b.{0,40}\b(issue|ticket)s?\b", low):
        repo = _parse_repo(prompt)
        return {
            "action_type": "list_issues",
            "kind": "github",
            "payload": {
                "repo": repo,
                "summary": prompt.strip()[:200],
            },
        }
    if "mcp" in low:
        write_verbs = ("create", "update", "delete", "write", "post", "publish", "send", "remove", "archive", "deploy")
        is_write = any(v in low for v in write_verbs)
        server = _parse_mcp_server(prompt)
        tool = "write_item" if is_write else "list_items"
        return {
            "action_type": mcp_client.MCP_WRITE_ACTION if is_write else mcp_client.MCP_READ_ACTION,
            "kind": "mcp",
            "payload": {
                "server": server,
                "tool": tool,
                "summary": prompt.strip()[:200],
            },
        }
    return None
from ..tools.web_search import governed_web_search

class ChiefOfStaff:
    def __init__(self):
        self.primary_model = settings.primary_model
        self.worker_model = settings.worker_model

    def route_intent(self, prompt: str) -> Dict[str, str]:
        """
        Zero-token intent routing. Single source of truth is
        mechanical_triage.classify_incoming_intent — the standalone
        zero-token pipeline and the gateway can never drift apart.
        """
        c = classify_incoming_intent(prompt)
        return {
            "role": c["route"],
            "model_tier": c["tier"],
            "profile": c["action"],
        }

    async def execute_task(self, prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        # 1. Routing step (zero-token mechanical classification)
        route = self.route_intent(prompt)
        yield {
            "type": "route_decision",
            "role": route["role"],
            "model_tier": route["model_tier"],
            "detail": f"Routed to {route['role']} using {route['model_tier']} model tier."
        }

        # 2. Memory context recall
        recalled = await knowledge_vault.query_notes(prompt[:50], limit=2)
        if recalled:
            yield {
                "type": "memory_recall",
                "count": len(recalled),
                "items": [r["title"] for r in recalled]
            }

        # 2.4 Governed web search (P2: /search) — read-only SAFE action.
        # Runs AFTER recall, BEFORE the mutation/red-line gate. Every run
        # submits action_type "search_web" (SAFE_ACTIONS) so the ledger
        # records AUTO_APPROVED. Results feed the model call as context.
        search_context = ""
        try:
            full_intent = classify_incoming_intent(prompt)
        except Exception:
            full_intent = {}
        if isinstance(full_intent, dict) and full_intent.get("action") == "web_search":
            search_query = str(full_intent.get("query", "") or "").strip()
            yield {"type": "search_dispatch", "query": search_query[:200]}
            try:
                gate, search_result = await governed_web_search(
                    search_query, caller=route.get("role", "researcher")
                )
            except Exception as e:
                gate, search_result = {"approved": False, "status": "ERROR", "gate_id": ""}, {
                    "ok": False, "error": str(e)[:300] or "search failed", "results": [],
                }
            gate_id = gate.get("gate_id", "")
            if search_result.get("ok"):
                results = search_result.get("results", []) or []
                yield {
                    "type": "search_results",
                    "count": len(results),
                    "results": results,
                    "gate_id": gate_id,
                }
                if results:
                    lines = [
                        f"- {r.get('title', '')} — {r.get('url', '')}\n  {r.get('snippet', '')[:300]}"
                        for r in results
                    ]
                    search_context = (
                        f"\n\nWeb search results for \"{search_query[:200]}\":\n"
                        + "\n".join(lines)
                        + "\nCite URLs when you use them. Do not fabricate beyond these results.\n"
                    )
                else:
                    search_context = (
                        f"\n\nWeb search for \"{search_query[:200]}\" returned no results. "
                        "Say so honestly; do not fabricate.\n"
                    )
            else:
                yield {
                    "type": "search_results",
                    "count": 0,
                    "results": [],
                    "error": str(search_result.get("error", "search failed"))[:300],
                    "gate_id": gate_id,
                }
                search_context = (
                    f"\n\nWeb search failed: {str(search_result.get('error', 'search failed'))[:200]} "
                    "(do not fabricate results; report the failure honestly.)\n"
                )

        # 2.5a Governed connectors (GitHub / MCP) — specific action types so
        # reads auto-approve (SAFE + ledger) and writes pause (YELLOW + dry_run).
        # Red lines are enforced inside submit_action_for_governance (single
        # source of truth in policy.py). Never execute on PENDING.
        connector_req = _detect_connector_request(prompt)
        if connector_req:
            action_type = connector_req["action_type"]
            payload = connector_req["payload"]
            gate = approval_manager.submit_action_for_governance(
                action_type=action_type,
                payload=payload,
                caller=route["role"],
            )
            if not gate.get("approved"):
                status = gate.get("status")
                if status == "PENDING_APPROVAL":
                    yield {
                        "type": "approval_required",
                        "gate_id": gate["gate_id"],
                        "action": action_type,
                        "message": gate.get("message", "Action paused. Operator review required."),
                    }
                else:  # REJECTED_RED_LINE or other hard stop
                    yield {
                        "type": "action_rejected",
                        "gate_id": gate.get("gate_id"),
                        "action": action_type,
                        "message": gate.get("detail", "Action violates Red Lines."),
                    }
                return
            # Approved (AUTO_APPROVED read or operator-APPROVED write): execute now.
            try:
                if action_type == "list_issues":
                    result = await github_connector.list_issues(repo=payload.get("repo", ""))
                elif action_type == "create_issue":
                    result = await github_connector.create_issue(
                        repo=payload.get("repo", ""),
                        title=payload.get("title", ""),
                        body=payload.get("body", ""),
                    )
                elif action_type in (mcp_client.MCP_READ_ACTION, mcp_client.MCP_WRITE_ACTION):
                    result = await mcp_client.dispatch(
                        server=payload.get("server", ""),
                        tool=payload.get("tool", ""),
                        params={"summary": payload.get("summary", "")},
                    )
                else:
                    result = {"ok": False, "error": f"Unknown connector action '{action_type}'."}
            except Exception as e:
                result = {"ok": False, "error": f"Connector failed: {str(e)[:300]}"}
            if result.get("ok"):
                yield {
                    "type": "connector_result",
                    "action": action_type,
                    "gate_id": gate.get("gate_id"),
                    "result": result,
                }
            else:
                # Fail-closed honest error — never fabricate connector output.
                yield {
                    "type": "model_error",
                    "worker": route["role"],
                    "model": action_type,
                    "error": result.get("error", "Connector failed.")[:300],
                }
            return

        # 2.5b Opt-in computer runtime (P4) — narrow "computer <verb>" intents.
        # action_type "computer_navigate" is NEVER in SAFE_ACTIONS, so the
        # first pass always pauses (PENDING_APPROVAL + dry_run) or hard-stops
        # (REJECTED_RED_LINE via policy.py). Never execute on PENDING.
        # Existing 2.4 search / 2.5a connectors above are untouched.
        computer_req = detect_computer_request(prompt)
        if computer_req:
            gate, computer_result = await governed_computer_action(
                op=computer_req["op"],
                target=computer_req.get("target", ""),
                caller=route["role"],
            )
            if computer_result is None:
                status = gate.get("status")
                if status == "PENDING_APPROVAL":
                    yield {
                        "type": "approval_required",
                        "gate_id": gate["gate_id"],
                        "action": COMPUTER_ACTION,
                        "message": gate.get("message", "Action paused. Operator review required."),
                    }
                else:  # REJECTED_RED_LINE or other hard stop
                    yield {
                        "type": "action_rejected",
                        "gate_id": gate.get("gate_id"),
                        "action": COMPUTER_ACTION,
                        "message": gate.get("detail", "Action violates Red Lines."),
                    }
                return
            # Approved: execution already happened inside the governed path.
            if computer_result.ok:
                yield {
                    "type": "computer_result",
                    "action": COMPUTER_ACTION,
                    "gate_id": gate.get("gate_id"),
                    "result": computer_result.to_dict(),
                }
            else:
                # Fail-closed honest error — never fabricate computer output.
                yield {
                    "type": "model_error",
                    "worker": route["role"],
                    "model": COMPUTER_ACTION,
                    "error": (computer_result.error or "Computer action failed.")[:300],
                }
            return

        # 2.5 Governance gate — runs on EVERY remaining task:
        #   - Red-line content (.env, id_rsa, rm -rf, ...) hard-rejects
        #     regardless of intent (reading secrets is as bad as deleting).
        #   - Mutating intents pause at the Yellow Gate for operator sign-off.
        p_lower = prompt.strip().lower()
        is_mutation = any(pat in p_lower for pat in MUTATION_INTENTS)
        red_hit = check_red_lines({"summary": prompt})
        if red_hit or is_mutation:
            gate = approval_manager.submit_action_for_governance(
                action_type="external_mutation" if is_mutation else "sensitive_read",
                payload={"summary": prompt[:2000], "route": route},
                caller=route["role"],
            )
            if not gate.get("approved"):
                status = gate.get("status")
                if status == "PENDING_APPROVAL":
                    yield {
                        "type": "approval_required",
                        "gate_id": gate["gate_id"],
                        "message": gate.get("message", "Action paused. Operator review required."),
                    }
                else:  # REJECTED_RED_LINE or other hard stop
                    yield {
                        "type": "action_rejected",
                        "gate_id": gate.get("gate_id"),
                        "message": gate.get("detail", "Action violates Red Lines."),
                    }
                return

        # 3. Model call (CoS or delegated worker)
        model_name = settings.primary_model if route["model_tier"] == "primary" else settings.worker_model
        # Credential resolution order: env > encrypted store > settings-baked > "".
        # (get_provider_key checks live env first, so it covers the settings value;
        # the settings fallback matters for tests that monkeypatch settings.)
        try:
            from ..security.credential_store import get_provider_key as _get_provider_key
            _stored_key = _get_provider_key("primary" if route["model_tier"] == "primary" else "worker")
        except Exception:
            _stored_key = ""
        _settings_key = settings.primary_api_key if route["model_tier"] == "primary" else settings.worker_api_key
        api_key = _stored_key or _settings_key
        base_url = settings.primary_base_url if route["model_tier"] == "primary" else settings.worker_base_url

        system_instruction = (
            f"You are {route['role']} in the Indy-Dots autonomous system.\n"
            f"Role profile: {route['profile']}.\n"
            f"Follow extreme token discipline: concise, factual, no pleasantries.\n"
            f"If an external mutation is needed, format it clearly for governance review."
        )

        output_text = ""
        model_input = prompt + search_context if search_context else prompt
        if api_key:
            yield {"type": "worker_dispatch", "worker": route["role"], "model": model_name}
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": model_input}
                            ],
                            "stream": True,
                            "temperature": 0.3
                        }
                    ) as resp:
                        resp.raise_for_status()
                        async for chunk in resp.aiter_lines():
                            if chunk.startswith("data: ") and not chunk.endswith("[DONE]"):
                                try:
                                    data = json.loads(chunk[6:])
                                    delta = data["choices"][0]["delta"].get("content", "")
                                    if delta:
                                        output_text += delta
                                        yield {"type": "content_chunk", "chunk": delta}
                                except Exception:
                                    continue
            except Exception as e:
                # Honest failure: report the error, do NOT fabricate a reply.
                output_text = ""
                yield {
                    "type": "model_error",
                    "worker": route["role"],
                    "model": model_name,
                    "error": str(e)[:300],
                }

        # 4. Verification Gate pass (fail-closed, 1 corrective pass max)
        yield {"type": "verification_gate_started", "status": "checking_done_when_criteria"}
        passed, v_reason, output_text = await verification_gate.verify_output(
            prompt, output_text,
            regenerate=lambda: self._regenerate(model_input, system_instruction, route),
        )
        yield {
            "type": "verification_gate_result",
            "passed": passed,
            "reason": v_reason
        }

        # 5. Compounding Knowledge Vault commit — only for verified,
        # substantive research outputs (not every chat blurb).
        if passed and route["role"] == "researcher" and len(output_text) > 400:
            title_slug = f"research_{hash(prompt) % 10000}"
            await knowledge_vault.save_note(title_slug, f"handoffs/{route['role']}", output_text)
            yield {"type": "vault_compounded", "note": title_slug}

    async def _regenerate(self, prompt: str, system_instruction: str, route: Dict[str, str]) -> str:
        """One corrective regeneration pass used by the verification gate."""
        model_name = settings.primary_model if route["model_tier"] == "primary" else settings.worker_model
        try:
            from ..security.credential_store import get_provider_key as _get_provider_key
            _stored_key = _get_provider_key("primary" if route["model_tier"] == "primary" else "worker")
        except Exception:
            _stored_key = ""
        _settings_key = settings.primary_api_key if route["model_tier"] == "primary" else settings.worker_api_key
        api_key = _stored_key or _settings_key
        base_url = settings.primary_base_url if route["model_tier"] == "primary" else settings.worker_base_url
        if not api_key:
            return ""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"].get("content", "") or ""

chief_of_staff = ChiefOfStaff()
