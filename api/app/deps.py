import time
import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from . import security
from .config import settings
from .db import SessionLocal
from .models import Role, User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")
_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings().redis_url, decode_responses=True)
    return _redis


async def current_user(token: str = Depends(oauth2)) -> User:
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                                 headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = security.decode(token, "access")
        # Own short session, so the route's session starts with no transaction open.
        async with SessionLocal() as session:
            user = await session.get(User, uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorised
    if user is None:
        raise unauthorised
    return user


async def rate_limited(request: Request, user: User = Depends(current_user)) -> User:
    """Fixed one-minute window per user, counted in Redis so it holds across API replicas."""
    window = int(time.time() // 60)
    key = f"rl:{user.id}:{window}"
    r = redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 70)
    limit = settings().rate_limit_per_minute
    request.state.rate_remaining = max(0, limit - count)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded",
                            headers={"Retry-After": str(60 - int(time.time()) % 60)})
    return user


async def admin(user: User = Depends(rate_limited)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user
