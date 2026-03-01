"""
Tests for system endpoints:
- Security: auth required on /status, /config, /scheduler/status
- Admin-only endpoints
- Dashboard data isolation
"""
import pytest
from .conftest import _make_manga, _make_chapter, _make_comic, _make_issue, _make_book, _auth


# ── /system/status ─────────────────────────────────────────────────────────────

def test_system_status_requires_auth(client):
    r = client.get("/api/v1/system/status")
    assert r.status_code == 403


def test_system_status_returns_user_data(client, db, regular_user, auth_headers):
    """Stats are filtered to current user's data."""
    _make_manga(db, regular_user, title="Mine")
    r = client.get("/api/v1/system/status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_manga"] == 1
    assert "status" in data


def test_system_status_isolation(client, db, regular_user, second_user, auth_headers):
    """User only sees their own stats, not others'."""
    from .conftest import _make_user
    _make_manga(db, second_user, title="Other's", anilist_id=99)
    r = client.get("/api/v1/system/status", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total_manga"] == 0  # regular_user has none


# ── /system/config ─────────────────────────────────────────────────────────────

def test_system_config_requires_auth(client):
    r = client.get("/api/v1/system/config")
    assert r.status_code == 403


def test_system_config_returns_config(client, auth_headers):
    r = client.get("/api/v1/system/config", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "check_interval_hours" in data


# ── /system/health ─────────────────────────────────────────────────────────────

def test_system_health_public(client):
    """Health check should be public (for load balancers)."""
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


# ── /health (root) ─────────────────────────────────────────────────────────────

def test_root_health_public(client):
    r = client.get("/health")
    assert r.status_code == 200


# ── /scheduler/status ─────────────────────────────────────────────────────────

def test_scheduler_status_requires_auth(client):
    r = client.get("/scheduler/status")
    assert r.status_code == 403


def test_scheduler_status_authenticated(client, auth_headers):
    r = client.get("/scheduler/status", headers=auth_headers)
    assert r.status_code == 200


# ── Admin-only: /system/stats ──────────────────────────────────────────────────

def test_admin_stats_requires_admin(client, auth_headers):
    r = client.get("/api/v1/system/stats", headers=auth_headers)
    assert r.status_code == 403


def test_admin_stats_for_admin(client, admin_headers):
    r = client.get("/api/v1/system/stats", headers=admin_headers)
    assert r.status_code == 200


# ── Admin-only: /system/logs/recent ───────────────────────────────────────────

def test_logs_requires_admin(client, auth_headers):
    r = client.get("/api/v1/system/logs/recent", headers=auth_headers)
    assert r.status_code == 403


def test_logs_for_admin(client, admin_headers):
    r = client.get("/api/v1/system/logs/recent", headers=admin_headers)
    assert r.status_code == 200
    assert "logs" in r.json()


# ── /system/dashboard ─────────────────────────────────────────────────────────

def test_dashboard_requires_auth(client):
    r = client.get("/api/v1/system/dashboard")
    assert r.status_code == 403


def test_dashboard_returns_user_data(client, db, regular_user, auth_headers):
    _make_manga(db, regular_user)
    r = client.get("/api/v1/system/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "library" in data
    assert data["library"]["manga"] == 1
    assert "recent_downloads" in data
    assert "reading_stats" in data


def test_dashboard_data_isolation(client, db, regular_user, second_user, auth_headers):
    _make_manga(db, second_user, title="Not mine", anilist_id=99)
    r = client.get("/api/v1/system/dashboard", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["library"]["manga"] == 0
