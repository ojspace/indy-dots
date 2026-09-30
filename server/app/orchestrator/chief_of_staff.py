import json
import httpx
from typing import AsyncGenerator, Dict, Any

from ..config import settings
from ..mechanical_triage import classify_incoming_intent
from ..policy import MUTATION_INTENTS, check_red_lines
from .verification_gate import verification_gate
from ..gates.approval_manager import approval_manager
from ..memory.vault import knowledge_vault

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

        # 2.5 Governance gate — runs on EVERY task:
        #   - Red-line content (.env, id_rsa, rm -rf, ...) hard-rejects
        #     regardless of intent (reading secrets is as bad as deleting).
        #   - Mutating intents pause at the Yellow Gate for operator sign-off.
        p_lower = prompt.strip().lower()
        is_mutation = any(pat in p_lower for pat in MUTATION_INTENTS)
        red_hit = check_red_lines({"summary": prompt[:200]})
        if red_hit or is_mutation:
            gate = approval_manager.submit_action_for_governance(
                action_type="external_mutation" if is_mutation else "sensitive_read",
                payload={"summary": prompt[:200], "route": route},
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
        api_key = settings.primary_api_key if route["model_tier"] == "primary" else settings.worker_api_key
        base_url = settings.primary_base_url if route["model_tier"] == "primary" else settings.worker_base_url

        system_instruction = (
            f"You are {route['role']} in the Indy-Dots autonomous system.\n"
            f"Role profile: {route['profile']}.\n"
            f"Follow extreme token discipline: concise, factual, no pleasantries.\n"
            f"If an external mutation is needed, format it clearly for governance review."
        )

        output_text = ""
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
                                {"role": "user", "content": prompt}
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
            regenerate=lambda: self._regenerate(prompt, system_instruction, route),
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
        api_key = settings.primary_api_key if route["model_tier"] == "primary" else settings.worker_api_key
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
