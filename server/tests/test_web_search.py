"""Governed /search (P2): triage route, You.com client, ledger, fail-closed."""
import json

import pytest

from app.mechanical_triage import classify_incoming_intent
from app.gates.approval_manager import ApprovalManager


class TestSearchRoute:
    def test_slash_search_routes_to_researcher_web_search(self):
        r = classify_incoming_intent("/search indy dots pricing")
        assert r["route"] == "researcher"
        assert r["tier"] == "worker"
        assert r["action"] == "web_search"
        assert "indy dots pricing" in r["query"]

    def test_slash_search_bare_query_empty_not_crash(self):
        r = classify_incoming_intent("/search")
        assert r["action"] == "web_search"
        assert r["query"] == ""

    def test_search_web_stays_safe(self, tmp_path):
        assert "search_web" in ApprovalManager.SAFE_ACTIONS


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            import httpx

            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        return self._payload


class FakeClient:
    """Minimal async stand-in for httpx.AsyncClient. Records last call."""

    last_kwargs = None
    behavior = "ok"  # ok | fail | no_key_check
    payload = {"hits": [{"title": "T", "url": "https://example.com", "snippets": ["S"]}]}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        FakeClient.last_kwargs = {"url": url, "params": params, "headers": headers}
        if FakeClient.behavior == "fail":
            raise ConnectionError("boom")
        return FakeResponse(FakeClient.payload)


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "ydc_api_key", "")
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    monkeypatch.delenv("MCP_SEARCH_API_KEY", raising=False)
    isolated = ApprovalManager(data_dir=str(tmp_path))
    # Point every holder at the isolated ledger so tests never touch real data.
    # governed_web_search() imports approval_manager from app.gates at call
    # time, so patching the source attribute is sufficient (no ws attr).
    monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
    monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
    import app.tools.web_search as ws

    monkeypatch.setattr(ws.httpx, "AsyncClient", FakeClient)
    return isolated


class TestWebSearchTool:
    async def test_happy_path(self, isolated_ledger, monkeypatch):
        FakeClient.behavior = "ok"
        FakeClient.last_kwargs = None
        from app.tools import web_search as ws

        gate, result = await ws.governed_web_search("hello world", caller="test")
        assert result["ok"] is True
        assert result["results"][0]["url"] == "https://example.com"
        assert result["results"][0]["title"] == "T"
        # Keyless fallback: no auth header when no key configured
        assert FakeClient.last_kwargs["headers"] == {}
        assert result["profile"] == "keyless"
        # Ledger entry written
        entries = isolated_ledger.get_ledger_entries()
        assert len(entries) == 1
        assert entries[0]["action"] == "search_web"
        assert entries[0]["status"] == "AUTO_APPROVED"

    async def test_keyed_profile_sends_header_no_leak(self, isolated_ledger, monkeypatch, caplog):
        import logging

        FakeClient.behavior = "ok"
        FakeClient.last_kwargs = None
        from app import config
        from app.tools import web_search as ws

        monkeypatch.setattr(config.settings, "ydc_api_key", "secret-123")
        with caplog.at_level(logging.INFO):
            gate, result = await ws.governed_web_search("keyed q", caller="test")
        assert result["profile"] == "keyed"
        assert FakeClient.last_kwargs["headers"] == {"X-API-Key": "secret-123"}
        # No secrets in logs
        assert "secret-123" not in caplog.text
        # Ledger payload must not contain the key either
        assert "secret-123" not in json.dumps(isolated_ledger.get_ledger_entries())

    async def test_network_failure_fails_closed(self, isolated_ledger):
        FakeClient.behavior = "fail"
        from app.tools import web_search as ws

        gate, result = await ws.governed_web_search("anything", caller="test")
        assert result["ok"] is False
        assert result["results"] == []
        assert "error" in result
        # Ledger entry STILL written even on failure
        entries = isolated_ledger.get_ledger_entries()
        assert len(entries) == 1
        assert entries[0]["action"] == "search_web"

    async def test_empty_query_fails_closed_with_ledger(self, isolated_ledger):
        from app.tools import web_search as ws

        gate, result = await ws.governed_web_search("   ", caller="test")
        assert result["ok"] is False
        assert result["results"] == []
        assert len(isolated_ledger.get_ledger_entries()) == 1


class TestSearchPipeline:
    async def test_execute_task_emits_search_events(self, tmp_path, monkeypatch):
        from app import config

        monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
        monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
        monkeypatch.setattr(config.settings, "ydc_api_key", "")
        monkeypatch.delenv("YDC_API_KEY", raising=False)
        monkeypatch.delenv("MCP_SEARCH_API_KEY", raising=False)
        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
        monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
        import app.tools.web_search as ws

        FakeClient.behavior = "ok"
        monkeypatch.setattr(ws.httpx, "AsyncClient", FakeClient)
        # No model keys => no worker_dispatch, but search events must still fire
        monkeypatch.setattr(config.settings, "primary_api_key", "")
        monkeypatch.setattr(config.settings, "worker_api_key", "")

        from app.orchestrator.chief_of_staff import ChiefOfStaff

        cos = ChiefOfStaff()
        events = [e async for e in cos.execute_task("/search test query")]
        types = [e["type"] for e in events]
        assert "search_dispatch" in types
        assert "search_results" in types
        sr = next(e for e in events if e["type"] == "search_results")
        assert sr["count"] >= 1
        # Ledger entry for the run
        assert any(e.get("action") == "search_web" for e in isolated.get_ledger_entries())


class TestSearchAPI:
    def test_post_search_requires_auth_and_returns_results(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from app import config
        from app.main import app

        monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
        monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
        monkeypatch.setattr(config.settings, "environment", "development")
        monkeypatch.setattr(config.settings, "auth_token", "test-token-abcdef123456")
        monkeypatch.setattr(config.settings, "ydc_api_key", "")
        monkeypatch.delenv("YDC_API_KEY", raising=False)
        monkeypatch.delenv("MCP_SEARCH_API_KEY", raising=False)
        isolated = ApprovalManager(data_dir=str(tmp_path))
        monkeypatch.setattr("app.main.approval_manager", isolated)
        monkeypatch.setattr("app.gates.approval_manager.approval_manager", isolated)
        monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
        import app.tools.web_search as ws

        FakeClient.behavior = "ok"
        monkeypatch.setattr(ws.httpx, "AsyncClient", FakeClient)

        client = TestClient(app)
        # No token => 401
        assert client.post("/api/search", json={"query": "x"}).status_code == 401
        res = client.post(
            "/api/search",
            headers={"Authorization": "Bearer test-token-abcdef123456"},
            json={"query": "indy dots"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["results"][0]["url"] == "https://example.com"
        assert body["gate_id"]
        assert len(isolated.get_ledger_entries()) == 1
