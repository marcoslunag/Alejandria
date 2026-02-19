"""
Tests for authentication endpoints
"""


async def test_login_success(client, admin_user):
    """Login with correct credentials returns a token."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testadmin",
        "password": "testpass123"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client, admin_user):
    """Login with wrong password returns 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testadmin",
        "password": "wrongpassword"
    })
    assert resp.status_code == 401


async def test_login_unknown_user(client):
    """Login with unknown username returns 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "doesnotexist",
        "password": "anything"
    })
    assert resp.status_code == 401


async def test_protected_route_without_token(client):
    """Accessing a protected route without token returns 401 or 403."""
    resp = await client.get("/api/v1/manga/")
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


async def test_protected_route_with_token(client, auth_headers):
    """Accessing a protected route with valid token returns 200."""
    resp = await client.get("/api/v1/manga/", headers=auth_headers)
    assert resp.status_code == 200


async def test_admin_endpoint_requires_admin(client, auth_headers):
    """Admin endpoint rejects regular users with 403."""
    resp = await client.get("/api/v1/auth/users", headers=auth_headers)
    assert resp.status_code == 403


async def test_admin_endpoint_allows_admin(client, admin_headers):
    """Admin endpoint allows admin users."""
    resp = await client.get("/api/v1/auth/users", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
