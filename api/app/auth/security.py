"""Password hashing (argon2) and JWT access tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

# pwdlib's recommended hasher is argon2id.
_password_hash = PasswordHash.recommended()

# Used when a login email does not exist, so the response takes about as long as a real check.
_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class TokenData:
    user_id: UUID
    store_id: UUID


def create_access_token(user_id: UUID, store_id: UUID) -> tuple[str, int]:
    """Return (token, expires_in_seconds). The store_id is baked into the signed token."""
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "store_id": str(store_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> TokenData | None:
    """Return the token's data, or None if it is invalid, expired, or tampered with."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "store_id", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            return None
        return TokenData(user_id=UUID(payload["sub"]), store_id=UUID(payload["store_id"]))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
