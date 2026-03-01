"""Tests for comic endpoints: CRUD, IDOR protection, reading status, bundles."""
import pytest
from .conftest import _make_comic, _make_issue, _auth


def test_get_comics_library_empty(client, auth_headers):
    r = client.get("/api/v1/comics/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_comics_isolation(client, db, regular_user, second_user):
    _make_comic(db, regular_user, title="Mine")
    _make_comic(db, second_user, title="Theirs", comicvine_id=99)
    r = client.get("/api/v1/comics/", headers=_auth(regular_user))
    assert r.status_code == 200
    titles = [c["title"] for c in r.json()]
    assert "Mine" in titles
    assert "Theirs" not in titles


def test_get_comic_detail(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    r = client.get(f"/api/v1/comics/{comic.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["title"] == comic.title


def test_get_comic_idor(client, db, regular_user, second_user):
    comic = _make_comic(db, second_user)
    r = client.get(f"/api/v1/comics/{comic.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_delete_comic(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    r = client.delete(f"/api/v1/comics/{comic.id}", headers=auth_headers)
    assert r.status_code in (200, 204)
    r2 = client.get(f"/api/v1/comics/{comic.id}", headers=auth_headers)
    assert r2.status_code == 404


def test_delete_comic_idor(client, db, regular_user, second_user):
    comic = _make_comic(db, second_user)
    r = client.delete(f"/api/v1/comics/{comic.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_get_issues(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    _make_issue(db, comic, "1")
    _make_issue(db, comic, "2")
    r = client.get(f"/api/v1/comics/{comic.id}/issues", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_issues_idor(client, db, regular_user, second_user):
    """Cannot access issues of another user's comic (IDOR check)."""
    comic = _make_comic(db, second_user)
    _make_issue(db, comic)
    r = client.get(f"/api/v1/comics/{comic.id}/issues", headers=_auth(regular_user))
    assert r.status_code == 404


def test_reading_status_comic(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    r = client.patch(f"/api/v1/comics/{comic.id}/reading-status",
                     json={"status": "reading"}, headers=auth_headers)
    assert r.status_code == 200


def test_reading_status_idor(client, db, regular_user, second_user):
    comic = _make_comic(db, second_user)
    r = client.patch(f"/api/v1/comics/{comic.id}/reading-status",
                     json={"status": "reading"}, headers=_auth(regular_user))
    assert r.status_code == 404


def test_download_issues_requires_ownership(client, db, regular_user, second_user):
    """Cannot trigger download on another user's issues."""
    comic = _make_comic(db, second_user)
    issue = _make_issue(db, comic)
    r = client.post(f"/api/v1/comics/{comic.id}/issues/download",
                    json={"issue_ids": [issue.id]},
                    headers=_auth(regular_user))
    assert r.status_code == 404


def test_monitored_toggle(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    r = client.patch(f"/api/v1/comics/{comic.id}", json={"monitored": False}, headers=auth_headers)
    assert r.status_code == 200
    db.refresh(comic)
    assert comic.monitored is False
