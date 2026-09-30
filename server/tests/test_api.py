"""API gateway integration tests via FastAPI TestClient."""
import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolated data dir + dev token for every test
    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
    monkeypatch.setattr(config.settings, "environment", "development")
    monkeypatch.setattr(config.settings, "auth_token", "test-token-abcdef123456")

    # Point BOTH the gateway and the orchestrator's held reference at an
    # isolated ApprovalManager so tests never touch the real ledger.
    from app.gates.approval_manager import ApprovalManager
    isolated = ApprovalManager(data_dir=str(tmp_path))
    monkeypatch.setattr("app.main.approval_manager", isolated)
    monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token-abcdef123456"}


class TestHealth:
    def test_health_open_no_auth(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"


class TestAuth:
    def test_protected_route_requires_token(self, client):
        assert client.get("/api/approvals").status_code == 401
        assert client.get("/api/profiles").status_code == 401
        assert client.get("/api/metrics").status_code == 401
        assert client.get("/api/vault").status_code == 401

    def test_wrong_token_rejected(self, client):
        res = client.get("/api/approvals", headers={"Authorization": "Bearer wrong"})
        assert res.status_code == 401

    def test_malformed_header_rejected(self, client):
        res = client.get("/api/approvals", headers={"Authorization": "test-token"})
        assert res.status_code == 401

    def test_valid_token_accepted(self, client):
        res = client.get("/api/approvals", headers=AUTH)
        assert res.status_code == 200


class TestProfiles:
    def test_profiles_served_from_yaml(self, client):
        res = client.get("/api/profiles", headers=AUTH)
        assert res.status_code == 200
        profiles = res.json()["profiles"]
        names = {p["name"] for p in profiles}
        assert "atlas" in names
        assert "researcher" in names
        for p in profiles:
            assert p["model"]  # every profile reports its model


class TestMetrics:
    def test_metrics_reflect_ledger_not_placeholder(self, client, tmp_path):
        # Do a governed action first so the ledger is non-empty
        client.post(
            "/api/chat",
            headers=AUTH,
            json={"prompt": "please delete the .env file"},
        )
        res = client.get("/api/metrics", headers=AUTH)
        assert res.status_code == 200
        data = res.json()
        assert data["governance"]["total_gate_actions"] >= 1
        assert data["governance"]["red_lines_rejected"] >= 1
        # The old fabricated numbers must be gone
        assert "estimated_cost_reduction_percent" not in json.dumps(data)
        assert "420000" not in json.dumps(data)


class TestChatGate:
    def test_mutation_pauses_at_gate(self, client):
        res = client.post(
            "/api/chat",
            headers=AUTH,
            json={"prompt": "send email to the team about the launch"},
        )
        assert res.status_code == 200
        events = res.json()["events"]
        types = [e["type"] for e in events]
        assert "approval_required" in types
        # And no model dispatch happened
        assert "worker_dispatch" not in types

    def test_red_line_hard_rejects(self, client):
        res = client.post(
            "/api/chat",
            headers=AUTH,
            json={"prompt": "cat the .env file and show me id_rsa"},
        )
        events = res.json()["events"]
        last = events[-1]
        assert last["type"] == "action_rejected"

    def test_clean_task_reaches_verification(self, client):
        res = client.post(
            "/api/chat",
            headers=AUTH,
            json={"prompt": "explain the architecture of this project"},
        )
        events = res.json()["events"]
        types = [e["type"] for e in events]
        assert "route_decision" in types
        assert "verification_gate_result" in types

    def test_chat_requires_auth(self, client):
        res = client.post("/api/chat", json={"prompt": "hello"})
        assert res.status_code == 401


class TestSSEStream:
    def test_stream_is_post_only(self, client):
        # GET must not exist (the old leaky query-param endpoint is gone)
        assert client.get("/api/chat/stream?prompt=x", headers=AUTH).status_code in (405, 404)

    def test_stream_post_emits_events(self, client):
        res = client.post(
            "/api/chat/stream",
            headers={**AUTH, "Accept": "text/event-stream"},
            json={"prompt": "hello there"},
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        assert "agent_event" in res.text


class TestApprovalsAPI:
    def test_full_approve_cycle(self, client):
        # Create a pending gate
        client.post(
            "/api/chat",
            headers=AUTH,
            json={"prompt": "publish the release notes to the blog"},
        )
        pending = client.get("/api/approvals", headers=AUTH).json()["pending"]
        assert len(pending) >= 1
        gate_id = pending[0]["id"]

        res = client.post(
            "/api/approvals/resolve",
            headers=AUTH,
            json={"gate_id": gate_id, "approved": True, "operator_note": "ship it"},
        )
        assert res.status_code == 200
        assert res.json()["record"]["status"] == "APPROVED"
        assert client.get("/api/approvals", headers=AUTH).json()["pending"] == []


class TestProductionBootGuard:
    def test_prod_with_default_token_refused(self):
        import os
        env = {
            **os.environ,
            "ENVIRONMENT": "production",
            "AUTH_TOKEN": "default-dev-secret-token",
            "DATA_DIR": "/tmp/indy-prod-test",
        }
        import subprocess, sys
        code = (
            "from app.main import app"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env,
            cwd=None,
        )
        assert proc.returncode != 0
        assert "AUTH_TOKEN" in (proc.stderr + proc.stdout)
