from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sqlalchemy import text
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.exceptions import AppError
from app.logging import configure_logging, get_logger
from app.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.routers import admin, analysis, feedback, health, matches, predictions, signals, stats

configure_logging()
settings = get_settings()
logger = get_logger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration(), CeleryIntegration()],
        traces_sample_rate=0.05,
        environment=settings.environment,
    )


async def _wait_for_database() -> None:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            logger.info("Database connection ready on startup (attempt %s)", attempt)
            return
        except Exception as exc:  # pragma: no cover - exercised at runtime
            last_error = exc
            logger.warning("Database startup check failed on attempt %s/3: %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(5)
    raise RuntimeError(f"Database unavailable after 3 startup attempts: {last_error}") from last_error


async def _check_redis_startup() -> None:
    try:
        redis = Redis.from_url(settings.redis_url)
        await asyncio.to_thread(redis.ping)
        logger.info("Redis connection ready on startup")
    except Exception as exc:  # pragma: no cover - exercised at runtime
        logger.warning("Redis unavailable on startup; continuing in degraded mode: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _wait_for_database()
    await _check_redis_startup()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": RATE_LIMIT_MESSAGE})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


app.include_router(health.router)
app.include_router(matches.router, prefix=settings.api_prefix)
app.include_router(predictions.router, prefix=settings.api_prefix)
app.include_router(signals.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(stats.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(analysis.router, prefix=settings.api_prefix)
