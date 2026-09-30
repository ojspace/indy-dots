import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Allow the server package to be imported when this script runs from a repo
# checkout (server/ is on sys.path when invoked as `python -m scripts.gate_runner`
# from server/, or standalone with PYTHONPATH set).
try:
    from app.policy import check_red_lines
except ImportError:  # pragma: no cover - fallback for repo-root invocation
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
    from app.policy import check_red_lines


def get_ledger_path() -> Path:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir) / "gate_ledger.jsonl"
    default_dir = Path("/opt/data")
    try:
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir / "gate_ledger.jsonl"
    except (PermissionError, OSError):
        local_dir = Path(__file__).resolve().parent.parent / "data"
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir / "gate_ledger.jsonl"

LEDGER_PATH = get_ledger_path()

def record_gate_request(action_type: str, payload: dict, operator_approved: bool = False) -> dict:
    """
    Validates the action against Red Lines and Yellow Lines.
    If high-risk and not explicitly approved, logs to ledger in PENDING state and halts.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    action_hash = __import__("hashlib").sha256(
        f"{action_type}:{json.dumps(payload, sort_keys=True)}".encode()
    ).hexdigest()[:12]

    # Red Line Checks — shared policy module (single source of truth)
    hit = check_red_lines(payload)
    if hit:
        pattern, reason = hit
        entry = {
            "id": action_hash,
            "timestamp": timestamp,
            "action": action_type,
            "status": "AUTO_REJECTED",
            "reason": f"Violates RED LINE: {reason}",
            "payload": payload
        }
        _append_ledger(entry)
        return {"status": "REJECTED", "code": 403, "detail": entry["reason"]}

    # Yellow Line (Dry Run & Human Approval Required)
    if not operator_approved:
        entry = {
            "id": action_hash,
            "timestamp": timestamp,
            "action": action_type,
            "status": "PENDING_APPROVAL",
            "dry_run_receipt": {
                "impact": f"Action '{action_type}' prepared for execution.",
                "parameters": payload
            }
        }
        _append_ledger(entry)
        return {
            "status": "PENDING_APPROVAL",
            "gate_id": action_hash,
            "message": "Action paused at yellow gate. Requires operator sign-off in Web UI or Telegram."
        }

    # Approved Execution
    entry = {
        "id": action_hash,
        "timestamp": timestamp,
        "action": action_type,
        "status": "EXECUTED",
        "operator_approved": True,
        "payload": payload
    }
    _append_ledger(entry)
    return {"status": "APPROVED_AND_EXECUTED", "gate_id": action_hash}


def _append_ledger(entry: dict):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    test_action = {"command": "git status", "target": "workspace"}
    res = record_gate_request("terminal_exec", test_action, operator_approved=False)
    print(json.dumps(res, indent=2))
