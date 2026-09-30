#!/usr/bin/env python3
"""
mechanical_triage.py — Zero-Token Deterministic Task Processor.

NEVER burn LLM tokens on pure mechanical sorting, classification, regex
filtering, or static transformations. The Chief of Staff imports
`classify_incoming_intent` from here so gateway routing and the standalone
zero-token pipeline can never drift apart.
"""

import re
from typing import Any, Dict, List


def classify_incoming_intent(text: str) -> Dict[str, Any]:
    """
    Deterministically classify intent without calling an LLM.
    Returns targeted persona/profile and execution mode.
    """
    clean = text.strip()
    low = clean.lower()

    # 1. Direct command prefixes (canonical routing table)
    if low.startswith("/research") or low.startswith("/find"):
        return {"route": "researcher", "tier": "worker", "action": "deep_search", "query": clean.split(maxsplit=1)[-1]}
    if low.startswith("/write") or low.startswith("/draft"):
        return {"route": "writer", "tier": "worker", "action": "content_draft", "prompt": clean.split(maxsplit=1)[-1]}
    if low.startswith("/seo") or low.startswith("/kw"):
        return {"route": "seo", "tier": "worker", "action": "keyword_audit", "target": clean.split(maxsplit=1)[-1]}
    if low.startswith("/ops") or low.startswith("/task"):
        return {"route": "ops", "tier": "worker", "action": "ticket_management", "detail": clean.split(maxsplit=1)[-1]}
    if low.startswith("/code") or low.startswith("/fix"):
        return {"route": "coder", "tier": "primary", "action": "repo_investigation", "context": clean.split(maxsplit=1)[-1]}

    # 2. Heuristic matches for common intents
    if re.search(r"\b(research|compare|competitor|look into|literature)\b", low):
        return {"route": "researcher", "tier": "worker", "action": "deep_search", "query": clean}
    if re.search(r"\b(draft|write|copy|document|changelog)\b", low):
        return {"route": "writer", "tier": "worker", "action": "content_draft", "prompt": clean}
    if re.search(r"\b(seo|keyword|search console|impressions)\b", low):
        return {"route": "seo", "tier": "worker", "action": "keyword_audit", "target": clean}
    if re.search(r"\b(tickets?|issues?|sprint|linear)\b", low):
        return {"route": "ops", "tier": "worker", "action": "ticket_management", "detail": clean}
    if re.search(r"\b(bug|refactor|function|code|typescript|python)\b", low):
        return {"route": "coder", "tier": "primary", "action": "repo_investigation", "context": clean}

    # 3. Heuristic regex matches for common mechanical actions
    if re.search(r"^(list|show|get|fetch)\s+(issues|tasks|tickets|prs)", low):
        return {"route": "ops", "tier": "worker", "action": "read_tickets_direct", "fast_path": True}

    if re.search(r"(summarize|read|parse)\s+https?://", low):
        urls = re.findall(r"https?://[^\s]+", clean)
        return {"route": "researcher", "tier": "worker", "action": "url_ingest", "urls": urls}

    # 4. Default fallback to Chief of Staff (Atlas) for ambiguous/reasoning queries
    return {"route": "atlas", "tier": "primary", "action": "reason_and_orchestrate", "raw_prompt": clean}


def triage_inbox_items(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Sort and filter items into categories using zero tokens.
    """
    triaged: Dict[str, List[Dict[str, Any]]] = {
        "urgent_notifications": [],
        "automated_noise": [],
        "actionable_todos": []
    }

    noise_patterns = [r"noreply@", r"unsubscribe", r"security alert.*login", r"daily digest"]
    urgent_patterns = [r"payment failed", r"production down", r"critical error", r"urgent"]

    for item in items:
        subject = item.get("subject", "")
        sender = item.get("sender", "")
        content = f"{subject} {sender}".lower()

        if any(re.search(p, content) for p in noise_patterns):
            triaged["automated_noise"].append(item)
        elif any(re.search(p, content) for p in urgent_patterns):
            triaged["urgent_notifications"].append(item)
        else:
            triaged["actionable_todos"].append(item)

    return triaged


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = classify_incoming_intent(query)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "ready", "engine": "mechanical_triage", "tokens_burned": 0}))
