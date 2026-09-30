"""Encrypted credential store (P5).

Provider API keys can be supplied in two ways, resolved in this order:

    env var  >  encrypted file store  >  ""

``APP_ENCRYPTION_KEY`` (a Fernet key) comes from the environment when set;
otherwise a key is generated once and kept at ``DATA_DIR/.encryption_key``
(``chmod 600``). Encrypted provider keys live in ``DATA_DIR/.provider_keys.json``
(``chmod 600``), one Fernet token per provider name.

Plaintext keys are never logged and never echoed back through the API —
errors and status responses reference provider *names* only.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Canonical provider name -> env vars checked in order (first non-empty wins).
PROVIDER_ENV_VARS: Dict[str, tuple] = {
    "primary": ("PRIMARY_MODEL_API_KEY",),
    "worker": ("WORKER_MODEL_API_KEY", "PRIMARY_MODEL_API_KEY"),
    "fallback": ("FALLBACK_MODEL_API_KEY",),
    "ydc": ("YDC_API_KEY", "MCP_SEARCH_API_KEY"),
    "github": ("GITHUB_TOKEN",),
}

# Aliases accepted by save/get so callers can use env-style names.
_NAME_ALIASES: Dict[str, str] = {
    "primary_model_api_key": "primary",
    "worker_model_api_key": "worker",
    "fallback_model_api_key": "fallback",
    "ydc_api_key": "ydc",
    "mcp_search_api_key": "ydc",
    "github_token": "github",
}

KNOWN_PROVIDERS = tuple(PROVIDER_ENV_VARS.keys())

_KEY_FILENAME = ".encryption_key"
_STORE_FILENAME = ".provider_keys.json"


def normalize_name(name: str) -> str:
    """Canonicalize a provider name or raise ValueError (never echoes secrets)."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("Provider name is required.")
    canonical = _NAME_ALIASES.get(key, key)
    if canonical not in PROVIDER_ENV_VARS:
        raise ValueError(
            f"Unknown provider '{key}'. Known providers: {', '.join(KNOWN_PROVIDERS)}."
        )
    return canonical


def _data_dir() -> Path:
    """Resolve DATA_DIR dynamically so tests can isolate via settings."""
    try:
        from ..config import settings

        d = Path(settings.data_dir)
    except Exception:
        d = Path(os.getenv("DATA_DIR", "/opt/data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key_path() -> Path:
    return _data_dir() / _KEY_FILENAME


def _store_path() -> Path:
    return _data_dir() / _STORE_FILENAME


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        logger.warning("Could not chmod 600 on credential file %s", path.name)


def _load_or_create_raw_key() -> bytes:
    """Return the raw Fernet key bytes from env or the key file (creating it)."""
    env_key = (os.getenv("APP_ENCRYPTION_KEY", "") or "").strip()
    if env_key:
        try:
            Fernet(env_key.encode())
        except Exception:
            raise ValueError("APP_ENCRYPTION_KEY is set but is not a valid Fernet key.")
        return env_key.encode()
    path = _key_path()
    if path.exists():
        raw = path.read_bytes().strip()
        try:
            Fernet(raw)
        except Exception:
            raise ValueError("Stored encryption key is corrupt; refusing to proceed.")
        _chmod_private(path)
        return raw
    raw = Fernet.generate_key()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    _chmod_private(path)
    logger.info("Generated new app encryption key at %s", path.name)
    return raw


def _fernet() -> Fernet:
    return Fernet(_load_or_create_raw_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext secret. Errors never include the plaintext."""
    if not (plaintext or "").strip():
        raise ValueError("Cannot encrypt an empty value.")
    try:
        return _fernet().encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.error("Credential encryption failed: %s", type(e).__name__)
        raise ValueError("Credential encryption failed.")


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token. Errors never include the token or plaintext."""
    if not (token or "").strip():
        raise ValueError("Cannot decrypt an empty value.")
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning("Credential decryption failed: invalid token or wrong key.")
        raise ValueError("Credential decryption failed: invalid token or wrong key.")
    except Exception as e:
        logger.error("Credential decryption failed: %s", type(e).__name__)
        raise ValueError("Credential decryption failed.")


def _load_store() -> Dict[str, str]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Credential store unreadable (%s); treating as empty.", type(e).__name__)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _save_store(data: Dict[str, str]) -> None:
    path = _store_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
    _chmod_private(path)


def save_provider_key(name: str, key: str) -> Dict[str, object]:
    """Store ``key`` for provider ``name`` (encrypted at rest).

    A blank/empty ``key`` preserves the existing stored value (no-op) so
    settings forms can submit without wiping secrets. Returns a status dict
    that never contains the key itself.
    """
    canonical = normalize_name(name)
    if not (key or "").strip():
        # Blank preserves whatever is already stored.
        return {"name": canonical, "configured": is_configured(canonical)}
    token = encrypt_value(key.strip())
    data = _load_store()
    data[canonical] = token
    _save_store(data)
    logger.info("Stored encrypted credential for provider '%s'.", canonical)
    return {"name": canonical, "configured": True}


def get_provider_key(name: str) -> str:
    """Resolve a provider key: env var > encrypted store > "".

    Never raises on store/decrypt problems — fails closed to "".
    """
    try:
        canonical = normalize_name(name)
    except ValueError:
        return ""
    for env_var in PROVIDER_ENV_VARS[canonical]:
        val = (os.getenv(env_var, "") or "").strip()
        if val:
            return val
    token = _load_store().get(canonical, "")
    if not token:
        return ""
    try:
        return decrypt_value(token)
    except ValueError:
        return ""


def is_configured(name: str) -> bool:
    """True when the provider resolves to a non-empty key (env or store)."""
    return bool(get_provider_key(name))


def list_provider_status() -> List[Dict[str, object]]:
    """Status for every known provider — names + configured bool, no secrets."""
    return [{"name": n, "configured": is_configured(n)} for n in KNOWN_PROVIDERS]
