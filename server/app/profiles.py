"""
profiles.py — Agent fleet loader.

Loads role profiles from profiles/*.yaml (supports multi-doc YAML like
workers_pack.yaml). Falls back to a built-in static fleet when the profiles
directory is missing or unreadable, so the gateway always reports a fleet.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import settings

_FALLBACK_FLEET: List[Dict[str, str]] = [
    {"name": "atlas", "role": "Chief of Staff", "tier": "primary"},
    {"name": "researcher", "role": "Deep Research", "tier": "worker"},
    {"name": "writer", "role": "Copy & Content", "tier": "worker"},
    {"name": "seo", "role": "Search Console", "tier": "worker"},
    {"name": "ops", "role": "Sprint Operations", "tier": "worker"},
    {"name": "coder", "role": "Software Engineer", "tier": "primary"},
]


def _profiles_dir() -> Path:
    env_dir = os.getenv("PROFILES_DIR")
    if env_dir:
        return Path(env_dir)
    # Repo checkout: <repo>/profiles. In Docker the compose file mounts the
    # profiles at /opt/data/profiles.
    repo_dir = Path(__file__).resolve().parent.parent.parent
    return repo_dir / "profiles"


def _model_for_tier(tier: str) -> str:
    return settings.primary_model if tier == "primary" else settings.worker_model


def _load_doc(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(doc, dict) or not doc.get("name"):
        return None
    tier = str(doc.get("model_preference", {}).get("tier", "worker"))
    return {
        "name": str(doc["name"]),
        "role": str(doc.get("role", "worker")).replace("_", " ").title(),
        "tier": tier,
        "model": _model_for_tier(tier),
        "description": str(doc.get("description", "")),
        "max_turns": int(doc.get("max_turns", 10)),
        "allowed_toolsets": list(doc.get("allowed_toolsets", [])),
        "disabled_toolsets": list(doc.get("disabled_toolsets", [])),
        "output_directory": str(doc.get("output_directory", "")),
    }


def load_profiles() -> List[Dict[str, Any]]:
    profiles_dir = _profiles_dir()
    fleet: List[Dict[str, Any]] = []
    if profiles_dir.is_dir():
        for yml in sorted(profiles_dir.glob("*.yaml")):
            try:
                docs = list(yaml.safe_load_all(yml.read_text(encoding="utf-8")))
            except Exception:
                continue
            for doc in docs:
                p = _load_doc(doc)
                if p:
                    fleet.append(p)
    if not fleet:
        fleet = [
            {**p, "model": _model_for_tier(p["tier"]), "description": "", "max_turns": 10,
             "allowed_toolsets": [], "disabled_toolsets": [], "output_directory": ""}
            for p in _FALLBACK_FLEET
        ]
    return fleet
