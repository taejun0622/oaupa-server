from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.usage import UsageRecord
from app.models.user import User


@pytest.mark.asyncio
class TestUsageAggregation:
    async def test_creates_usage_record(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
    ):
        # Manually simulate what the worker does
        from sqlalchemy import func

        conn_count = await db.scalar(
            select(func.count())
            .select_from(OAuthConnection)
            .where(
                OAuthConnection.project_id == test_project.id,
                OAuthConnection.status == "active",
            )
        )

        usage = UsageRecord(
            project_id=test_project.id,
            period_start=date.today(),
            connections_count=conn_count or 0,
        )
        db.add(usage)
        await db.flush()

        result = await db.execute(
            select(UsageRecord).where(
                UsageRecord.project_id == test_project.id,
                UsageRecord.period_start == date.today(),
            )
        )
        record = result.scalar_one()
        assert record.connections_count >= 1

    async def test_updates_existing_record(
        self,
        db: AsyncSession,
        test_project: Project,
    ):
        # Create initial record
        usage = UsageRecord(
            project_id=test_project.id,
            period_start=date(2025, 1, 1),
            connections_count=5,
            token_retrievals=100,
        )
        db.add(usage)
        await db.flush()

        # Update it
        usage.connections_count = 10
        await db.flush()

        result = await db.execute(
            select(UsageRecord).where(
                UsageRecord.project_id == test_project.id,
                UsageRecord.period_start == date(2025, 1, 1),
            )
        )
        record = result.scalar_one()
        assert record.connections_count == 10
