"""
web_search.py — Governed read-only web search tool (P2: /search).

Open-Dots reference: /search runs as a read-only external action with
audit events and a keyless fallback. This module follows the same pattern:

- You.com Search API (https://api.ydc-index.io/search) when YDC_API_KEY
  is set; otherwise the same endpoint without a key (keyless free profile).
- Timeout 15s. Returns a normalized title/url/snippet list.
- Fails closed: on any error returns {"ok": False, "error": ..., "results": []}.
  Never fabricates results. Never logs secrets.
- Every run goes through approval_manager as action_type "search_web",
  which lives in SAFE_ACTIONS (read-only class) and produces a ledger entry
  (AUTO_APPROVED outside strict mode).
"""

import os
from typing import Any, Dict, List, Tuple

import httpx

SEARCH_ENDPOINT = "https://api.ydc-index.io/search"
TIMEOUT_SECONDS = 15.0


def _api_key() -> str:
    """Prefer YDC_API_KEY; fall back to legacy MCP_SEARCH_API_KEY. Never logged."""
    try:
        from ..config import settings

        key = (getattr(settings, "ydc_api_key", "") or "").strip()
        if key:
            return key
    except Exception:
        pass
    env_key = (os.getenv("YDC_API_KEY", "") or os.getenv("MCP_SEARCH_API_KEY", "")).strip()
    if env_key:
        return env_key
    # Encrypted store fallback (env wins when set). Never logged.
    try:
        from ..security.credential_store import get_provider_key

        return get_provider_key("ydc")
    except Exception:
        return ""


def _normalize_hits(data: Any) -> List[Dict[str, str]]:
    """Tolerantly normalize You.com response shapes to title/url/snippet."""
    hits: List[Any] = []
    if isinstance(data, dict):
        if isinstance(data.get("hits"), list):
            hits = data["hits"]
        elif isinstance(data.get("web"), dict) and isinstance(data["web"].get("results"), list):
            hits = data["web"]["results"]
        elif isinstance(data.get("results"), list):
            hits = data["results"]
    out: List[Dict[str, str]] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        title = str(h.get("title", "") or "")[:200]
        url = str(h.get("url", "") or h.get("link", "") or "")[:500]
        snippet = ""
        snips = h.get("snippets")
        if isinstance(snips, list) and snips:
            snippet = str(snips[0] or "")[:500]
        elif isinstance(h.get("snippet"), str):
            snippet = h["snippet"][:500]
        elif isinstance(h.get("description"), str):
            snippet = h["description"][:500]
        if url:
            out.append({"title": title, "url": url, "snippet": snippet})
    return out


async def web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    """
    Raw (ungoverned) web search. Prefer governed_web_search() so every
    run produces a ledger entry. Fails closed — never raises, never fabricates.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "profile": "none"}
    try:
        n = max(1, min(int(num_results or 5), 10))
    except (TypeError, ValueError):
        n = 5

    key = _api_key()
    profile = "keyed" if key else "keyless"
    headers = {"X-API-Key": key} if key else {}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                SEARCH_ENDPOINT,
                params={"query": q, "num_web_results": n},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        results = _normalize_hits(data)[:n]
        return {"ok": True, "profile": profile, "results": results}
    except Exception as e:
        # Fail closed: report, don't fabricate. No secrets in the message.
        return {"ok": False, "error": str(e)[:300] or "search failed", "results": [], "profile": profile}


async def governed_web_search(
    query: str, caller: str = "researcher", num_results: int = 5
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Governed entry point shared by the orchestrator and POST /api/search.
    Always submits action_type "search_web" (SAFE read-only) so every run
    produces a ledger entry, then runs web_search.
    Returns (gate, result).
    """
    from ..gates.approval_manager import approval_manager

    q = (query or "").strip()
    gate = approval_manager.submit_action_for_governance(
        action_type="search_web",
        payload={"query": q[:500]},
        caller=caller,
    )
    result = await web_search(q, num_results=num_results)
    return gate, result
