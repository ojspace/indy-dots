import json
import fcntl
import hashlib
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..config import settings
from ..policy import check_red_lines

class ApprovalManager:
    """
    Governed Action Gate: records every mutating action to an append-only
    JSONL ledger. Red lines auto-reject; everything else pauses for
    operator sign-off unless auto-approved by policy.
    """

    # Actions safe to auto-approve with a ledger trail (read-only class).
    # Writes (create_issue, mcp_write, send_email, ...) must NEVER be added here.
    SAFE_ACTIONS = ("read_file", "search_web", "list_issues", "mcp_read", "query_vault", "mechanical_triage")

    def __init__(self, data_dir: Optional[str] = None):
        self.ledger_file = Path(data_dir or settings.data_dir) / "gate_ledger.jsonl"
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

    def get_ledger_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Most recent ledger entries (newest last), capped at `limit`."""
        if not self.ledger_file.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with open(self.ledger_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:]

    def submit_action_for_governance(
        self,
        action_type: str,
        payload: Dict[str, Any],
        caller: str = "orchestrator",
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        action_hash = hashlib.sha256(
            f"{action_type}:{json.dumps(payload, sort_keys=True)}:{timestamp}".encode()
        ).hexdigest()[:12]

        # Red line check via shared policy (single source of truth)
        hit = check_red_lines(payload)
        if hit:
            pattern, reason = hit
            entry = {
                "id": action_hash,
                "timestamp": timestamp,
                "action": action_type,
                "caller": caller,
                "status": "REJECTED_RED_LINE",
                "reason": f"Violates RED LINE policy against '{pattern}': {reason}",
                "payload": payload,
            }
            self._record(entry)
            return {
                "approved": False,
                "status": "REJECTED_RED_LINE",
                "gate_id": action_hash,
                "detail": entry["reason"],
            }

        # Auto-safe pass or yellow gate pause
        if action_type in self.SAFE_ACTIONS and settings.approvals_mode != "strict":
            entry = {
                "id": action_hash,
                "timestamp": timestamp,
                "action": action_type,
                "caller": caller,
                "status": "AUTO_APPROVED",
                "payload": payload,
            }
            self._record(entry)
            return {"approved": True, "status": "AUTO_APPROVED", "gate_id": action_hash}

        # Yellow Gate: Require Operator Approval
        # HTML-escape user-controlled content in dry_run so ledger readers
        # rendering it as HTML cannot be hit with stored XSS. The raw
        # payload is preserved for execution; only the display copy is escaped.
        def _esc(v: Any) -> Any:
            return html.escape(str(v)) if isinstance(v, str) else v
        safe_params = {k: _esc(v) for k, v in (payload or {}).items()} if isinstance(payload, dict) else _esc(payload)
        entry = {
            "id": action_hash,
            "timestamp": timestamp,
            "action": action_type,
            "caller": caller,
            "status": "PENDING_APPROVAL",
            "dry_run": {
                "summary": html.escape(f"Requesting approval to execute {action_type}"),
                "parameters": safe_params,
            },
            "payload": payload,
        }
        self._record(entry)
        return {
            "approved": False,
            "status": "PENDING_APPROVAL",
            "gate_id": action_hash,
            "message": "Action paused. Operator review required.",
        }

    def resolve_approval(
        self, gate_id: str, approved: bool, operator_note: Optional[str] = None
    ) -> Dict[str, Any]:
        records = []
        target = None
        # Exclusive lock around read-modify-write so concurrent resolvers
        # cannot interleave and lose updates (whole-file rewrite).
        lock_path = self.ledger_file.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+") as lock_f:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
            except OSError:
                pass
            try:
                if self.ledger_file.exists():
                    with open(self.ledger_file, "r") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    rec = json.loads(line)
                                except json.JSONDecodeError:
                                    continue
                                if rec.get("id") == gate_id and rec.get("status") == "PENDING_APPROVAL":
                                    rec["status"] = "APPROVED" if approved else "DENIED"
                                    rec["resolved_at"] = datetime.now(timezone.utc).isoformat()
                                    rec["operator_note"] = html.escape(str(operator_note)) if operator_note else operator_note
                                    target = rec
                                records.append(rec)

                if target:
                    with open(self.ledger_file, "w") as f:
                        for rec in records:
                            f.write(json.dumps(rec) + "\n")
                    return {"success": True, "record": target}
            finally:
                try:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
                except OSError:
                    pass

        return {"success": False, "error": f"Pending gate {gate_id} not found."}

    def _record(self, entry: Dict[str, Any]):
        with open(self.ledger_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

approval_manager = ApprovalManager()
