"""
Tests for basic health and connectivity
"""


async def test_health_check(client):
    """GET /health should return 200 with status healthy."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


async def test_docs_available_in_debug(client):
    """OpenAPI docs should be accessible (DEBUG=true in test env)."""
    resp = await client.get("/docs")
    assert resp.status_code == 200


async def test_api_prefix_exists(client):
    """Unauthenticated access to protected routes should return 401, not 404."""
    resp = await client.get("/api/v1/manga/")
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
