"""Approval manager: governed action gate lifecycle tests."""
import json

from app.gates.approval_manager import ApprovalManager


def make_manager(tmp_path):
    return ApprovalManager(data_dir=str(tmp_path))


class TestRedLineRejection:
    def test_rejects_destructive(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("terminal_exec", {"command": "rm -rf /"})
        assert res["approved"] is False
        assert res["status"] == "REJECTED_RED_LINE"
        assert "rm -rf" in res["detail"]

    def test_recorded_in_ledger(self, tmp_path):
        m = make_manager(tmp_path)
        m.submit_action_for_governance("terminal_exec", {"command": "DROP TABLE users"})
        entries = m.get_ledger_entries()
        assert len(entries) == 1
        assert entries[0]["status"] == "REJECTED_RED_LINE"


class TestYellowGate:
    def test_unapproved_action_pauses(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("send_email", {"to": "x@y.com"})
        assert res["status"] == "PENDING_APPROVAL"
        assert "gate_id" in res

    def test_pending_appears_in_queue(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("send_email", {"to": "x@y.com"})
        pending = m.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["id"] == res["gate_id"]

    def test_resolve_approve(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("send_email", {"to": "x@y.com"})
        out = m.resolve_approval(res["gate_id"], approved=True, operator_note="ok")
        assert out["success"] is True
        assert out["record"]["status"] == "APPROVED"
        assert m.get_pending_approvals() == []

    def test_resolve_deny(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("send_email", {"to": "x@y.com"})
        out = m.resolve_approval(res["gate_id"], approved=False)
        assert out["success"] is True
        assert out["record"]["status"] == "DENIED"

    def test_resolve_unknown_gate_fails(self, tmp_path):
        m = make_manager(tmp_path)
        out = m.resolve_approval("nonexistent", approved=True)
        assert out["success"] is False


class TestSafeActions:
    def test_read_only_auto_approved(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("read_file", {"path": "/opt/data/workspace/AGENTS.md"})
        assert res["approved"] is True
        assert res["status"] == "AUTO_APPROVED"

    def test_strict_mode_blocks_safe_actions(self, tmp_path, monkeypatch):
        from app import config
        monkeypatch.setattr(config.settings, "approvals_mode", "strict")
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("read_file", {"path": "/tmp/x"})
        assert res["status"] == "PENDING_APPROVAL"


class TestLedgerReader:
    def test_empty_when_no_ledger(self, tmp_path):
        m = make_manager(tmp_path)
        assert m.get_ledger_entries() == []

    def test_corrupt_lines_skipped(self, tmp_path):
        m = make_manager(tmp_path)
        m.submit_action_for_governance("read_file", {"path": "/tmp/x"})
        with open(m.ledger_file, "a") as f:
            f.write("THIS IS NOT JSON\n")
        entries = m.get_ledger_entries()
        assert len(entries) == 1

    def test_limit(self, tmp_path):
        m = make_manager(tmp_path)
        for i in range(5):
            m.submit_action_for_governance("read_file", {"path": f"/tmp/{i}"})
        assert len(m.get_ledger_entries(limit=2)) == 2
