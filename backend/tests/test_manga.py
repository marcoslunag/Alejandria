"""
Tests for manga endpoints:
- Library CRUD
- IDOR protection (user isolation)
- Reading status
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from .conftest import _make_manga, _make_chapter, _make_user, _auth


# ── Library ────────────────────────────────────────────────────────────────────

def test_get_manga_library_empty(client, auth_headers):
    r = client.get("/api/v1/manga/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_manga_library_shows_own_only(client, db, regular_user, second_user):
    """User can only see their own manga."""
    _make_manga(db, regular_user, title="My Manga")
    _make_manga(db, second_user, title="Their Manga", anilist_id=99999)

    r = client.get("/api/v1/manga/", headers=_auth(regular_user))
    assert r.status_code == 200
    titles = [m["title"] for m in r.json()]
    assert "My Manga" in titles
    assert "Their Manga" not in titles


def test_get_manga_library_unauthenticated(client):
    r = client.get("/api/v1/manga/")
    assert r.status_code == 403


# ── Detail ─────────────────────────────────────────────────────────────────────

def test_get_manga_detail(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    r = client.get(f"/api/v1/manga/{manga.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["title"] == manga.title


def test_get_manga_idor(client, db, regular_user, second_user):
    """User cannot access another user's manga."""
    manga = _make_manga(db, second_user, title="Private")
    r = client.get(f"/api/v1/manga/{manga.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_get_manga_not_found(client, auth_headers):
    r = client.get("/api/v1/manga/99999", headers=auth_headers)
    assert r.status_code == 404


# ── Delete ─────────────────────────────────────────────────────────────────────

def test_delete_manga(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    r = client.delete(f"/api/v1/manga/{manga.id}", headers=auth_headers)
    assert r.status_code == 204
    # Verify it's gone
    r2 = client.get(f"/api/v1/manga/{manga.id}", headers=auth_headers)
    assert r2.status_code == 404


def test_delete_manga_idor(client, db, regular_user, second_user):
    """User cannot delete another user's manga."""
    manga = _make_manga(db, second_user)
    r = client.delete(f"/api/v1/manga/{manga.id}", headers=_auth(regular_user))
    assert r.status_code == 404


# ── Chapters ───────────────────────────────────────────────────────────────────

def test_get_chapters(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0)
    _make_chapter(db, manga, number=2.0)
    r = client.get(f"/api/v1/manga/{manga.id}/chapters", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_chapters_idor(client, db, regular_user, second_user):
    manga = _make_manga(db, second_user)
    _make_chapter(db, manga)
    r = client.get(f"/api/v1/manga/{manga.id}/chapters", headers=_auth(regular_user))
    assert r.status_code == 404


# ── Reading status ─────────────────────────────────────────────────────────────

def test_set_reading_status(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    r = client.patch(f"/api/v1/manga/{manga.id}/reading-status",
                     json={"status": "reading"},
                     headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["reading_status"] == "reading"


def test_set_reading_status_completed_marks_chapters(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    ch = _make_chapter(db, manga, status="downloaded")
    r = client.patch(f"/api/v1/manga/{manga.id}/reading-status",
                     json={"status": "completed"},
                     headers=auth_headers)
    assert r.status_code == 200
    db.refresh(ch)
    assert ch.read_at is not None


def test_set_reading_status_invalid(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    r = client.patch(f"/api/v1/manga/{manga.id}/reading-status",
                     json={"status": "invalid_status"},
                     headers=auth_headers)
    assert r.status_code == 400


def test_set_reading_status_idor(client, db, regular_user, second_user):
    manga = _make_manga(db, second_user)
    r = client.patch(f"/api/v1/manga/{manga.id}/reading-status",
                     json={"status": "reading"},
                     headers=_auth(regular_user))
    assert r.status_code == 404


# ── Monitored toggle ───────────────────────────────────────────────────────────

def test_toggle_monitored(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    assert manga.monitored is True
    # Endpoint is PUT, not PATCH
    r = client.put(f"/api/v1/manga/{manga.id}",
                   json={"monitored": False},
                   headers=auth_headers)
    assert r.status_code == 200
    db.refresh(manga)
    assert manga.monitored is False


# ── Add manga (mocked AniList) ─────────────────────────────────────────────────

def test_add_manga_from_anilist(client, db, regular_user, auth_headers):
    mock_metadata = {
        "anilist_id": 777,
        "title": "Mock Manga",
        "title_romaji": "Mock Manga",
        "title_english": "Mock Manga",
        "title_native": "モックマンガ",
        "description": "A test manga",
        "cover_image": None,
        "banner_image": None,
        "cover_color": None,
        "format": "MANGA",
        "status": "RELEASING",
        "genres": ["Action"],
        "tags": [],
        "authors": [],
        "artists": [],
        "average_score": 80,
        "popularity": 1000,
        "chapters": None,
        "volumes": None,
        "start_date": None,
        "end_date": None,
        "anilist_url": "https://anilist.co/manga/777",
        "country": "JP",
        "mal_id": None,
    }
    with patch("app.api.v1.manga.AnilistService") as MockAnilist:
        instance = MockAnilist.return_value
        instance.get_manga_by_id = AsyncMock(return_value=mock_metadata)
        r = client.post("/api/v1/manga/add/anilist",
                        json={"anilist_id": 777, "monitored": True},
                        headers=auth_headers)
    assert r.status_code in (200, 201)
    assert r.json()["title"] == "Mock Manga"


def test_add_manga_duplicate(client, db, regular_user, auth_headers):
    """Adding same manga twice should return 409."""
    manga = _make_manga(db, regular_user, anilist_id=555)
    with patch("app.api.v1.manga.AnilistService"):
        r = client.post("/api/v1/manga/add/anilist",
                        json={"anilist_id": 555, "monitored": True},
                        headers=auth_headers)
    assert r.status_code in (400, 409)  # endpoint returns 400 for duplicates
