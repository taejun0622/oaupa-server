"""Tests for audit logging: service unit tests and integration via auth endpoints."""

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_service import log_action


# ── Unit tests for audit_service.log_action ──────────────────────────────────


@pytest.mark.asyncio
class TestLogAction:
    async def test_creates_audit_log_entry(self, db: AsyncSession, test_user: User):
        """log_action inserts exactly one row into audit_logs."""
        await log_action(
            db,
            "test.action",
            user_id=test_user.id,
            resource_type="user",
            resource_id=test_user.id,
            ip_address="127.0.0.1",
        )

        rows = (await db.execute(sa.select(AuditLog).where(AuditLog.action == "test.action"))).scalars().all()
        assert len(rows) == 1
        entry = rows[0]
        assert entry.action == "test.action"
        assert entry.user_id == test_user.id
        assert entry.resource_type == "user"
        assert entry.resource_id == test_user.id
        assert str(entry.ip_address) == "127.0.0.1"

    async def test_stores_ip_address(self, db: AsyncSession, test_user: User):
        """ip_address is persisted correctly."""
        await log_action(
            db,
            "test.ip",
            user_id=test_user.id,
            ip_address="192.168.1.42",
        )

        row = (
            await db.execute(sa.select(AuditLog).where(AuditLog.action == "test.ip"))
        ).scalar_one()
        assert str(row.ip_address) == "192.168.1.42"

    async def test_stores_metadata(self, db: AsyncSession, test_user: User):
        """metadata dict is persisted in the JSONB column."""
        await log_action(
            db,
            "test.meta",
            user_id=test_user.id,
            metadata={"key": "value", "count": 3},
        )

        row = (
            await db.execute(sa.select(AuditLog).where(AuditLog.action == "test.meta"))
        ).scalar_one()
        assert row.metadata_["key"] == "value"
        assert row.metadata_["count"] == 3

    async def test_no_user_id_allowed(self, db: AsyncSession):
        """user_id is optional; system-level events can be recorded without it."""
        await log_action(db, "system.event", ip_address="10.0.0.1")

        row = (
            await db.execute(sa.select(AuditLog).where(AuditLog.action == "system.event"))
        ).scalar_one()
        assert row.user_id is None
        assert row.action == "system.event"

    async def test_empty_metadata_default(self, db: AsyncSession, test_user: User):
        """Omitting metadata stores an empty dict, not None."""
        await log_action(db, "test.nometa", user_id=test_user.id)

        row = (
            await db.execute(sa.select(AuditLog).where(AuditLog.action == "test.nometa"))
        ).scalar_one()
        assert row.metadata_ == {}

    async def test_user_agent_stored(self, db: AsyncSession, test_user: User):
        """user_agent string is persisted."""
        ua = "Mozilla/5.0 (Test)"
        await log_action(db, "test.ua", user_id=test_user.id, user_agent=ua)

        row = (
            await db.execute(sa.select(AuditLog).where(AuditLog.action == "test.ua"))
        ).scalar_one()
        assert row.user_agent == ua

    async def test_project_id_stored(self, db: AsyncSession, test_user: User, test_project):
        """project_id FK is persisted when provided."""
        await log_action(
            db,
            "test.project_action",
            user_id=test_user.id,
            project_id=test_project.id,
        )

        row = (
            await db.execute(
                sa.select(AuditLog).where(AuditLog.action == "test.project_action")
            )
        ).scalar_one()
        assert row.project_id == test_project.id


# ── Integration tests: audit logs created through auth HTTP endpoints ─────────


@pytest.mark.asyncio
class TestAuditLogViaAuthEndpoints:
    async def test_register_creates_audit_log(self, client: AsyncClient, db: AsyncSession):
        """POST /register writes a user.registered audit log row."""
        email = f"audit-reg-{uuid.uuid4().hex[:8]}@test.com"
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123", "full_name": "Audit User"},
        )
        assert resp.status_code == 201
        user_id = uuid.UUID(resp.json()["id"])

        rows = (
            await db.execute(
                sa.select(AuditLog).where(AuditLog.action == "user.registered")
            )
        ).scalars().all()
        # Find the row for this specific user (multiple tests may have registered)
        matching = [r for r in rows if r.user_id == user_id]
        assert len(matching) == 1
        entry = matching[0]
        assert entry.user_id == user_id
        assert entry.resource_type == "user"
        assert entry.resource_id == user_id

    async def test_login_creates_audit_log(self, client: AsyncClient, db: AsyncSession):
        """POST /login writes a user.login audit log row after successful auth."""
        email = f"audit-login-{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        assert reg_resp.status_code == 201
        user_id = uuid.UUID(reg_resp.json()["id"])

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepass123"},
        )
        assert login_resp.status_code == 200

        rows = (
            await db.execute(
                sa.select(AuditLog).where(AuditLog.action == "user.login")
            )
        ).scalars().all()
        matching = [r for r in rows if r.user_id == user_id]
        assert len(matching) == 1
        entry = matching[0]
        assert entry.user_id == user_id
        assert entry.resource_type == "user"
        assert entry.resource_id == user_id

    async def test_login_audit_log_has_ip_address(self, client: AsyncClient, db: AsyncSession):
        """The login audit log entry has an ip_address field set."""
        email = f"audit-ip-{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        user_id = uuid.UUID(reg_resp.json()["id"])

        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepass123"},
        )

        row = (
            await db.execute(
                sa.select(AuditLog).where(
                    AuditLog.action == "user.login",
                    AuditLog.user_id == user_id,
                )
            )
        ).scalar_one()
        # In tests the ASGI test client reports "testclient" as host; the field
        # must not be None regardless of the exact value.
        assert row.ip_address is not None

    async def test_register_audit_log_has_ip_address(self, client: AsyncClient, db: AsyncSession):
        """The register audit log entry has an ip_address field set."""
        email = f"audit-regip-{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        user_id = uuid.UUID(reg_resp.json()["id"])

        row = (
            await db.execute(
                sa.select(AuditLog).where(
                    AuditLog.action == "user.registered",
                    AuditLog.user_id == user_id,
                )
            )
        ).scalar_one()
        assert row.ip_address is not None

    async def test_failed_login_does_not_create_audit_log(
        self, client: AsyncClient, db: AsyncSession
    ):
        """A failed login attempt must NOT produce a user.login audit entry."""
        email = f"audit-fail-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correct123"},
        )

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

        # Fetch all user.login rows and ensure none belong to a user with this
        # email by cross-referencing user table.
        from app.models.user import User as UserModel

        user_row = (
            await db.execute(sa.select(UserModel).where(UserModel.email == email))
        ).scalar_one()
        login_rows = (
            await db.execute(
                sa.select(AuditLog).where(
                    AuditLog.action == "user.login",
                    AuditLog.user_id == user_row.id,
                )
            )
        ).scalars().all()
        assert login_rows == []
