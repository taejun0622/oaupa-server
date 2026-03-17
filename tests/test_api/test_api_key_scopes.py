"""Test plan: API key scope enforcement.

Tests that API key scopes restrict access to only authorized operations.
require_scope(scope) is implemented in app/api/deps.py and enforced on
token endpoints via Depends(require_scope("tokens:read")).

Expected scopes: tokens:read, tokens:write, connections:read, connections:write,
                 webhooks:read, webhooks:write
Expected behavior:
  - API key with tokens:read can GET tokens
  - API key with no matching scope gets 403
  - API key with multiple scopes including tokens:read works
  - Expired API keys get 401
  - Revoked API keys get 401
  - last_used_at is updated on successful API key use
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.token_vault import TokenVault
from app.models.user import User


# ─── Helper ────────────────────────────────────────────────────────────────────


def _make_api_key(project: Project, scopes: list[str], **kwargs) -> tuple[ApiKey, str]:
    """Return an (ApiKey ORM object, raw key string) pair — NOT yet added to the session."""
    full_key = f"oau_live_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    api_key = ApiKey(
        project_id=project.id,
        name=f"Key-{uuid.uuid4().hex[:6]}",
        key_prefix=full_key[:12],
        key_hash=key_hash,
        scopes=scopes,
        **kwargs,
    )
    return api_key, full_key


# ─── Expiration / revocation (already working) ─────────────────────────────────


@pytest.mark.asyncio
class TestAPIKeyExpiration:
    """Tests for expiration and revocation — pass without scope enforcement."""

    async def test_expired_key_returns_401(
        self, client: AsyncClient, db: AsyncSession, test_project: Project
    ):
        """API key past its expires_at should be rejected with 401."""
        api_key, full_key = _make_api_key(
            test_project,
            scopes=["tokens:read"],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        assert resp.status_code == 401

    async def test_non_expired_key_works(
        self, client: AsyncClient, db: AsyncSession, test_project: Project
    ):
        """API key with a future expires_at should pass authentication."""
        api_key, full_key = _make_api_key(
            test_project,
            scopes=["tokens:read"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        # Auth passes; token may not exist so 404 is expected — but never 401
        assert resp.status_code != 401

    async def test_revoked_key_returns_401(
        self, client: AsyncClient, db: AsyncSession, test_project: Project
    ):
        """Revoked (is_active=False) API key should be rejected with 401."""
        api_key, full_key = _make_api_key(
            test_project,
            scopes=["tokens:read"],
            is_active=False,
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        assert resp.status_code == 401

    async def test_last_used_at_updated(
        self, client: AsyncClient, db: AsyncSession, test_project: Project
    ):
        """Successful API key use must update last_used_at in the database."""
        api_key, full_key = _make_api_key(test_project, scopes=["tokens:read"])
        db.add(api_key)
        await db.flush()

        assert api_key.last_used_at is None

        await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )

        await db.refresh(api_key)
        assert api_key.last_used_at is not None


# ─── Scope enforcement ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAPIKeyScopeEnforcement:
    """Tests for require_scope() enforcement on token endpoints."""

    async def test_tokens_read_scope_allows_token_retrieval(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        """Key with tokens:read scope can reach token endpoints (auth passes)."""
        api_key, full_key = _make_api_key(test_project, scopes=["tokens:read"])
        db.add(api_key)
        await db.flush()

        # GET /tokens?provider=... — scope enforced
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": test_connection.provider_id},
        )
        # Auth and scope check pass; response may be 200 or a business-logic
        # error, but must not be 401 (auth) or 403 (scope).
        assert resp.status_code not in (401, 403), resp.text

        # GET /tokens/{connection_id} — same scope gate
        resp2 = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens/{test_connection.id}",
            headers={"X-API-Key": full_key},
        )
        assert resp2.status_code not in (401, 403), resp2.text

    async def test_missing_scope_returns_403(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_project: Project,
    ):
        """API key without any scope gets 403 Forbidden on a scope-guarded endpoint."""
        api_key, full_key = _make_api_key(test_project, scopes=[])
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        assert resp.status_code == 403, resp.text

    async def test_wrong_scope_returns_403(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_project: Project,
    ):
        """API key with a different scope (e.g. connections:read) gets 403 on tokens endpoint."""
        api_key, full_key = _make_api_key(
            test_project, scopes=["connections:read", "webhooks:read"]
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        assert resp.status_code == 403, resp.text

    async def test_multiple_scopes_including_tokens_read_works(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        """Key carrying multiple scopes that include tokens:read can access token endpoints."""
        api_key, full_key = _make_api_key(
            test_project,
            scopes=["connections:read", "tokens:read", "webhooks:read"],
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": test_connection.provider_id},
        )
        assert resp.status_code not in (401, 403), resp.text

    async def test_tokens_read_scope_blocks_wrong_project(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_user: User,
        test_project: Project,
    ):
        """API key for project A cannot retrieve tokens for project B (403 from endpoint guard)."""
        # Create a second project owned by the same user
        other_project = Project(
            user_id=test_user.id,
            name="Other Project",
            slug=f"other-{uuid.uuid4().hex[:8]}",
        )
        db.add(other_project)
        await db.flush()

        # Key is issued for other_project
        api_key, full_key = _make_api_key(other_project, scopes=["tokens:read"])
        db.add(api_key)
        await db.flush()

        # But we try to access test_project's tokens with the other project's key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            headers={"X-API-Key": full_key},
            params={"provider": "google"},
        )
        # resolve_api_key returns the other_project; the endpoint checks
        # project.id != project_id and raises ForbiddenError → 403
        assert resp.status_code == 403, resp.text
