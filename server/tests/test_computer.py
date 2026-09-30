"""Opt-in computer runtime (P4): providers, governance, wiring, API.

Covers: fake deterministic, docker-missing fails closed, remote
not-configured fails closed, YELLOW pause (never SAFE), red-line in
computer params rejected, no exec on PENDING, approved-path executes,
narrow detection, and the /api/computer endpoints (auth + governed).
"""
import json

import pytest

from app.gates.approval_manager import ApprovalManager
from app.computer import (
    COMPUTER_ACTION,
    detect_computer_request,
    get_provider,
    governed_computer_action,
)
from app.computer.base import ActionResult
from app.computer.fake import FakeComputerProvider


def make_manager(tmp_path):
    return ApprovalManager(data_dir=str(tmp_path))


def _patch_ledgers(monkeypatch, tmp_path):
    """Point every approval_manager holder at an isolated ledger."""
    isolated = ApprovalManager(data_dir=str(tmp_path))
    monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
    monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
    monkeypatch.setattr("app.main.approval_manager", isolated)
    return isolated


async def _empty_notes(*args, **kwargs):
    return []


class TestFakeDeterministic:
    async def test_navigate_deterministic(self):
        p = FakeComputerProvider()
        a = await p.navigate("https://example.com")
        b = await p.navigate("https://example.com")
        assert a.ok is True
        assert a.to_dict() == b.to_dict()
        assert a.to_dict()["data"]["url"] == "https://example.com"

    async def test_snapshot_deterministic(self):
        p = FakeComputerProvider()
        a = await p.snapshot()
        b = await p.snapshot()
        assert a.ok is True
        assert a.to_dict() == b.to_dict()

    async def test_act_echoes(self):
        p = FakeComputerProvider()
        res = await p.act("click", "the login button")
        assert res.ok is True
        assert res.to_dict()["data"]["action"] == "click"

    async def test_navigate_empty_fails_closed(self):
        p = FakeComputerProvider()
        res = await p.navigate("   ")
        assert res.ok is False
        assert res.error


class TestFactory:
    def test_default_is_fake(self, monkeypatch):
        monkeypatch.delenv("COMPUTER_PROVIDER", raising=False)
        from app import config

        monkeypatch.setattr(config.settings, "computer_provider", "fake")
        assert get_provider().name == "fake"

    def test_unknown_falls_back_to_fake(self, monkeypatch):
        from app import config

        monkeypatch.delenv("COMPUTER_PROVIDER", raising=False)
        monkeypatch.setattr(config.settings, "computer_provider", "quantum")
        assert get_provider().name == "fake"

    def test_env_selects_docker_and_remote(self, monkeypatch):
        monkeypatch.setenv("COMPUTER_PROVIDER", "docker")
        assert get_provider().name == "docker"
        monkeypatch.setenv("COMPUTER_PROVIDER", "remote")
        assert get_provider().name == "remote"


class TestFailClosedProviders:
    async def test_docker_missing_binary_fails_closed(self, monkeypatch):
        import app.computer.docker as docker_mod

        monkeypatch.setattr(docker_mod.shutil, "which", lambda *a, **k: None)
        res = await docker_mod.DockerComputerProvider().navigate("https://example.com")
        assert res.ok is False
        assert "Docker" in res.error

    async def test_docker_missing_image_fails_closed(self, monkeypatch, tmp_path):
        import app.computer.docker as docker_mod

        monkeypatch.setattr(docker_mod.shutil, "which", lambda *a, **k: "/usr/bin/docker")
        monkeypatch.setenv("COMPUTER_DOCKER_IMAGE", "indy-nonexistent-image-xyz:latest")

        class FakeProc:
            def __init__(self, rc=0):
                self.returncode = rc
                self.stdout = ""
                self.stderr = ""

        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[:2] == ["docker", "info"]:
                return FakeProc(rc=0)
            return FakeProc(rc=1)  # image inspect fails

        monkeypatch.setattr(docker_mod.subprocess, "run", fake_run)
        res = await docker_mod.DockerComputerProvider().navigate("https://example.com")
        assert res.ok is False
        assert "not found" in res.error

    async def test_remote_not_configured_fails_closed(self, monkeypatch):
        from app import config
        from app.computer.remote import RemoteComputerProvider

        monkeypatch.delenv("COMPUTER_REMOTE_URL", raising=False)
        monkeypatch.setattr(config.settings, "computer_remote_url", "")
        res = await RemoteComputerProvider().navigate("https://example.com")
        assert res.ok is False
        assert "not configured" in res.error


