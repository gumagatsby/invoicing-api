import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import rate_limited
from ..models import User, WebhookDelivery, WebhookEndpoint
from ..schemas import DeliveryOut, WebhookIn, WebhookOut
from ..services.webhooks import allowed_url_host, new_secret

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookOut, status_code=201)
async def create(body: WebhookIn, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    if not allowed_url_host(body.url.host or ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The webhook URL must point at a public address")
    ep = WebhookEndpoint(owner_id=user.id, url=str(body.url), secret=new_secret())
    session.add(ep)
    await session.commit()
    return WebhookOut(id=ep.id, url=ep.url, active=ep.active, secret=ep.secret)  # the only time the secret is shown


@router.get("", response_model=list[WebhookOut])
async def list_(user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    eps = (await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.owner_id == user.id))).scalars().all()
    return [WebhookOut(id=e.id, url=e.url, active=e.active) for e in eps]


@router.get("/{endpoint_id}/deliveries", response_model=list[DeliveryOut])
async def deliveries(endpoint_id: uuid.UUID, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    ep = await session.get(WebhookEndpoint, endpoint_id)
    if ep is None or ep.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook endpoint not found")
    return (await session.execute(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
                                  .order_by(WebhookDelivery.created_at.desc()).limit(100))).scalars().all()
