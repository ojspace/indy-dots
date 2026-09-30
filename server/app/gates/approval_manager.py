import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import settings

class ApprovalManager:
    def __init__(self):
        self.ledger_file = Path(settings.data_dir) / "gate_ledger.jsonl"
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        if not self.ledger_file.exists():
            return []
        pending = []
        with open(self.ledger_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if record.get("status") == "PENDING_APPROVAL":
                            pending.append(record)
                    except json.JSONDecodeError:
                        continue
        return pending

    def submit_action_for_governance(self, action_type: str, payload: Dict[str, Any], caller: str = "orchestrator") -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        action_hash = hashlib.sha256(f"{action_type}:{json.dumps(payload, sort_keys=True)}:{timestamp}".encode()).hexdigest()[:12]
        
        # Red line check
        red_lines = ["rm -rf", "git push --force", "DROP TABLE", ".env", "id_rsa", "eval("]
        payload_str = json.dumps(payload)
        for rl in red_lines:
            if rl in payload_str:
                entry = {
                    "id": action_hash,
                    "timestamp": timestamp,
                    "action": action_type,
                    "caller": caller,
                    "status": "REJECTED_RED_LINE",
                    "reason": f"Violates RED LINE policy against '{rl}'",
                    "payload": payload
                }
                self._record(entry)
                return {"approved": False, "status": "REJECTED_RED_LINE", "gate_id": action_hash, "detail": entry["reason"]}

        # Auto-safe pass or yellow gate pause
        safe_actions = ["read_file", "search_web", "list_issues", "query_vault", "mechanical_triage"]
        if action_type in safe_actions and settings.approvals_mode != "strict":
            entry = {
                "id": action_hash,
                "timestamp": timestamp,
                "action": action_type,
                "caller": caller,
                "status": "AUTO_APPROVED",
                "payload": payload
            }
            self._record(entry)
            return {"approved": True, "status": "AUTO_APPROVED", "gate_id": action_hash}

        # Yellow Gate: Require Operator Approval
        entry = {
            "id": action_hash,
            "timestamp": timestamp,
            "action": action_type,
            "caller": caller,
            "status": "PENDING_APPROVAL",
            "dry_run": {
                "summary": f"Requesting approval to execute {action_type}",
                "parameters": payload
            },
            "payload": payload
        }
        self._record(entry)
        return {
            "approved": False,
            "status": "PENDING_APPROVAL",
            "gate_id": action_hash,
            "message": "Action paused. Operator review required."
        }

    def resolve_approval(self, gate_id: str, approved: bool, operator_note: Optional[str] = None) -> Dict[str, Any]:
        records = []
        target = None
        if self.ledger_file.exists():
            with open(self.ledger_file, "r") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        if rec.get("id") == gate_id and rec.get("status") == "PENDING_APPROVAL":
                            rec["status"] = "APPROVED" if approved else "DENIED"
                            rec["resolved_at"] = datetime.now(timezone.utc).isoformat()
                            rec["operator_note"] = operator_note
                            target = rec
                        records.append(rec)
        
        if target:
            with open(self.ledger_file, "w") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")
            return {"success": True, "record": target}
        
        return {"success": False, "error": f"Pending gate {gate_id} not found."}

    def _record(self, entry: Dict[str, Any]):
        with open(self.ledger_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

approval_manager = ApprovalManager()
