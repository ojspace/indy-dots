"""Narrow GitHub connector: list_issues (read-only, SAFE) vs create_issue (mutating).

Uses GitHub REST API with GITHUB_TOKEN from env. Fail-closed: missing
token or any network error returns {"ok": False, "error": ...} — never
fabricates issues. Governance (red-line check + approval) is enforced by
the caller via approval_manager; these executors never bypass it.
"""

import os
from typing import Any, Dict, List, Optional

import httpx

GITHUB_API = "https://api.github.com"

# Read-only vs mutating split. Only READ_ACTIONS may appear in SAFE_ACTIONS.
READ_ACTIONS = ("list_issues",)
WRITE_ACTIONS = ("create_issue",)


def _get_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token
    # Encrypted store fallback (env wins when set). Never logged.
    try:
        from ..security.credential_store import get_provider_key

        return get_provider_key("github")
    except Exception:
        return ""


def _get_default_repo() -> str:
    return os.getenv("GITHUB_REPO", "")


async def list_issues(
    repo: str = "",
    state: str = "open",
    limit: int = 10,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """List issues for owner/repo. Read-only. Fail-closed on error."""
    repo = repo or _get_default_repo()
    if not repo or "/" not in repo:
        return {
            "ok": False,
            "error": "No GitHub repo specified (expected 'owner/repo' in prompt or GITHUB_REPO env).",
        }
    token = _get_token()
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN not configured."}
    url = f"{GITHUB_API}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    params = {"state": state, "per_page": max(1, min(limit, 100))}
    try:
        if client is not None:
            resp = await client.get(url, headers=headers, params=params)
        else:
            async with httpx.AsyncClient(timeout=20.0) as c:
                resp = await c.get(url, headers=headers, params=params)
        resp.raise_for_status()
        items: List[Dict[str, Any]] = resp.json()
        slim = [
            {
                "number": i.get("number"),
                "title": i.get("title"),
                "state": i.get("state"),
                "url": i.get("html_url"),
            }
            for i in items[:limit]
        ]
        return {"ok": True, "repo": repo, "issues": slim}
    except Exception as e:
        return {"ok": False, "error": f"GitHub list_issues failed: {str(e)[:300]}"}


async def create_issue(
    repo: str = "",
    title: str = "",
    body: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Create an issue. Mutating — caller must hold an APPROVED/AUTO_APPROVED gate."""
    repo = repo or _get_default_repo()
    if not repo or "/" not in repo:
        return {
            "ok": False,
            "error": "No GitHub repo specified (expected 'owner/repo' in prompt or GITHUB_REPO env).",
        }
    if not title.strip():
        return {"ok": False, "error": "Issue title is required."}
    token = _get_token()
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN not configured."}
    url = f"{GITHUB_API}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        if client is not None:
            resp = await client.post(url, headers=headers, json={"title": title, "body": body})
        else:
            async with httpx.AsyncClient(timeout=20.0) as c:
                resp = await c.post(url, headers=headers, json={"title": title, "body": body})
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "repo": repo,
            "issue": {
                "number": data.get("number"),
                "title": data.get("title"),
                "url": data.get("html_url"),
            },
        }
    except Exception as e:
        return {"ok": False, "error": f"GitHub create_issue failed: {str(e)[:300]}"}
