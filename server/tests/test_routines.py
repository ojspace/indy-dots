"""P5: routine scheduler — parser, CRUD, due-run execution, governance safety."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routines.scheduler import is_due, parse_cron, run_due_routines
from app.routines.store import RoutineStore


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "vault_dir", str(tmp_path / "vault"))
    monkeypatch.setattr(config.settings, "environment", "development")
    monkeypatch.setattr(config.settings, "auth_token", "test-token-abcdef123456")
    monkeypatch.delenv("ROUTINES_ENABLED", raising=False)
    # Isolated approval ledger for governance assertions.
    from app.gates.approval_manager import ApprovalManager

    isolated = ApprovalManager(data_dir=str(tmp_path))
    monkeypatch.setattr("app.main.approval_manager", isolated)
    monkeypatch.setattr("app.orchestrator.chief_of_staff.approval_manager", isolated)
    return tmp_path


@pytest.fixture
def client(tmp_data):
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token-abcdef123456"}
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class TestParser:
    def test_every_minutes(self):
        assert parse_cron("every_30m") == {"kind": "interval", "minutes": 30}

    def test_every_hours(self):
        assert parse_cron("every_6h") == {"kind": "interval", "minutes": 360}

    def test_daily(self):
        assert parse_cron("daily_09:30") == {"kind": "daily", "hour": 9, "minute": 30}

    @pytest.mark.parametrize(
        "bad", ["", "hourly", "every day", "every_0m", "every_1m", "every_4m", "every_5x", "daily_25:00",
                "daily_9:5", "daily_09:60", "* * * * *", "every_-5m"]
    )
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValueError):
            parse_cron(bad)


class TestDueLogic:
    def test_interval_first_run_is_due(self):
        assert is_due({"enabled": True, "cron": "every_30m", "last_run": None}, NOW)

    def test_interval_respects_elapsed(self):
        assert is_due(
            {"enabled": True, "cron": "every_30m",
             "last_run": (NOW - timedelta(minutes=31)).isoformat()}, NOW
        ) is True
        assert is_due(
            {"enabled": True, "cron": "every_30m",
             "last_run": (NOW - timedelta(minutes=10)).isoformat()}, NOW
        ) is False

    def test_disabled_never_due(self):
        assert is_due({"enabled": False, "cron": "every_5m", "last_run": None}, NOW) is False

    def test_daily_due_after_time(self):
        assert is_due({"enabled": True, "cron": "daily_09:30", "last_run": None}, NOW) is True

    def test_daily_not_due_before_time(self):
        early = NOW.replace(hour=8, minute=0)
        assert is_due({"enabled": True, "cron": "daily_09:30", "last_run": None}, early) is False

    def test_daily_not_due_twice_same_day(self):
        assert is_due(
            {"enabled": True, "cron": "daily_09:30",
             "last_run": NOW.replace(hour=10, minute=0).isoformat()}, NOW
        ) is False

    def test_bad_cron_never_due(self):
        assert is_due({"enabled": True, "cron": "hourly", "last_run": None}, NOW) is False


class TestStoreCRUD:
    def test_create_list_get(self, tmp_data):
        s = RoutineStore()
        r = s.create("morning", "summarize inbox", "daily_09:00")
        assert r["id"] and r["enabled"] is True and r["last_run"] is None
        assert len(s.list()) == 1
        assert s.get(r["id"])["prompt"] == "summarize inbox"

    def test_create_rejects_bad_cron_and_blanks(self, tmp_data):
        s = RoutineStore()
        with pytest.raises(ValueError):
            s.create("x", "y", "hourly")
        with pytest.raises(ValueError):
            s.create("", "y", "every_5m")
        with pytest.raises(ValueError):
            s.create("x", "", "every_5m")

    def test_enable_disable_delete(self, tmp_data):
        s = RoutineStore()
        r = s.create("r", "do thing", "every_15m")
        assert s.set_enabled(r["id"], False)["enabled"] is False
        assert s.set_enabled(r["id"], True)["enabled"] is True
        assert s.set_enabled("missing", True) is None
        assert s.delete(r["id"]) is True
        assert s.delete(r["id"]) is False
        assert s.get(r["id"]) is None


async def _ok_executor(prompt):
    yield {"type": "route_decision", "role": "researcher"}
    yield {"type": "content_chunk", "chunk": "done"}


async def _yellow_executor(prompt):
    yield {"type": "route_decision", "role": "ops"}
    yield {"type": "approval_required", "gate_id": "abc123", "action": "external_mutation"}


class TestDueRun:
    async def test_due_run_executes_and_records(self, tmp_data):
        s = RoutineStore()
        r = s.create("beat", "hello there", "every_5m")
        calls = []

        async def spy(prompt):
            calls.append(prompt)
            async for e in _ok_executor(prompt):
                yield e

        outcomes = await run_due_routines(now=NOW, executor=spy, store=s)
        assert outcomes == [{"id": r["id"], "name": "beat", "status": "completed"}]
        assert calls == ["hello there"]
        updated = s.get(r["id"])
        assert updated["last_run"] is not None
        assert updated["last_status"] == "completed"

    async def test_disabled_never_runs(self, tmp_data):
        s = RoutineStore()
        r = s.create("off", "hello there", "every_5m")
        s.set_enabled(r["id"], False)
        calls = []

        async def spy(prompt):
            calls.append(prompt)
            yield {"type": "content_chunk", "chunk": "x"}

        outcomes = await run_due_routines(now=NOW, executor=spy, store=s)
        assert outcomes == []
        assert calls == []
        assert s.get(r["id"])["last_run"] is None

    async def test_not_due_does_not_run(self, tmp_data):
        s = RoutineStore()
        r = s.create("later", "hello there", "daily_09:30")
        s.record_run(r["id"], "completed", run_at=NOW.replace(hour=10).isoformat())
        calls = []

        async def spy(prompt):
            calls.append(prompt)
            yield {"type": "content_chunk", "chunk": "x"}

        assert await run_due_routines(now=NOW, executor=spy, store=s) == []
        assert calls == []

    async def test_yellow_gate_still_pends_no_bypass(self, tmp_data):
        """A mutating routine pauses as pending_approval — scheduler never approves."""
        from app.gates.approval_manager import ApprovalManager

        s = RoutineStore()
        r = s.create("risky", "publish the release notes", "every_5m")
        outcomes = await run_due_routines(now=NOW, executor=_yellow_executor, store=s)
        assert outcomes[0]["status"] == "pending_approval"
        assert s.get(r["id"])["last_status"] == "pending_approval"
        # The gate must still be pending — nothing auto-approved it.
        pending = ApprovalManager(data_dir=str(tmp_data)).get_pending_approvals()
        assert pending == []  # mock executor emits no real gate; see next test for ledger

    async def test_real_mutation_pauses_in_ledger(self, tmp_data):
        """End-to-end: real execute_task on a mutation prompt pends, never executes."""
        from app.orchestrator.chief_of_staff import chief_of_staff

        s = RoutineStore()
        r = s.create("ship", "send email to the team about the launch", "every_5m")
        outcomes = await run_due_routines(
            now=NOW, executor=chief_of_staff.execute_task, store=s
        )
        assert outcomes[0]["status"] == "pending_approval"
        from app.gates.approval_manager import ApprovalManager

        pending = ApprovalManager(data_dir=str(tmp_data)).get_pending_approvals()
        assert len(pending) >= 1  # ledger holds it; no auto-approve bypass

    async def test_executor_error_recorded_never_fabricated(self, tmp_data):
        s = RoutineStore()
        r = s.create("boom", "hello there", "every_5m")

        async def bad(prompt):
            raise RuntimeError("model down")
            yield  # pragma: no cover

        outcomes = await run_due_routines(now=NOW, executor=bad, store=s)
        assert outcomes[0]["status"] == "error"
        assert s.get(r["id"])["last_status"] == "error"


class TestRoutineAPI:
    def test_auth_required(self, client):
        assert client.get("/api/routines").status_code == 401
        assert client.post("/api/routines", json={}).status_code == 401

    def test_crud_cycle(self, client):
        created = client.post(
            "/api/routines",
            headers=AUTH,
            json={"name": "standup", "prompt": "summarize inbox", "cron": "daily_09:00"},
        )
        assert created.status_code == 200
        rid = created.json()["routine"]["id"]

        listed = client.get("/api/routines", headers=AUTH).json()["routines"]
        assert any(r["id"] == rid for r in listed)

        patched = client.patch(
            f"/api/routines/{rid}", headers=AUTH, json={"enabled": False}
        )
        assert patched.status_code == 200
        assert patched.json()["routine"]["enabled"] is False

        deleted = client.delete(f"/api/routines/{rid}", headers=AUTH)
        assert deleted.status_code == 200
        assert client.get("/api/routines", headers=AUTH).json()["routines"] == []

    def test_create_rejects_bad_cron(self, client):
        res = client.post(
            "/api/routines",
            headers=AUTH,
            json={"name": "x", "prompt": "y", "cron": "hourly"},
        )
        assert res.status_code == 400

    def test_missing_routine_404(self, client):
        assert client.patch("/api/routines/nope", headers=AUTH, json={"enabled": True}).status_code == 404
        assert client.delete("/api/routines/nope", headers=AUTH).status_code == 404


class TestSettingsKeysAPI:
    def test_auth_required(self, client):
        assert client.get("/api/settings/keys").status_code == 401
        assert client.post("/api/settings/keys", json={}).status_code == 401

    def test_save_and_list_without_echo(self, client):
        res = client.post(
            "/api/settings/keys", headers=AUTH, json={"name": "primary", "key": "sk-api-test"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert "sk-api-test" not in res.text

        listed = client.get("/api/settings/keys", headers=AUTH).json()["keys"]
        entry = next(k for k in listed if k["name"] == "primary")
        assert entry == {"name": "primary", "configured": True}
        assert "sk-api-test" not in res.text and "sk-api-test" not in str(listed)

    def test_blank_preserves_via_api(self, client):
        client.post("/api/settings/keys", headers=AUTH, json={"name": "ydc", "key": "ydc-secret"})
        res = client.post("/api/settings/keys", headers=AUTH, json={"name": "ydc", "key": ""})
        assert res.json()["configured"] is True
        listed = client.get("/api/settings/keys", headers=AUTH).json()["keys"]
        assert next(k for k in listed if k["name"] == "ydc")["configured"] is True

    def test_unknown_provider_400(self, client):
        res = client.post("/api/settings/keys", headers=AUTH, json={"name": "nope", "key": "x"})
        assert res.status_code == 400
