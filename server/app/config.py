import os
from pydantic import BaseModel
from typing import Optional

def _resolve_data_dir() -> str:
    env_dir = os.getenv("DATA_DIR")
    if env_dir:
        return env_dir
    default_dir = "/opt/data"
    try:
        os.makedirs(default_dir, exist_ok=True)
        return default_dir
    except (PermissionError, OSError):
        local_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
        os.makedirs(local_dir, exist_ok=True)
        return local_dir

_default_data_dir = _resolve_data_dir()

class Settings(BaseModel):
    environment: str = os.getenv("ENVIRONMENT", "development")
    auth_token: str = os.getenv("AUTH_TOKEN", "default-dev-secret-token")
    data_dir: str = os.getenv("DATA_DIR", _default_data_dir)
    vault_dir: str = os.getenv("OBSIDIAN_VAULT_DIR", os.path.join(_default_data_dir, "vault"))
    
    # Model Configurations
    primary_provider: str = os.getenv("PRIMARY_MODEL_PROVIDER", "openrouter")
    primary_model: str = os.getenv("PRIMARY_MODEL", "anthropic/claude-3.7-sonnet")
    primary_api_key: str = os.getenv("PRIMARY_MODEL_API_KEY", "")
    primary_base_url: str = os.getenv("PRIMARY_MODEL_BASE_URL", "https://openrouter.ai/api/v1")
    
    worker_provider: str = os.getenv("WORKER_MODEL_PROVIDER", "openrouter")
    worker_model: str = os.getenv("WORKER_MODEL", "deepseek/deepseek-chat")
    worker_api_key: str = os.getenv("WORKER_MODEL_API_KEY", "") or os.getenv("PRIMARY_MODEL_API_KEY", "")
    worker_base_url: str = os.getenv("WORKER_MODEL_BASE_URL", "https://openrouter.ai/api/v1")
    
    # Governance & Token Discipline
    max_turns: int = int(os.getenv("MAX_TURNS_PER_TASK", "20"))
    verification_max_passes: int = int(os.getenv("VERIFICATION_GATE_MAX_PASSES", "1"))
    approvals_mode: str = os.getenv("APPROVALS_MODE", "manual")

settings = Settings()
