"""Tests for settings endpoints: get/update, device_setup_completed, ereader_type."""
import pytest
from .conftest import _make_user, _auth


# ── Auth ───────────────────────────────────────────────────────────────────────

def test_get_settings_requires_auth(client):
    r = client.get("/api/v1/settings")
    assert r.status_code in (401, 403)


def test_save_settings_requires_auth(client):
    r = client.post("/api/v1/settings", json={"kcc_profile": "KPW5"})
    assert r.status_code in (401, 403)


# ── GET /settings ─────────────────────────────────────────────────────────────

def test_get_settings_returns_defaults(client, auth_headers):
    r = client.get("/api/v1/settings", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["kcc_profile"] == "KPW5"
    assert data["auto_send_to_kindle"] is False
    assert data["preferred_quality"] == "hq"
    assert data["preferred_format"] == "auto"
    assert "device_setup_completed" in data
    assert "ereader_type" in data


def test_get_settings_device_setup_completed_default(client, auth_headers):
    """Regular test user has device_setup_completed=True (set in conftest)."""
    r = client.get("/api/v1/settings", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["device_setup_completed"] is True


# ── POST /settings ────────────────────────────────────────────────────────────

def test_save_settings_device_setup_completed(client, db, auth_headers):
    """Setting device_setup_completed to True persists."""
    r = client.post("/api/v1/settings", json={"device_setup_completed": True},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["device_setup_completed"] is True


def test_save_settings_ereader_type_valid(client, auth_headers):
    """Valid ereader types are accepted."""
    for ereader_type in ("kindle", "kobo", "pocketbook", "android", "other"):
        r = client.post("/api/v1/settings", json={"ereader_type": ereader_type},
                        headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["ereader_type"] == ereader_type


def test_save_settings_ereader_type_invalid_ignored(client, auth_headers):
    """Invalid ereader_type is silently ignored (not stored)."""
    # First set a known valid type
    client.post("/api/v1/settings", json={"ereader_type": "kindle"}, headers=auth_headers)
    # Then try invalid type
    r = client.post("/api/v1/settings", json={"ereader_type": "toaster"}, headers=auth_headers)
    assert r.status_code == 200
    # Should keep the previous valid value (kindle), not "toaster"
    assert r.json()["ereader_type"] == "kindle"


def test_save_settings_kcc_profile(client, auth_headers):
    r = client.post("/api/v1/settings", json={"kcc_profile": "KO2"},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["kcc_profile"] == "KO2"


def test_save_settings_auto_send_to_kindle(client, auth_headers):
    r = client.post("/api/v1/settings", json={"auto_send_to_kindle": True},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["auto_send_to_kindle"] is True


def test_save_settings_partial_update(client, auth_headers):
    """Only specified fields are updated, others retain previous values."""
    # Set initial values
    client.post("/api/v1/settings",
                json={"kcc_profile": "KPW5", "preferred_quality": "hq"},
                headers=auth_headers)
    # Update only one field
    r = client.post("/api/v1/settings", json={"preferred_quality": "lq"},
                    headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["preferred_quality"] == "lq"
    # kcc_profile should still be KPW5
    assert data["kcc_profile"] == "KPW5"


def test_settings_isolated_between_users(client, db, regular_user, second_user):
    """Settings are per-user, not shared."""
    # User 1 sets their ereader_type
    from .conftest import _auth
    client.post("/api/v1/settings", json={"ereader_type": "kobo"},
                headers=_auth(regular_user))
    # User 2 should have their own defaults
    r2 = client.get("/api/v1/settings", headers=_auth(second_user))
    assert r2.status_code == 200
    # User 2's ereader_type should NOT be kobo (it's user 1's setting)
    assert r2.json()["ereader_type"] != "kobo" or r2.json()["ereader_type"] == "kindle"


# ── TeraBox status ────────────────────────────────────────────────────────────

def test_terabox_status_requires_auth(client):
    r = client.get("/api/v1/settings/terabox-status")
    assert r.status_code in (401, 403)


def test_terabox_status_no_config(client, auth_headers):
    """Returns valid response when TERABOX_COOKIE not set."""
    r = client.get("/api/v1/settings/terabox-status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "is_configured" in data
