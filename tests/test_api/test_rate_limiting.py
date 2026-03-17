"""Rate limiting enforcement tests.

Tests for slowapi rate limiting and login lockout across auth endpoints.

Covered:
  - Login brute-force lockout (5 failed attempts → account locked)
  - Lockout clears after a successful login
  - Registration rate limit (3/min — 4th request in a minute → 429)
  - Login rate limit (5/min — 6th request in a minute → 429)
  - Rate limit headers (X-RateLimit-Limit etc.) — currently disabled in the
    limiter config, so we only assert they are absent rather than present.
    If headers are ever enabled this test documents the expected header names.
"""

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.config import settings


# ---------------------------------------------------------------------------
# Module-level isolation: flush rate-limit and lockout Redis keys before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def flush_rate_limit_keys():
    """Flush all LIMITS:* and login_lockout:* keys from Redis before each test.

    The conftest reset_rate_limiter fixture uses the sync Redis client embedded
    in the slowapi storage.  In some async test configurations that client can
    be bound to the wrong event loop.  This async fixture uses the same
    redis.asyncio library used by login_lockout, ensuring the flush always
    executes on the correct event loop.
    """
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        keys = await r.keys("LIMITS:*")
        lockout_keys = await r.keys("login_lockout:*")
        all_keys = keys + lockout_keys
        if all_keys:
            await r.delete(*all_keys)
    finally:
        await r.aclose()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register(client: AsyncClient, email: str, password: str = "Password123!") -> int:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test"},
    )
    return resp.status_code


async def _login(client: AsyncClient, email: str, password: str = "Password123!") -> int:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp


