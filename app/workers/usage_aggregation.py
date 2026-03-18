"""Daily usage aggregation worker."""

import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.usage import UsageRecord
from app.workers.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.workers.usage_aggregation.aggregate_daily_usage")
def aggregate_daily_usage():
    _run_async(_aggregate_daily_usage())


async def _aggregate_daily_usage():
    today = date.today()

    session_factory = _make_session_factory()
    async with session_factory() as session:
        # Get all active projects
        result = await session.execute(
            select(Project.id).where(Project.is_active.is_(True))
        )
        project_ids = [row[0] for row in result.all()]

        for project_id in project_ids:
            # Count active connections
            conn_count = await session.scalar(
                select(func.count()).select_from(OAuthConnection).where(
                    OAuthConnection.project_id == project_id,
                    OAuthConnection.status == "active",
                )
            )

            # Upsert usage record
            result = await session.execute(
                select(UsageRecord).where(
                    UsageRecord.project_id == project_id,
                    UsageRecord.period_start == today,
                )
            )
            usage = result.scalar_one_or_none()

            if usage is None:
                usage = UsageRecord(
                    project_id=project_id,
                    period_start=today,
                    connections_count=conn_count or 0,
                )
                session.add(usage)
            else:
                usage.connections_count = conn_count or 0

        await session.commit()
