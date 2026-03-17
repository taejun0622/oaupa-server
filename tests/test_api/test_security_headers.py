"""Test plan: Security headers verification.

Tests that all HTTP responses include required security headers.
Verifies the SecurityHeadersMiddleware and CORS configuration in app/main.py.

Headers set by SecurityHeadersMiddleware (app/core/security_headers.py):
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security: max-age=31536000; includeSubDomains
  - Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
  - Referrer-Policy: strict-origin-when-cross-origin

CORS: Restricted to settings.cors_origins (default: http://localhost:3000).
"""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestSecurityHeaders:
    async def test_x_content_type_options(self, client: AsyncClient):
        """All responses should include X-Content-Type-Options: nosniff."""
        resp = await client.get("/api/v1/billing/config")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, client: AsyncClient):
        """All responses should include X-Frame-Options: DENY."""
        resp = await client.get("/api/v1/billing/config")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_x_xss_protection(self, client: AsyncClient):
        """All responses should include X-XSS-Protection: 1; mode=block."""
        resp = await client.get("/api/v1/billing/config")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    async def test_strict_transport_security(self, client: AsyncClient):
        """All responses should include HSTS header with max-age and includeSubDomains."""
        resp = await client.get("/api/v1/billing/config")
        hsts = resp.headers.get("strict-transport-security", "")
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts

    async def test_content_security_policy(self, client: AsyncClient):
        """All responses should include CSP with default-src 'self'."""
        resp = await client.get("/api/v1/billing/config")
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src" in csp
        assert "'self'" in csp

    async def test_content_security_policy_no_framing(self, client: AsyncClient):
        """CSP should disallow framing via frame-ancestors 'none'."""
        resp = await client.get("/api/v1/billing/config")
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors" in csp

    async def test_referrer_policy(self, client: AsyncClient):
        """All responses should include Referrer-Policy: strict-origin-when-cross-origin."""
        resp = await client.get("/api/v1/billing/config")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    async def test_headers_on_authenticated_endpoints(self, client: AsyncClient):
        """Security headers should be present on authenticated endpoints too."""
        headers = await auth_headers(client)
        resp = await client.get("/api/v1/projects", headers=headers)
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("strict-transport-security") is not None
        assert resp.headers.get("content-security-policy") is not None

    async def test_headers_on_error_responses(self, client: AsyncClient):
        """Security headers should be present even on 4xx responses."""
        resp = await client.get("/api/v1/billing/subscription")  # unauthenticated → 4xx
        assert resp.status_code >= 400
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_headers_on_health_endpoint(self, client: AsyncClient):
        """Security headers should be present on the health endpoint."""
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
class TestCORSHardening:
    async def test_cors_rejects_unknown_origin(self, client: AsyncClient):
        """Requests from non-allowed origins should not get CORS allow-origin header."""
        resp = await client.options(
            "/api/v1/billing/config",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.com"

    async def test_cors_allows_configured_origin(self, client: AsyncClient):
        """Requests from the configured allowed origin should get proper CORS headers."""
        resp = await client.options(
            "/api/v1/billing/config",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    async def test_cors_methods_restricted(self, client: AsyncClient):
        """CORS allowed methods should not include TRACE."""
        resp = await client.options(
            "/api/v1/billing/config",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "TRACE" not in allowed

    async def test_cors_credentials_header(self, client: AsyncClient):
        """CORS should include allow-credentials: true."""
        resp = await client.options(
            "/api/v1/billing/config",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    async def test_cors_simple_request_reflects_origin(self, client: AsyncClient):
        """A simple GET with a valid Origin should echo back the origin."""
        resp = await client.get(
            "/api/v1/billing/config",
            headers={"Origin": "http://localhost:3000"},
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    async def test_cors_simple_request_unknown_origin_no_header(self, client: AsyncClient):
        """A simple GET with an unknown Origin should not echo back any allow-origin."""
        resp = await client.get(
            "/api/v1/billing/config",
            headers={"Origin": "https://attacker.example.com"},
        )
        assert resp.headers.get("access-control-allow-origin") is None