class TestGovernance:
    def test_computer_action_never_safe(self):
        assert COMPUTER_ACTION == "computer_navigate"
        assert COMPUTER_ACTION not in ApprovalManager.SAFE_ACTIONS

    def test_first_pass_pauses_with_dry_run(self, tmp_path):
        m = make_manager(tmp_path)
        res = m.submit_action_for_governance(
            COMPUTER_ACTION, {"op": "navigate", "target": "https://example.com"}
        )
        assert res["status"] == "PENDING_APPROVAL"
        assert res["approved"] is False
        pending = m.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["dry_run"]["parameters"]["op"] == "navigate"

    async def test_red_line_in_params_rejected(self, tmp_path, monkeypatch):
        _patch_ledgers(monkeypatch, tmp_path)
        gate, result = await governed_computer_action(
            op="navigate", target="https://example.com rm -rf /", caller="test"
        )
        assert gate["status"] == "REJECTED_RED_LINE"
        assert result is None

    async def test_pending_executes_nothing(self, tmp_path, monkeypatch):
        isolated = _patch_ledgers(monkeypatch, tmp_path)
        calls = []

        class CountingProvider(FakeComputerProvider):
            async def navigate(self, target="", assistant="default"):
                calls.append(("navigate", target))
                return await super().navigate(target, assistant)

            async def snapshot(self, assistant="default"):
                calls.append(("snapshot", ""))
                return await super().snapshot(assistant)

            async def act(self, action="", target="", assistant="default"):
                calls.append((action, target))
                return await super().act(action, target, assistant)

        monkeypatch.setattr("app.computer.get_provider", lambda *a, **k: CountingProvider())
        gate, result = await governed_computer_action(
            op="navigate", target="https://example.com", caller="test"
        )
        assert gate["status"] == "PENDING_APPROVAL"
        assert result is None
        assert calls == []
        assert len(isolated.get_pending_approvals()) == 1

    async def test_approved_path_executes(self, tmp_path, monkeypatch):
        isolated = _patch_ledgers(monkeypatch, tmp_path)
        monkeypatch.setattr(
            ApprovalManager, "submit_action_for_governance",
            lambda self, **k: {"approved": True, "status": "APPROVED", "gate_id": "g1"},
        )
        gate, result = await governed_computer_action(
            op="snapshot", caller="test", provider=FakeComputerProvider()
        )
        assert gate["approved"] is True
        assert result is not None and result.ok is True
        # Approved-path execution writes no pending entry
        assert isolated.get_pending_approvals() == []


class TestDetection:
    def test_verbs_detected(self):
        for prompt, op in [
            ("computer navigate https://example.com", "navigate"),
            ("computer snapshot", "snapshot"),
            ("computer click the login button", "click"),
            ("computer type hello into search", "type"),
            ("computer browse https://example.com/docs", "browse"),
        ]:
            req = detect_computer_request(prompt)
            assert req is not None, prompt
            assert req["op"] == op
            assert req["action_type"] == COMPUTER_ACTION

    def test_non_computer_prompts_ignored(self):
        assert detect_computer_request("list github issues for octo/repo") is None
        assert detect_computer_request("send email to the team") is None
        assert detect_computer_request("explain the architecture") is None
        assert detect_computer_request("compute the navigate route") is None


