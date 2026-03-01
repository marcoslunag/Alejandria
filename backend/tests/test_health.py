"""
Tests for basic health and connectivity
"""


def test_health_check(client):
    """GET /health should return 200 with status healthy."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_docs_available_in_debug(client):
    """OpenAPI docs should be accessible (DEBUG=true in test env)."""
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_api_prefix_exists(client):
    """Unauthenticated access to protected routes should return 401, not 404."""
    resp = client.get("/api/v1/manga/")
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
