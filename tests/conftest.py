import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://oaupa:oaupa@localhost:5432/oaupa_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OAUPA_MASTER_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")  # 32-byte test key
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# ─── Test isolation fixtures ───


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi rate limiter storage before each test to prevent 429 bleed-over."""
    from app.core.rate_limit import limiter

    limiter.reset()
    yield


@pytest.fixture(autouse=True)
def reset_login_lockout_redis():
    """Reset the login lockout Redis singleton before each test.

    The module-level ``_redis`` client caches a connection bound to the event
    loop that was current when it was first created.  When pytest-asyncio
    creates a new event loop for each test the cached client becomes stale and
    any awaited call on it raises ``RuntimeError: Event loop is closed``.
    Setting it to ``None`` forces ``_get_redis()`` to create a fresh client on
    the new loop.
    """
    import app.core.login_lockout as login_lockout

    login_lockout._redis = None
    yield
    login_lockout._redis = None

from app.core.encryption import encrypt, get_current_key_version
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.oauth_connection import OAuthConnection
from app.models.oauth_provider import OAuthProvider
from app.models.oauth_state import OAuthState  # noqa: F401
from app.models.project import Project
from app.models.subscription import Subscription  # noqa: F401
from app.models.token_vault import TokenVault
from app.models.usage import UsageRecord  # noqa: F401
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery  # noqa: F401

TEST_DB_URL = os.environ["DATABASE_URL"]

# Track if tables have been created (across event loops using sync flag)
_tables_created = False  # reset on schema changes


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    global _tables_created
    engine = create_async_engine(TEST_DB_URL, echo=False)

    if not _tables_created:
        async with engine.begin() as conn:
            await conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(sa.text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ─── Helper fixtures ───


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("testpassword123"),
        full_name="Test User",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_superadmin(db: AsyncSession) -> User:
    user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("adminpassword123"),
        full_name="Admin User",
        is_superadmin=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(db: AsyncSession, test_user: User) -> Project:
    project = Project(
        user_id=test_user.id,
        name="Test Project",
        slug=f"test-project-{uuid.uuid4().hex[:8]}",
    )
    db.add(project)
    await db.flush()
    return project


@pytest_asyncio.fixture
async def test_api_key(db: AsyncSession, test_project: Project) -> tuple[ApiKey, str]:
    full_key = f"oau_live_test{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    api_key = ApiKey(
        project_id=test_project.id,
        name="Test Key",
        key_prefix=full_key[:12],
        key_hash=key_hash,
        scopes=["tokens:read"],
    )
    db.add(api_key)
    await db.flush()
    return api_key, full_key


@pytest_asyncio.fixture
async def test_provider(db: AsyncSession) -> OAuthProvider:
    provider_id = f"test-provider-{uuid.uuid4().hex[:8]}"
    provider = OAuthProvider(
        id=provider_id,
        display_name="Test Provider",
        auth_url="https://provider.example.com/auth",
        token_url="https://provider.example.com/token",
        revoke_url="https://provider.example.com/revoke",
        client_id="test-client-id",
        client_secret_encrypted=encrypt("test-client-secret"),
        default_scopes=["read", "write"],
        supports_refresh=True,
    )
    db.add(provider)
    await db.flush()
    return provider


@pytest_asyncio.fixture
async def test_connection(
    db: AsyncSession, test_project: Project, test_user: User, test_provider: OAuthProvider
) -> OAuthConnection:
    connection = OAuthConnection(
        project_id=test_project.id,
        user_id=test_user.id,
        provider_id=test_provider.id,
        provider_account_id="ext-account-123",
        provider_account_email="ext@example.com",
        scopes_granted=["read", "write"],
        status="active",
    )
    db.add(connection)
    await db.flush()
    return connection


@pytest_asyncio.fixture
async def test_token_vault(db: AsyncSession, test_connection: OAuthConnection) -> TokenVault:
    vault = TokenVault(
        connection_id=test_connection.id,
        access_token_encrypted=encrypt("test-access-token-12345"),
        refresh_token_encrypted=encrypt("test-refresh-token-12345"),
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        encryption_key_id=get_current_key_version(),
    )
    db.add(vault)
    await db.flush()
    return vault


@pytest_asyncio.fixture
async def test_webhook(db: AsyncSession, test_project: Project) -> Webhook:
    webhook = Webhook(
        project_id=test_project.id,
        url="https://webhook.example.com/callback",
        secret="test-webhook-secret-hex",
        events=["connection.created", "token.refreshed"],
    )
    db.add(webhook)
    await db.flush()
    return webhook


async def auth_headers(client: AsyncClient, email: str | None = None) -> dict[str, str]:
    """Register + login, return auth headers."""
    email = email or f"auth-{uuid.uuid4().hex[:8]}@test.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpassword123", "full_name": "Test"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpassword123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_project_via_api(client: AsyncClient, headers: dict) -> dict:
    slug = f"proj-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "slug": slug},
        headers=headers,
    )
    return resp.json()


async def create_api_key_via_api(client: AsyncClient, headers: dict, project_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "Test Key"},
        headers=headers,
    )
    return resp.json()
