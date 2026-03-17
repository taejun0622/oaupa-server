from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health():
    return {"status": "ok"}


@health_router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
