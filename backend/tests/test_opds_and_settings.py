"""Tests for OPDS catalog server and ereader_type settings."""
import base64


def _get_token(client, username, password):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


# ─── OPDS Auth Tests ──────────────────────────────────────────────────────────

def test_opds_root_no_auth(client):
    """GET /opds without credentials should return 401."""
    resp = client.get("/api/v1/opds")
    assert resp.status_code == 401


def test_opds_root_wrong_password(client, regular_user):
    """GET /opds with wrong password should return 401."""
    creds = base64.b64encode(b"testuser:wrongpassword").decode()
    resp = client.get("/api/v1/opds", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 401


def test_opds_root_valid_auth(client, regular_user):
    """GET /opds with valid credentials returns Atom XML."""
    creds = base64.b64encode(b"testuser:password123").decode()  # default password in conftest
    resp = client.get("/api/v1/opds", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")
    body = resp.text
    assert "<feed" in body


def test_opds_manga_feed(client, regular_user):
    """GET /opds/manga returns Atom XML feed."""
    creds = base64.b64encode(b"testuser:password123").decode()
    resp = client.get("/api/v1/opds/manga", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")


def test_opds_search(client, regular_user):
    """GET /opds/search?q=test returns Atom XML."""
    creds = base64.b64encode(b"testuser:password123").decode()
    resp = client.get("/api/v1/opds/search?q=test", headers={"Authorization": f"Basic {creds}"})
    assert resp.status_code == 200
    assert "application/atom+xml" in resp.headers.get("content-type", "")


def test_opds_opensearch_xml(client):
    """GET /opds/opensearch.xml returns OpenSearch description (no auth needed)."""
    resp = client.get("/api/v1/opds/opensearch.xml")
    assert resp.status_code == 200
    assert "opensearch" in resp.headers.get("content-type", "").lower()


# ─── ereader_type Settings Tests ─────────────────────────────────────────────

def test_settings_includes_ereader_type(client, regular_user):
    """GET /settings should return ereader_type field."""
    token = _get_token(client, "testuser", "password123")
    resp = client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ereader_type" in data
    assert data["ereader_type"] in ("kindle", "kobo", "pocketbook", "android", "other")


def test_settings_update_ereader_type(client, regular_user):
    """POST /settings with ereader_type=kobo persists the value."""
    token = _get_token(client, "testuser", "password123")
    resp = client.post("/api/v1/settings", json={"ereader_type": "kobo"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["ereader_type"] == "kobo"
    resp2 = client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp2.json()["ereader_type"] == "kobo"


def test_settings_invalid_ereader_type_ignored(client, regular_user):
    """POST /settings with invalid ereader_type should be silently ignored."""
    token = _get_token(client, "testuser", "password123")
    client.post("/api/v1/settings", json={"ereader_type": "kindle"},
                headers={"Authorization": f"Bearer {token}"})
    resp = client.post("/api/v1/settings", json={"ereader_type": "invalid_device"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["ereader_type"] == "kindle"


def test_auth_me_includes_ereader_type(client, regular_user):
    """GET /auth/me should include ereader_type in UserResponse."""
    token = _get_token(client, "testuser", "password123")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "ereader_type" in resp.json()
