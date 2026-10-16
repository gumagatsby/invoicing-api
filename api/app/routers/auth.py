import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import security
from ..config import settings
from ..db import get_session
from ..deps import current_user
from ..models import RefreshToken, User
from ..schemas import Refresh, Register, Tokens, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue(session: AsyncSession, user: User, family: uuid.UUID | None = None) -> Tokens:
    jti, family = uuid.uuid4(), family or uuid.uuid4()
    session.add(RefreshToken(id=jti, user_id=user.id, family=family,
                             expires_at=datetime.now(UTC) + timedelta(days=settings().refresh_token_days)))
    return Tokens(access_token=security.access_token(user.id, user.role.value),
                  refresh_token=security.refresh_token(user.id, jti, family),
                  expires_in=settings().access_token_minutes * 60)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: Register, session: AsyncSession = Depends(get_session)):
    user = User(email=body.email.lower(), password_hash=security.hash_password(body.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return user


@router.post("/token", response_model=Tokens)
async def login(form: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == form.username.lower()))).scalar_one_or_none()
    if not security.verify_password(form.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    tokens = await _issue(session, user)
    await session.commit()
    return tokens


@router.post("/refresh", response_model=Tokens)
async def refresh(body: Refresh, session: AsyncSession = Depends(get_session)):
    """Refresh tokens rotate: each works once. Presenting a used one means it was stolen, so the
    whole family (every token descended from that login) is revoked."""
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    try:
        claims = security.decode(body.refresh_token, "refresh")
        jti = uuid.UUID(claims["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise invalid
    row = await session.get(RefreshToken, jti, with_for_update=True)
    if row is None or row.revoked_at is not None:
        raise invalid
    now = datetime.now(UTC)
    if row.used_at is not None:
        await session.execute(update(RefreshToken).where(RefreshToken.family == row.family).values(revoked_at=now))
        await session.commit()
        raise invalid
    row.used_at = now
    user = await session.get(User, row.user_id)
    tokens = await _issue(session, user, row.family)
    await session.commit()
    return tokens


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user
