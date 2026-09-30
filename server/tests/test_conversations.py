"""P3: conversation persistence tests."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.memory import conversations as conversation_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
    monkeypatch.setattr(config.settings, "environment", "development")
    monkeypatch.setattr(config.settings, "auth_token", "test-token-abcdef123456")

    from app.gates.approval_manager import ApprovalManager
    isolated = ApprovalManager(data_dir=str(tmp_path))
    monkeypatch.setattr("app.main.approval_manager", isolated)
    monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token-abcdef123456"}


class TestConversationStore:
    @pytest.mark.asyncio
    async def test_save_and_list_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
        await conversation_store.save_message("s1", "user", "hello")
        await conversation_store.save_message("s1", "assistant", "hi there")
        hist = await conversation_store.list_history("s1")
        assert [m["role"] for m in hist] == ["user", "assistant"]
        assert hist[0]["content"] == "hello"
        assert all(m["session_id"] == "s1" for m in hist)

    @pytest.mark.asyncio
    async def test_sessions_isolated_and_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
        for i in range(5):
            await conversation_store.save_message("a", "user", f"a{i}")
        await conversation_store.save_message("b", "user", "other")
        hist = await conversation_store.list_history("a", limit=3)
        assert len(hist) == 3
        assert [m["content"] for m in hist] == ["a0", "a1", "a2"]
        hist_b = await conversation_store.list_history("b")
        assert len(hist_b) == 1


class TestConversationAPI:
    def test_chat_persists_history(self, client):
        res = client.post(
            "/api/chat", headers=AUTH,
            json={"prompt": "explain the architecture of this project",
                  "session_id": "sess-1"},
        )
        assert res.status_code == 200
        hist = client.get(
            "/api/conversations",
            headers=AUTH, params={"session_id": "sess-1"},
        )
        assert hist.status_code == 200
        msgs = hist.json()["messages"]
        assert len(msgs) >= 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_stream_persists_history(self, client):
        res = client.post(
            "/api/chat/stream",
            headers={**AUTH, "Accept": "text/event-stream"},
            json={"prompt": "hello there", "session_id": "sess-stream"},
        )
        assert res.status_code == 200
        hist = client.get(
            "/api/conversations",
            headers=AUTH, params={"session_id": "sess-stream"},
        )
        assert hist.status_code == 200
        assert len(hist.json()["messages"]) >= 2

    def test_conversations_require_auth(self, client):
        assert client.get("/api/conversations").status_code == 401
        assert client.delete(
            "/api/conversations", params={"session_id": "x"}
        ).status_code == 401

    def test_delete_clears_session(self, client):
        client.post("/api/chat", headers=AUTH,
                    json={"prompt": "hello there", "session_id": "sess-del"})
        assert len(client.get(
            "/api/conversations", headers=AUTH,
            params={"session_id": "sess-del"}).json()["messages"]) >= 2
        d = client.delete("/api/conversations", headers=AUTH,
                          params={"session_id": "sess-del"})
        assert d.status_code == 200
        assert d.json()["deleted"] >= 2
        assert client.get(
            "/api/conversations", headers=AUTH,
            params={"session_id": "sess-del"}).json()["messages"] == []

    def test_persistence_failure_does_not_break_chat(self, client, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(conversation_store, "save_message", boom)
        res = client.post("/api/chat", headers=AUTH,
                          json={"prompt": "explain the architecture of this project"})
        assert res.status_code == 200
        assert res.json()["status"] == "completed"
        assert "events" in res.json()