class TestChiefOfStaffWiring:
    async def _collect(self, cos, prompt):
        return [e async for e in cos.execute_task(prompt)]

    async def test_computer_prompt_pauses_no_exec(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
        monkeypatch.setattr(cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes())

        calls = []

        class CountingProvider(FakeComputerProvider):
            async def navigate(self, target="", assistant="default"):
                calls.append(target)
                return await super().navigate(target, assistant)

        # Patch the factory used inside the governed path
        import app.computer as comp_mod

        monkeypatch.setattr(comp_mod, "get_provider", lambda *a, **k: CountingProvider())

        events = await self._collect(cos_mod.chief_of_staff, "computer navigate https://example.com")
        types = [e["type"] for e in events]
        assert "approval_required" in types
        assert "computer_result" not in types
        assert "worker_dispatch" not in types
        assert calls == []  # no exec on PENDING

    async def test_computer_red_line_rejected_in_pipeline(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
        monkeypatch.setattr(cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes())

        events = await self._collect(
            cos_mod.chief_of_staff, "computer navigate https://example.com rm -rf /"
        )
        assert events[-1]["type"] == "action_rejected"

    async def test_approved_computer_yields_result(self, tmp_path, monkeypatch):
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes())

        async def fake_governed(op, target="", caller="", assistant="default", provider=None):
            return (
                {"approved": True, "status": "APPROVED", "gate_id": "g1"},
                ActionResult(ok=True, provider="fake", op=op, data={"url": target}),
            )

        monkeypatch.setattr(cos_mod, "governed_computer_action", fake_governed)
        events = await self._collect(cos_mod.chief_of_staff, "computer snapshot")
        types = [e["type"] for e in events]
        assert "computer_result" in types
        assert "approval_required" not in types

    async def test_existing_connector_path_untouched(self, tmp_path, monkeypatch):
        """2.5a still handles GitHub without touching the computer stage."""
        from app.orchestrator import chief_of_staff as cos_mod

        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr(cos_mod, "approval_manager", isolated)
        monkeypatch.setattr(cos_mod.knowledge_vault, "query_notes", lambda *a, **k: _empty_notes())

        async def fake_list(repo="", **kwargs):
            return {"ok": True, "repo": repo or "o/r", "issues": []}

        monkeypatch.setattr(cos_mod.github_connector, "list_issues", fake_list)
        events = await self._collect(cos_mod.chief_of_staff, "list github issues for octo/repo")
        types = [e["type"] for e in events]
        assert "connector_result" in types
        assert "computer_result" not in types


class TestComputerAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from app import config
        from app.main import app

        monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
        monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
        monkeypatch.setattr(config.settings, "environment", "development")
        monkeypatch.setattr(config.settings, "auth_token", "test-token-abcdef123456")
        monkeypatch.setattr(config.settings, "computer_provider", "fake")
        monkeypatch.delenv("COMPUTER_PROVIDER", raising=False)
        _patch_ledgers(monkeypatch, tmp_path)
        return TestClient(app)

    AUTH = {"Authorization": "Bearer test-token-abcdef123456"}

    def test_status_requires_auth(self, client):
        assert client.get("/api/computer/status").status_code == 401

    def test_status_reports_fake_not_hardened(self, client):
        res = client.get("/api/computer/status", headers=self.AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["provider"] == "fake"
        assert body["opt_in"] is False
        assert body["sandbox_hardened"] is False
        # No secrets leak in the status payload (names/booleans only)
        dumped = json.dumps(body)
        assert "remote_token" not in dumped.lower()
        assert "AUTH_TOKEN" not in dumped
        assert body["workspace_root"]

    def test_act_requires_auth(self, client):
        assert client.post("/api/computer/act", json={"op": "navigate"}).status_code == 401

    def test_act_invalid_op_rejected(self, client):
        res = client.post(
            "/api/computer/act", headers=self.AUTH, json={"op": "rm", "target": "x"}
        )
        assert res.status_code == 400

    def test_act_pauses_yellow(self, client):
        res = client.post(
            "/api/computer/act",
            headers=self.AUTH,
            json={"op": "navigate", "target": "https://example.com"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "PENDING_APPROVAL"
        assert body["approved"] is False
        assert body["gate_id"]
        assert "result" not in body  # nothing executed

    def test_act_red_line_rejected(self, client):
        res = client.post(
            "/api/computer/act",
            headers=self.AUTH,
            json={"op": "type", "target": "cat the .env file"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "REJECTED_RED_LINE"
