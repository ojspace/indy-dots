"""
Authentication & boot-safety for the Indy-Dots gateway.

Every operator-facing route requires `Authorization: Bearer <AUTH_TOKEN>`.
Only /health is exempt. In production the server refuses to boot with the
default dev token so an unauthenticated control plane can never ship.
"""
from fastapi import Header, HTTPException, status
import hmac

from .config import settings

_DEV_DEFAULT_TOKEN = "default-dev-secret-token"


def enforce_production_token_safety() -> None:
    """
    Refuse to boot in production when AUTH_TOKEN is missing or left at the
    insecure default. Called once at app startup.
    """
    if settings.environment != "production":
        return
    token = settings.auth_token.strip()
    if not token or token == _DEV_DEFAULT_TOKEN or len(token) < 32:
        raise RuntimeError(
            "Refusing to start: ENVIRONMENT=production requires a secure "
            "AUTH_TOKEN (min 32 chars, not the default). Set it in .env."
        )


async def require_auth(
    authorization: str = Header(default=""),
) -> None:
    """FastAPI dependency: validate the Bearer token against settings.auth_token."""
    expected = settings.auth_token.strip()
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Constant-time compare to avoid timing leaks on prefix matching.
    if not hmac.compare_digest(credentials.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
