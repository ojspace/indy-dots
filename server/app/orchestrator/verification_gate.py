import re
import httpx
from typing import Awaitable, Callable, Dict, Optional, Tuple

from ..config import settings

# Evidence markers: URLs, file paths, code fences, numbers with units.
_EVIDENCE_RE = re.compile(
    r"(https?://[^\s)]+|`[^`]+`|/[\w./-]{4,}|\b\d+(?:\.\d+)?\s?(?:ms|s|kb|mb|gb|%|usd|\$)\b)",
    re.IGNORECASE,
)

class VerificationGate:
    """
    Verification Gate Protocol (fail-closed):
    1. Restate original ASK and DONE-WHEN criteria.
    2. Check output against criteria with evidence (links, files, data),
       not plausible prose.
    3. PASS -> approve and feed knowledge to vault.
    4. FAIL -> EXACTLY ONE corrective pass (via `regenerate`). If it fails
       again, halt and report the gap. NEVER fail open on network errors.
    """

    def __init__(self):
        self.max_corrective_passes = settings.verification_max_passes

    async def verify_output(
        self,
        task_prompt: str,
        candidate_output: str,
        regenerate: Optional[Callable[[], Awaitable[str]]] = None,
    ) -> Tuple[bool, str, str]:
        """
        Returns (passed, reason, final_output). `final_output` is the
        (possibly regenerated) candidate that passed — or the original on
        failure so callers can show what was rejected.
        """
        # Structural baseline: non-trivial output with concrete evidence.
        ok, reason = self._structural_check(candidate_output)
        if not ok:
            corrected = await self._one_corrective_pass(
                f"Output rejected: {reason}", regenerate
            )
            if corrected is not None:
                ok2, reason2 = self._structural_check(corrected)
                if ok2:
                    return True, f"Passed after 1 corrective pass ({reason})", corrected
            return False, reason, candidate_output

        # Model-based strict verification when a primary key is configured.
        if settings.primary_api_key:
            verdict = await self._model_verify(task_prompt, candidate_output)
            if verdict is not None:
                passed, reason = verdict
                if passed:
                    return True, reason, candidate_output
                corrected = await self._one_corrective_pass(reason, regenerate)
                if corrected is not None:
                    verdict2 = await self._model_verify(task_prompt, corrected)
                    if verdict2 is not None and verdict2[0]:
                        return True, f"Passed after 1 corrective pass: {verdict2[1]}", corrected
                return False, reason, candidate_output
            # verdict is None => verifier itself was unreachable: FAIL CLOSED.
            return False, (
                "Verification gate unreachable (model API error). Failing closed — "
                "output marked unverified and NOT approved."
            ), candidate_output

        # No model configured: structural baseline is the gate.
        return True, reason, candidate_output

    def _structural_check(self, output: str) -> Tuple[bool, str]:
        text = output.strip()
        if len(text) < 10:
            return False, "Output is too short or empty."
        if not _EVIDENCE_RE.search(text):
            return False, "No concrete evidence found (links, files, code, or data)."
        return True, "Passed structural evidence baseline."

    async def _one_corrective_pass(
        self, failure_reason: str, regenerate: Optional[Callable[[], Awaitable[str]]]
    ) -> Optional[str]:
        """The 1-pass rule: exactly one corrective attempt, or None."""
        if regenerate is None or self.max_corrective_passes < 1:
            return None
        try:
            return await regenerate()
        except Exception:
            return None

    async def _model_verify(
        self, task_prompt: str, candidate_output: str
    ) -> Optional[Tuple[bool, str]]:
        """Returns (passed, reason), or None when the verifier is unreachable."""
        verification_prompt = (
            f"You are the Indy-Dots Verification Gate.\n"
            f"TASK ASK: {task_prompt}\n"
            f"CANDIDATE OUTPUT TO VERIFY:\n{candidate_output}\n\n"
            f"Check with fresh eyes: Does this candidate output actually fulfill the ask "
            f"with concrete evidence (data, links, code, files) rather than generic fluff "
            f"or excuses?\n"
            f"Reply ONLY in format:\n"
            f"STATUS: PASS or FAIL\n"
            f"REASON: <concise reason>"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.primary_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.primary_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.primary_model,
                        "messages": [{"role": "user", "content": verification_prompt}],
                        "temperature": 0.0,
                        "max_tokens": 150,
                    },
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    passed = "STATUS: PASS" in content
                    return passed, content.strip()[:300]
                return None  # Non-200: verifier unreachable -> fail closed
        except Exception:
            return None  # Network error -> fail closed

verification_gate = VerificationGate()
