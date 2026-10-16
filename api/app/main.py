import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from . import telemetry
from .config import settings
from .db import engine
from .deps import redis
from .metrics import REQUESTS
from .routers import auth, billing, webhooks

app = FastAPI(title="Invoicing API", version="1.0.0",
              description="Invoices, idempotent payments, a double-entry ledger and signed webhooks.")
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Idempotent-Replayed", "Retry-After"])
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(webhooks.router)
telemetry.setup(app)


@app.middleware("http")
async def timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    # The route template (/invoices/{invoice_id}), not the raw path, so metrics stay low-cardinality.
    REQUESTS.labels(request.method, getattr(route, "path", "unmatched"), response.status_code).observe(time.perf_counter() - start)
    return response


@app.get("/health", tags=["ops"])
async def health():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis().ping()
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
