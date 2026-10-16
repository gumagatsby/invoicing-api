import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

_hasher = PasswordHasher()
ISSUER = "invoicing-api"
# A fixed hash, verified when the email is unknown, so a failed login takes the same time either way.
_DUMMY = _hasher.hash("timing-equaliser-not-a-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _hasher.verify(hashed or _DUMMY, password) and hashed is not None
    except VerifyMismatchError:
        return False


def _encode(claims: dict, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode({**claims, "iss": ISSUER, "iat": now, "exp": now + ttl}, settings().jwt_secret, algorithm="HS256")


def access_token(user_id: uuid.UUID, role: str) -> str:
    return _encode({"sub": str(user_id), "role": role, "typ": "access"}, timedelta(minutes=settings().access_token_minutes))


def refresh_token(user_id: uuid.UUID, jti: uuid.UUID, family: uuid.UUID) -> str:
    return _encode({"sub": str(user_id), "jti": str(jti), "fam": str(family), "typ": "refresh"},
                   timedelta(days=settings().refresh_token_days))


def decode(token: str, typ: str) -> dict:
    claims = jwt.decode(token, settings().jwt_secret, algorithms=["HS256"], issuer=ISSUER,
                        options={"require": ["exp", "iat", "sub", "typ"]})
    if claims["typ"] != typ:
        raise jwt.InvalidTokenError("wrong token type")
    return claims
