"""
Tests for OPDS catalog server and ereader_type settings.
"""
import base64


# ---------------------------------------------------------------------------
# OPDS Auth Tests
# ---------------------------------------------------------------------------

async def test_opds_root_no_auth(client):
    """GET /opds without credentials should return 401."""
    resp = await client.get("/api/v1/opds")
    assert resp.status_code == 401


async def test_opds_root_wrong_password(client, regular_user):
    """GET /opds with wrong password should return 401."""
    creds = base64.b64encode(b"testuser:wrongpassword").decode()
    resp = await client.get("/api/v1/opds", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 401


async def test_opds_root_valid_auth(client, regular_user):
    """GET /opds with valid credentials returns Atom XML."""
    creds = base64.b64encode(b"testuser:testpass123").decode()
    resp = await client.get("/api/v1/opds", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")
    body = resp.text
    assert "<feed" in body
    assert "Alejandría" in body


async def test_opds_manga_feed(client, regular_user):
    """GET /opds/manga returns Atom XML feed."""
    creds = base64.b64encode(b"testuser:testpass123").decode()
    resp = await client.get("/api/v1/opds/manga", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")


async def test_opds_search(client, regular_user):
    """GET /opds/search?q=test returns Atom XML."""
    creds = base64.b64encode(b"testuser:testpass123").decode()
    resp = await client.get("/api/v1/opds/search?q=test", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")


async def test_opds_opensearch_xml(client):
    """GET /opds/opensearch.xml returns OpenSearch description (no auth needed)."""
    resp = await client.get("/api/v1/opds/opensearch.xml")
    assert resp.status_code == 200
    assert "opensearch" in resp.headers.get("content-type", "").lower()


# ---------------------------------------------------------------------------
# ereader_type Settings Tests
# ---------------------------------------------------------------------------

async def _get_token(client, username, password):
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


async def test_settings_includes_ereader_type(client, regular_user):
    """GET /settings should return ereader_type field."""
    token = await _get_token(client, "testuser", "testpass123")
    resp = await client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ereader_type" in data
    assert data["ereader_type"] in ("kindle", "kobo", "pocketbook", "android", "other")


async def test_settings_update_ereader_type(client, regular_user):
    """POST /settings with ereader_type=kobo persists the value."""
    token = await _get_token(client, "testuser", "testpass123")

    resp = await client.post(
        "/api/v1/settings",
        json={"ereader_type": "kobo"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["ereader_type"] == "kobo"

    # Verify it persists
    resp2 = await client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp2.json()["ereader_type"] == "kobo"


async def test_settings_invalid_ereader_type_ignored(client, regular_user):
    """POST /settings with invalid ereader_type should be silently ignored (not crash)."""
    token = await _get_token(client, "testuser", "testpass123")

    # First set to known value
    await client.post(
        "/api/v1/settings",
        json={"ereader_type": "kindle"},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Now send invalid value
    resp = await client.post(
        "/api/v1/settings",
        json={"ereader_type": "invalid_device"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    # Value should remain unchanged (kindle)
    assert resp.json()["ereader_type"] == "kindle"


async def test_auth_me_includes_ereader_type(client, regular_user):
    """GET /auth/me should include ereader_type in UserResponse."""
    token = await _get_token(client, "testuser", "testpass123")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ereader_type" in data
