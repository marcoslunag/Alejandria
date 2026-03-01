"""
Tests for authentication endpoints:
- Login (correct/wrong credentials, rate limiting)
- Change password
- Get me
- Admin user management
"""
import pytest
from .conftest import _make_user, _auth, _token


# ── Login ──────────────────────────────────────────────────────────────────────

def test_login_success(client, db):
    _make_user(db, username="alice", email="alice@test.com", password="pass123")
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": "pass123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["must_change_password"] is False


def test_login_wrong_password(client, db):
    _make_user(db, username="bob", email="bob@test.com", password="correct")
    r = client.post("/api/v1/auth/login", json={"username": "bob", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client, db):
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "pass"})
    assert r.status_code == 401


def test_login_inactive_user(client, db):
    u = _make_user(db, username="inactive", email="i@test.com", password="pass")
    u.is_active = False
    db.commit()
    r = client.post("/api/v1/auth/login", json={"username": "inactive", "password": "pass"})
    assert r.status_code == 403


def test_login_sets_must_change_password(client, db):
    _make_user(db, username="newu", email="new@test.com", password="pass",
               must_change_password=True, device_setup_completed=False)
    r = client.post("/api/v1/auth/login", json={"username": "newu", "password": "pass"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True


def test_login_rate_limit(client, db):
    """More than 10 failed attempts from same IP should return 429."""
    _make_user(db, username="target", email="t@test.com", password="correct")
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"username": "target", "password": "WRONG"})
    r = client.post("/api/v1/auth/login", json={"username": "target", "password": "WRONG"})
    assert r.status_code == 429


# ── Get me ─────────────────────────────────────────────────────────────────────

def test_get_me_authenticated(client, regular_user, auth_headers):
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["username"] == regular_user.username
    assert "password_hash" not in r.json()


def test_get_me_unauthenticated(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 403  # HTTPBearer returns 403 when no credentials


def test_get_me_invalid_token(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert r.status_code == 401


# ── Change password ────────────────────────────────────────────────────────────

def test_change_password_success(client, db):
    user = _make_user(db, username="cp1", email="cp1@test.com", password="oldpass")
    headers = _auth(user)
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "oldpass", "new_password": "newpass123"},
                    headers=headers)
    assert r.status_code == 200
    # Should be able to login with new password
    r2 = client.post("/api/v1/auth/login", json={"username": "cp1", "password": "newpass123"})
    assert r2.status_code == 200


def test_change_password_wrong_current(client, regular_user, auth_headers):
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "wrongpass", "new_password": "newpass"},
                    headers=auth_headers)
    assert r.status_code == 400


def test_change_password_too_short(client, regular_user, auth_headers):
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "password123", "new_password": "abc"},
                    headers=auth_headers)
    assert r.status_code == 400


def test_change_password_clears_must_change_flag(client, db):
    user = _make_user(db, username="cp2", email="cp2@test.com", password="pass",
                      must_change_password=True, device_setup_completed=False)
    headers = _auth(user)
    client.post("/api/v1/auth/change-password",
                json={"current_password": "pass", "new_password": "newpass123"},
                headers=headers)
    db.refresh(user)
    assert user.must_change_password is False


# ── Admin: list users ──────────────────────────────────────────────────────────

def test_admin_list_users(client, admin_headers, admin_user, regular_user):
    r = client.get("/api/v1/auth/users", headers=admin_headers)
    assert r.status_code == 200
    usernames = [u["username"] for u in r.json()]
    assert admin_user.username in usernames
    assert regular_user.username in usernames


def test_list_users_requires_admin(client, auth_headers):
    r = client.get("/api/v1/auth/users", headers=auth_headers)
    assert r.status_code == 403


# ── Admin: create user ─────────────────────────────────────────────────────────

def test_admin_create_user(client, admin_headers):
    r = client.post("/api/v1/auth/users",
                    json={"username": "newuser", "email": "new@test.com", "password": "pass123"},
                    headers=admin_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "newuser"
    assert data["must_change_password"] is True  # always set on creation


def test_create_user_duplicate_username(client, admin_headers, db):
    _make_user(db, username="dupe", email="dupe@test.com", password="pass")
    r = client.post("/api/v1/auth/users",
                    json={"username": "dupe", "email": "nodupe@test.com", "password": "pass"},
                    headers=admin_headers)
    assert r.status_code == 400


def test_create_user_requires_admin(client, auth_headers):
    r = client.post("/api/v1/auth/users",
                    json={"username": "x", "email": "x@x.com", "password": "pass123"},
                    headers=auth_headers)
    assert r.status_code == 403


# ── Admin: delete user ─────────────────────────────────────────────────────────

def test_admin_delete_user(client, admin_headers, regular_user):
    r = client.delete(f"/api/v1/auth/users/{regular_user.id}", headers=admin_headers)
    assert r.status_code == 200


def test_admin_cannot_delete_self(client, admin_headers, admin_user):
    r = client.delete(f"/api/v1/auth/users/{admin_user.id}", headers=admin_headers)
    assert r.status_code == 400


def test_delete_user_requires_admin(client, auth_headers, regular_user):
    r = client.delete(f"/api/v1/auth/users/{regular_user.id}", headers=auth_headers)
    assert r.status_code == 403


# ── Admin: reset password ──────────────────────────────────────────────────────

def test_admin_reset_password(client, admin_headers, regular_user):
    r = client.patch(f"/api/v1/auth/users/{regular_user.id}/reset-password", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "new_password" in data
    assert len(data["new_password"]) >= 8


def test_reset_password_requires_admin(client, auth_headers, regular_user):
    r = client.patch(f"/api/v1/auth/users/{regular_user.id}/reset-password", headers=auth_headers)
    assert r.status_code == 403
