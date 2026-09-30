"""Governed connectors: red-line rejection, read auto-approve, write pend, resolve flow."""
import pytest

from app.gates.approval_manager import ApprovalManager
from app.connectors import github as github_connector
from app.connectors import mcp_client


def make_manager(tmp_path):
    return ApprovalManager(data_dir=str(tmp_path))


class TestConnectorRedLines:
    def test_list_issues_red_line_rejected(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("list_issues", {"repo": "o/r", "summary": "list issues rm -rf /"})
        assert res["status"] == "REJECTED_RED_LINE"
        assert res["approved"] is False

    def test_create_issue_red_line_rejected(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            "create_issue", {"repo": "o/r", "title": "x", "summary": "read the .env file"}
        )
        assert res["status"] == "REJECTED_RED_LINE"

    def test_mcp_write_red_line_rejected(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            "mcp_write", {"server": "linear", "tool": "write_item", "summary": "DROP TABLE users"}
        )
        assert res["status"] == "REJECTED_RED_LINE"


class TestReadAutoApproved:
    def test_list_issues_auto_approved(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("list_issues", {"repo": "o/r", "summary": "list issues"})
        assert res["status"] == "AUTO_APPROVED"
        assert res["approved"] is True

    def test_mcp_read_auto_approved(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            "mcp_read", {"server": "linear", "tool": "list_items", "summary": "mcp list"}
        )
        assert res["status"] == "AUTO_APPROVED"
        assert res["approved"] is True


class TestWritePends:
    def test_create_issue_pends_with_dry_run(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            "create_issue", {"repo": "o/r", "title": "bug", "summary": "create issue"}
        )
        assert res["status"] == "PENDING_APPROVAL"
        assert res["approved"] is False
        pending = m.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["dry_run"]["parameters"]["title"] == "bug"

    def test_mcp_write_pends(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            "mcp_write", {"server": "linear", "tool": "write_item", "summary": "mcp write"}
        )
        assert res["status"] == "PENDING_APPROVAL"
        assert res["approved"] is False

    def test_writes_never_in_safe_actions(self):
        assert "create_issue" not in ApprovalManager.SAFE_ACTIONS
        assert "mcp_write" not in ApprovalManager.SAFE_ACTIONS
        assert "list_issues" in ApprovalManager.SAFE_ACTIONS
        assert "mcp_read" in ApprovalManager.SAFE_ACTIONS


class TestResolveFlow:
    def test_resolve_approve_write(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("create_issue", {"repo": "o/r", "title": "t"})
        out = m.resolve_approval(res["gate_id"], approved=True, operator_note="ship")
        assert out["success"] is True
        assert out["record"]["status"] == "APPROVED"
        assert m.get_pending_approvals() == []

    def test_resolve_deny_write(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance("mcp_write", {"server": "s", "tool": "write_item"})
        out = m.resolve_approval(res["gate_id"], approved=False)
        assert out["success"] is True
        assert out["record"]["status"] == "DENIED"


class TestFailClosed:
    async def test_github_list_no_token_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        res = await github_connector.list_issues(repo="octo/repo")
        assert res["ok"] is False
        assert "GITHUB_TOKEN" in res["error"]

    async def test_github_create_no_repo_fails_closed(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPO", raising=False)
        res = await github_connector.create_issue(repo="", title="t")
        assert res["ok"] is False

    async def test_mcp_allowlist_rejects(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWLIST", "linear")
        res = await mcp_client.dispatch(server="evil", tool="list_items", params={})
        assert res["ok"] is False
        assert "allowlist" in res["error"].lower()

    async def test_mcp_empty_allowlist_refuses(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWLIST", "")
        res = await mcp_client.dispatch(server="linear", tool="list_items", params={})
        assert res["ok"] is False


class TestChiefOfStaffWiring:
    async def _collect(self, cos, prompt):
        events = []
        async for e in cos.execute_task(prompt):
            events.append(e)
        return events

    async def test_list_issues_governed_read(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(
            cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes()
        )

        async def fake_list(repo="", **kwargs):
            return {"ok": True, "repo": repo or "o/r", "issues": []}

        monkeypatch.setattr(cos_mod.github_connector, "list_issues", fake_list)
        events = await self._collect(cos_mod.chief_of_staff, "list github issues for octo/repo")
        types = [e["type"] for e in events]
        assert "connector_result" in types
        assert "approval_required" not in types
        assert "worker_dispatch" not in types

    async def test_create_issue_pauses(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(
            cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes()
        )
        events = await self._collect(cos_mod.chief_of_staff, "create github issue in octo/repo titled login bug")
        types = [e["type"] for e in events]
        assert "approval_required" in types
        assert "connector_result" not in types
        assert "worker_dispatch" not in types

    async def test_connector_red_line_rejected(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(
            cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes()
        )
        events = await self._collect(
            cos_mod.chief_of_staff, "list github issues for octo/repo rm -rf /"
        )
        assert events[-1]["type"] == "action_rejected"

    async def test_connector_network_error_is_model_error(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(
            cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes()
        )

        async def fake_fail(repo="", **kwargs):
            return {"ok": False, "error": "boom"}

        monkeypatch.setattr(cos_mod.github_connector, "list_issues", fake_fail)
        events = await self._collect(cos_mod.chief_of_staff, "list github issues for octo/repo")
        types = [e["type"] for e in events]
        assert "model_error" in types


async def _empty_notes(*args, **kwargs):
    return []
