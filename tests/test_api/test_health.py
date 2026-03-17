import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealth:
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_readiness(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}
