#!/usr/bin/env python3
"""
mechanical_triage.py — Zero-Token Deterministic Task Processor
Based on the 'jev' architectural pattern: NEVER burn LLM tokens on pure mechanical
sorting, classification, regex filtering, or static transformations.
"""

import sys
import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List

def classify_incoming_intent(text: str) -> Dict[str, Any]:
    """
    Deterministically classify intent without calling an LLM.
    Returns targeted persona/profile and execution mode.
    """
    clean = text.strip()
    
    # 1. Direct command prefixes
    if clean.startswith("/research") or clean.startswith("/find"):
        return {"route": "researcher", "action": "deep_search", "query": clean.split(maxsplit=1)[-1]}
    if clean.startswith("/write") or clean.startswith("/draft"):
        return {"route": "writer", "action": "content_draft", "prompt": clean.split(maxsplit=1)[-1]}
    if clean.startswith("/seo") or clean.startswith("/kw"):
        return {"route": "seo", "action": "keyword_audit", "target": clean.split(maxsplit=1)[-1]}
    if clean.startswith("/ops") or clean.startswith("/task"):
        return {"route": "ops", "action": "ticket_management", "detail": clean.split(maxsplit=1)[-1]}
    if clean.startswith("/code") or clean.startswith("/fix"):
        return {"route": "coder", "action": "repo_investigation", "context": clean.split(maxsplit=1)[-1]}

    # 2. Heuristic regex matches for common mechanical actions
    if re.search(r"^(list|show|get|fetch)\s+(issues|tasks|tickets|prs)", clean, re.IGNORECASE):
        return {"route": "ops", "action": "read_tickets_direct", "fast_path": True}
    
    if re.search(r"(summarize|read|parse)\s+https?://", clean, re.IGNORECASE):
        urls = re.findall(r"https?://[^\s]+", clean)
        return {"route": "researcher", "action": "url_ingest", "urls": urls}

    # 3. Default fallback to Chief of Staff (Atlas) for ambiguous/reasoning queries
    return {"route": "chief_of_staff", "action": "reason_and_orchestrate", "raw_prompt": clean}


def triage_inbox_items(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Sort and filter items into categories using zero tokens.
    """
    triaged = {
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
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = classify_incoming_intent(query)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "ready", "engine": "mechanical_triage", "tokens_burned": 0}))
