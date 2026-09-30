"""P5: encrypted credential store — roundtrip, env precedence, no plaintext leaks."""
import json
import logging
import os
import stat

import pytest

from app import config
from app.security import credential_store as store


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    monkeypatch.delenv("APP_ENCRYPTION_KEY", raising=False)
    for var in (
        "PRIMARY_MODEL_API_KEY",
        "WORKER_MODEL_API_KEY",
        "FALLBACK_MODEL_API_KEY",
        "YDC_API_KEY",
        "MCP_SEARCH_API_KEY",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


class TestRoundtrip:
    def test_save_and_get(self, isolated):
        res = store.save_provider_key("primary", "sk-test-123")
        assert res == {"name": "primary", "configured": True}
        assert store.get_provider_key("primary") == "sk-test-123"

    def test_store_file_has_no_plaintext(self, isolated):
        secret = "sk-super-secret-xyz-999"
        store.save_provider_key("worker", secret)
        raw = (isolated / ".provider_keys.json").read_text()
        assert secret not in raw
        # It is a Fernet token, not the raw key.
        data = json.loads(raw)
        assert data["worker"] != secret

    def test_unconfigured_returns_empty(self, isolated):
        assert store.get_provider_key("github") == ""
        assert store.is_configured("github") is False

    def test_alias_names_resolve(self, isolated):
        store.save_provider_key("github_token", "ghp_abc")
        assert store.get_provider_key("github") == "ghp_abc"

    def test_unknown_provider_rejected(self, isolated):
        with pytest.raises(ValueError):
            store.save_provider_key("nope", "x")

    def test_encrypt_decrypt_helpers(self, isolated):
        token = store.encrypt_value("hello")
        assert token != "hello"
        assert store.decrypt_value(token) == "hello"
        with pytest.raises(ValueError):
            store.decrypt_value("not-a-token")


class TestBlankPreserves:
    def test_blank_preserves_stored_value(self, isolated):
        store.save_provider_key("primary", "sk-original")
        res = store.save_provider_key("primary", "")
        assert res == {"name": "primary", "configured": True}
        assert store.get_provider_key("primary") == "sk-original"

    def test_whitespace_preserves_stored_value(self, isolated):
        store.save_provider_key("primary", "sk-original")
        store.save_provider_key("primary", "   ")
        assert store.get_provider_key("primary") == "sk-original"

    def test_blank_on_empty_store_stays_unconfigured(self, isolated):
        res = store.save_provider_key("ydc", "")
        assert res == {"name": "ydc", "configured": False}


class TestEnvOverridesStore:
    def test_env_wins_over_store(self, isolated, monkeypatch):
        store.save_provider_key("primary", "sk-from-store")
        monkeypatch.setenv("PRIMARY_MODEL_API_KEY", "sk-from-env")
        assert store.get_provider_key("primary") == "sk-from-env"

    def test_env_cleared_falls_back_to_store(self, isolated, monkeypatch):
        store.save_provider_key("primary", "sk-from-store")
        monkeypatch.setenv("PRIMARY_MODEL_API_KEY", "sk-from-env")
        assert store.get_provider_key("primary") == "sk-from-env"
        monkeypatch.delenv("PRIMARY_MODEL_API_KEY")
        assert store.get_provider_key("primary") == "sk-from-store"

    def test_worker_falls_back_to_primary_env(self, isolated, monkeypatch):
        monkeypatch.setenv("PRIMARY_MODEL_API_KEY", "sk-primary")
        assert store.get_provider_key("worker") == "sk-primary"


class TestNoPlaintextLeaks:
    def test_decrypt_failure_never_echoes_secret(self, isolated, caplog):
        secret = "sk-do-not-leak-12345"
        store.save_provider_key("primary", secret)
        # Corrupt the stored token; resolution must fail closed without logging it.
        path = isolated / ".provider_keys.json"
        path.write_text(json.dumps({"primary": "corrupted-token"}))
        with caplog.at_level(logging.WARNING, logger="app.security.credential_store"):
            assert store.get_provider_key("primary") == ""
        assert secret not in caplog.text
        assert "corrupted-token" not in caplog.text

    def test_error_paths_never_echo_key_material(self, isolated, caplog):
        with pytest.raises(ValueError) as exc:
            store.save_provider_key("", "sk-should-never-appear")
        assert "sk-should-never-appear" not in str(exc.value)

    def test_status_lists_names_only(self, isolated):
        store.save_provider_key("primary", "sk-hidden-value")
        statuses = store.list_provider_status()
        assert {"name": "primary", "configured": True} in statuses
        assert "sk-hidden-value" not in json.dumps(statuses)


class TestFilePermissions:
    def test_key_and_store_files_are_600(self, isolated):
        store.save_provider_key("primary", "sk-perm-check")
        for fname in (".encryption_key", ".provider_keys.json"):
            mode = stat.S_IMODE(os.stat(isolated / fname).st_mode)
            assert mode == 0o600, f"{fname} mode is {oct(mode)}, expected 0o600"

    def test_env_key_leaves_no_key_file(self, isolated, monkeypatch):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())
        store.save_provider_key("primary", "sk-env-key-mode")
        assert not (isolated / ".encryption_key").exists()
