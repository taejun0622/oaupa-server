from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.api.v1.router import api_v1_router
from app.api.health import health_router
from app.core.rate_limit import limiter

import app.models  # noqa: F401 — ensure all models are registered with SQLAlchemy


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    yield
    # Shutdown
    from app.db.session import engine

    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title="oaupa",
        description="OAuth infrastructure platform for managing SaaS API tokens",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Rate limiting
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.include_router(health_router)
    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_app()