# ---------------------------------------------------------------------------
# 1. Login brute-force lockout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoginLockout:
    async def test_five_failures_trigger_lockout(self, client: AsyncClient):
        """5 consecutive wrong passwords must lock the account out."""
        email = "lockout-victim@test.com"
        await _register(client, email)

        # 5 failed attempts — each should return 401 (not locked yet)
        for _ in range(5):
            resp = await _login(client, email, password="WrongPass!")
            assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

        # 6th attempt (correct password) must now be blocked with 429
        resp = await _login(client, email, password="Password123!")
        assert resp.status_code == 429, (
            f"Expected 429 after lockout, got {resp.status_code}: {resp.json()}"
        )

    async def test_lockout_message_mentions_retry(self, client: AsyncClient):
        """Lockout error message should tell the user when to retry.

        The lockout is triggered by the login_lockout module (RateLimitError) and
        fires *before* slowapi counts the request.  We therefore need an email that
        hasn't burned its own slowapi login budget.  We use the lockout module's
        public API directly to pre-populate the failure counter, then make a single
        login call to trigger the lockout 429.
        """
        import app.core.login_lockout as login_lockout

        email = "lockout-message@test.com"
        await _register(client, email)

        # Pre-populate 5 failures via the internal module (bypasses slowapi counter)
        r = login_lockout._get_redis()
        for _ in range(5):
            await login_lockout.record_failed_attempt(email)

        # One login call now — lockout middleware fires before slowapi counts it
        resp = await _login(client, email, password="WrongPass!")
        assert resp.status_code == 429
        detail = resp.json().get("detail", "")
        assert "minute" in detail.lower(), f"Expected retry time in detail: {detail}"

    async def test_wrong_password_before_lockout_returns_401(self, client: AsyncClient):
        """Attempts 1-5 must return 401 (not yet locked)."""
        email = "pre-lockout@test.com"
        await _register(client, email)

        for attempt in range(1, 6):
            resp = await _login(client, email, password="WrongPass!")
            assert resp.status_code == 401, (
                f"Attempt {attempt}: expected 401, got {resp.status_code}"
            )

    async def test_lockout_blocks_correct_password(self, client: AsyncClient):
        """After lockout, even the correct password must be rejected."""
        email = "blocked-correct@test.com"
        await _register(client, email)

        for _ in range(5):
            await _login(client, email, password="WrongPass!")

        # Correct password — must still be rejected
        resp = await _login(client, email, password="Password123!")
        assert resp.status_code == 429

    async def test_lockout_persists_across_multiple_wrong_attempts_post_lockout(
        self, client: AsyncClient
    ):
        """Subsequent attempts after lockout must also be 429, not 401."""
        email = "persist-lockout@test.com"
        await _register(client, email)

        for _ in range(5):
            await _login(client, email, password="WrongPass!")

        for _ in range(3):
            resp = await _login(client, email, password="AnotherWrong!")
            assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 2. Lockout clears after a successful login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLockoutClears:
    async def test_successful_login_clears_failed_attempts(self, client: AsyncClient):
        """A successful login must reset the lockout failure counter.

        We manipulate the lockout counter directly (bypassing the API) to avoid
        consuming the slowapi 5/min login budget, then confirm the counter is
        cleared after a successful login.
        """
        import app.core.login_lockout as login_lockout

        email = "clear-on-success@test.com"
        await _register(client, email)

        # Pre-populate 4 failures in Redis (one short of lockout threshold)
        for _ in range(4):
            await login_lockout.record_failed_attempt(email)

        # Successful login via the API — should clear the counter
        resp = await _login(client, email, password="Password123!")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.json()}"

        # Confirm the Redis counter has been cleared
        r = login_lockout._get_redis()
        key = login_lockout._key(email)
        stored = await r.get(key)
        assert stored is None or int(stored) == 0, (
            f"Expected lockout counter to be cleared, got: {stored}"
        )

    async def test_four_failures_then_success_not_locked(self, client: AsyncClient):
        """4 failures then 1 success: account must not be locked."""
        email = "four-then-success@test.com"
        await _register(client, email)

        for _ in range(4):
            await _login(client, email, password="WrongPass!")

        resp = await _login(client, email, password="Password123!")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Registration rate limiting (3/minute)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRegistrationRateLimit:
    async def test_fourth_register_in_a_minute_is_429(self, client: AsyncClient):
        """The 4th register request within the 1-minute window must return 429."""
        # 3 requests — all should succeed (or 409 if email taken, not 429)
        for i in range(3):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"reg-limit-{i}@test.com",
                    "password": "Password123!",
                    "full_name": "Test",
                },
            )
            assert resp.status_code in (201, 409), (
                f"Request {i + 1}: expected 201 or 409, got {resp.status_code}"
            )

        # 4th request must be rate-limited
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "reg-limit-4th@test.com",
                "password": "Password123!",
                "full_name": "Test",
            },
        )
        assert resp.status_code == 429, (
            f"Expected 429 on 4th register, got {resp.status_code}: {resp.json()}"
        )

    async def test_subsequent_registers_after_limit_also_429(self, client: AsyncClient):
        """Requests beyond the limit should all be 429."""
        for i in range(3):
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"reg-extra-{i}@test.com",
                    "password": "Password123!",
                    "full_name": "Test",
                },
            )

        for i in range(3, 6):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"reg-extra-{i}@test.com",
                    "password": "Password123!",
                    "full_name": "Test",
                },
            )
            assert resp.status_code == 429, (
                f"Request {i + 1}: expected 429, got {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# 4. Login rate limiting (5/minute)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoginRateLimit:
    async def test_sixth_login_in_a_minute_is_429(self, client: AsyncClient):
        """The 6th login request within the 1-minute window must return 429."""
        # 5 requests — 401 (wrong password) or 200 (right password), never 429
        for _ in range(5):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "nonexistent-rl@test.com", "password": "WrongPass!"},
            )
            assert resp.status_code != 429, (
                f"Hit rate limit too early: {resp.status_code}"
            )

        # 6th request must be rate-limited
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent-rl@test.com", "password": "WrongPass!"},
        )
        assert resp.status_code == 429, (
            f"Expected 429 on 6th login attempt, got {resp.status_code}: {resp.json()}"
        )

    async def test_login_rate_limit_applies_regardless_of_account_existence(
        self, client: AsyncClient
    ):
        """Rate limit on /login should apply even when the account doesn't exist."""
        for _ in range(5):
            await client.post(
                "/api/v1/auth/login",
                json={"email": "ghost-rl@test.com", "password": "WrongPass!"},
            )

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost-rl@test.com", "password": "WrongPass!"},
        )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 5. Rate-limit response headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRateLimitHeaders:
    async def test_rate_limit_response_has_no_ratelimit_headers_by_default(
        self, client: AsyncClient
    ):
        """slowapi headers are disabled in the current limiter config.

        This test documents the current behaviour.  If headers are ever
        enabled, change the assertion to check for their *presence* instead.
        """
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "headers-test@test.com", "password": "WrongPass!"},
        )
        # Headers are disabled — none of these should appear
        assert "x-ratelimit-limit" not in resp.headers
        assert "x-ratelimit-remaining" not in resp.headers
        assert "x-ratelimit-reset" not in resp.headers

    async def test_429_response_body_has_error_field(self, client: AsyncClient):
        """429 responses produced by slowapi's _rate_limit_exceeded_handler use
        the key 'error', not 'detail'.  Verify the structure matches."""
        for _ in range(5):
            await client.post(
                "/api/v1/auth/login",
                json={"email": "detail-test@test.com", "password": "WrongPass!"},
            )

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "detail-test@test.com", "password": "WrongPass!"},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert "error" in body, f"Expected 'error' key in 429 body: {body}"
        assert "rate limit" in body["error"].lower(), (
            f"Expected rate-limit text in 'error': {body['error']}"
        )

    async def test_429_response_content_type_is_json(self, client: AsyncClient):
        """slowapi 429 responses should be JSON."""
        for _ in range(5):
            await client.post(
                "/api/v1/auth/login",
                json={"email": "ctype-test@test.com", "password": "WrongPass!"},
            )

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ctype-test@test.com", "password": "WrongPass!"},
        )
        assert resp.status_code == 429
        assert "application/json" in resp.headers.get("content-type", "")
