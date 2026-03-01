"""Tests for queue endpoints: list isolation, add/remove, IDOR protection, stats, clear."""
import pytest
from .conftest import (
    _make_manga, _make_chapter, _make_comic, _make_issue,
    _make_book, _make_book_chapter, _auth
)
from app.models.download import DownloadQueue


# ── Auth ───────────────────────────────────────────────────────────────────────

def test_queue_list_requires_auth(client):
    r = client.get("/api/v1/queue/")
    assert r.status_code in (401, 403)


def test_queue_stats_requires_auth(client):
    r = client.get("/api/v1/queue/stats")
    assert r.status_code in (401, 403)


def test_queue_add_requires_auth(client):
    r = client.post("/api/v1/queue/1")
    assert r.status_code in (401, 403)


# ── GET /queue/ ────────────────────────────────────────────────────────────────

def test_queue_list_empty(client, auth_headers):
    r = client.get("/api/v1/queue/", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_queue_list_shows_downloading_chapters(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0, status="downloading")
    r = client.get("/api/v1/queue/", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["content_type"] == "manga"
    assert items[0]["status"] == "downloading"


def test_queue_list_shows_error_chapters(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=2.0, status="error")
    r = client.get("/api/v1/queue/", headers=auth_headers)
    items = r.json()
    assert any(item["status"] == "failed" for item in items)


def test_queue_list_does_not_show_pending_chapters(client, db, regular_user, auth_headers):
    """Pending chapters (never downloaded) should NOT appear in queue."""
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0, status="pending")
    r = client.get("/api/v1/queue/", headers=auth_headers)
    assert r.json() == []


def test_queue_list_isolation(client, db, regular_user, second_user):
    """User can only see their own queue items."""
    manga_u1 = _make_manga(db, regular_user, title="Mine", anilist_id=111)
    manga_u2 = _make_manga(db, second_user, title="Theirs", anilist_id=222)
    _make_chapter(db, manga_u1, number=1.0, status="downloading")
    _make_chapter(db, manga_u2, number=1.0, status="downloading")

    r = client.get("/api/v1/queue/", headers=_auth(regular_user))
    items = r.json()
    assert len(items) == 1
    assert items[0]["manga_title"] == "Mine"


def test_queue_list_includes_book_chapters(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    _make_book_chapter(db, book, number=1, status="downloaded")
    r = client.get("/api/v1/queue/", headers=auth_headers)
    items = r.json()
    book_items = [i for i in items if i["content_type"] == "book"]
    assert len(book_items) == 1


def test_queue_list_includes_comic_issues(client, db, regular_user, auth_headers):
    comic = _make_comic(db, regular_user)
    issue = _make_issue(db, comic, status="error")
    r = client.get("/api/v1/queue/", headers=auth_headers)
    items = r.json()
    comic_items = [i for i in items if i["content_type"] == "comic"]
    assert len(comic_items) == 1
    assert comic_items[0]["status"] == "failed"


# ── POST /queue/{chapter_id} ───────────────────────────────────────────────────

def test_add_to_queue_success(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga)
    r = client.post(f"/api/v1/queue/{chapter.id}", headers=auth_headers)
    assert r.status_code == 201


def test_add_to_queue_idor(client, db, regular_user, second_user):
    """Cannot add another user's chapter to queue."""
    manga = _make_manga(db, second_user, title="Other's Manga", anilist_id=9999)
    chapter = _make_chapter(db, manga)
    r = client.post(f"/api/v1/queue/{chapter.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_add_to_queue_duplicate(client, db, regular_user, auth_headers):
    """Adding same chapter twice returns 400."""
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga)
    # Add queue entry manually
    dq = DownloadQueue(chapter_id=chapter.id, status="queued")
    db.add(dq)
    db.commit()

    r = client.post(f"/api/v1/queue/{chapter.id}", headers=auth_headers)
    assert r.status_code == 400
    assert "already in queue" in r.json()["detail"]


# ── DELETE /queue/{chapter_id} ─────────────────────────────────────────────────

def test_remove_from_queue_success(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga, status="error")
    r = client.delete(f"/api/v1/queue/{chapter.id}", headers=auth_headers)
    assert r.status_code == 204
    db.refresh(chapter)
    assert chapter.status == "pending"


def test_remove_from_queue_idor(client, db, regular_user, second_user):
    manga = _make_manga(db, second_user, title="Other's Manga", anilist_id=8888)
    chapter = _make_chapter(db, manga, status="error")
    r = client.delete(f"/api/v1/queue/{chapter.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_remove_from_queue_downloading_fails(client, db, regular_user, auth_headers):
    """Cannot remove a chapter that is currently downloading."""
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga, status="downloading")
    r = client.delete(f"/api/v1/queue/{chapter.id}", headers=auth_headers)
    assert r.status_code == 400


# ── GET /queue/stats ───────────────────────────────────────────────────────────

def test_queue_stats_empty(client, auth_headers):
    r = client.get("/api/v1/queue/stats", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["downloading"] == 0
    assert data["completed"] == 0
    assert data["failed"] == 0


def test_queue_stats_counts(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0, status="downloading")
    _make_chapter(db, manga, number=2.0, status="converted")
    _make_chapter(db, manga, number=3.0, status="error")
    r = client.get("/api/v1/queue/stats", headers=auth_headers)
    data = r.json()
    assert data["downloading"] == 1
    assert data["completed"] == 1
    assert data["failed"] == 1


def test_queue_stats_isolation(client, db, regular_user, second_user):
    """Stats only count current user's chapters."""
    manga_u1 = _make_manga(db, regular_user, title="Mine", anilist_id=111)
    manga_u2 = _make_manga(db, second_user, title="Theirs", anilist_id=222)
    _make_chapter(db, manga_u1, number=1.0, status="downloading")
    _make_chapter(db, manga_u2, number=1.0, status="downloading")

    r = client.get("/api/v1/queue/stats", headers=_auth(regular_user))
    assert r.json()["downloading"] == 1  # only user 1's chapter


# ── POST /queue/clear ──────────────────────────────────────────────────────────

def test_clear_queue_success(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0, status="converted")
    _make_chapter(db, manga, number=2.0, status="error")
    r = client.post("/api/v1/queue/clear", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["cleared"] == 2


def test_clear_queue_status_filter(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    _make_chapter(db, manga, number=1.0, status="converted")
    _make_chapter(db, manga, number=2.0, status="error")
    # Only clear failed
    r = client.post("/api/v1/queue/clear?status=failed", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["cleared"] == 1


def test_clear_queue_does_not_affect_other_users(client, db, regular_user, second_user):
    """Clear queue only affects the current user's chapters."""
    manga_u1 = _make_manga(db, regular_user, title="Mine", anilist_id=111)
    manga_u2 = _make_manga(db, second_user, title="Theirs", anilist_id=222)
    _make_chapter(db, manga_u1, number=1.0, status="error")
    chapter_u2 = _make_chapter(db, manga_u2, number=1.0, status="error")

    client.post("/api/v1/queue/clear", headers=_auth(regular_user))

    # User 2's chapter should NOT be affected
    db.refresh(chapter_u2)
    assert chapter_u2.status == "error"


# ── POST /queue/reset-stuck ────────────────────────────────────────────────────

def test_reset_stuck_requires_auth(client):
    r = client.post("/api/v1/queue/reset-stuck")
    assert r.status_code in (401, 403)


def test_reset_stuck_success(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga, status="downloading")
    r = client.post("/api/v1/queue/reset-stuck", headers=auth_headers)
    assert r.status_code == 200
    db.refresh(chapter)
    assert chapter.status == "pending"


# ── POST /queue/{chapter_id}/retry ────────────────────────────────────────────

def test_retry_failed_chapter(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga, status="error")
    r = client.post(f"/api/v1/queue/{chapter.id}/retry", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_retry_non_failed_chapter(client, db, regular_user, auth_headers):
    manga = _make_manga(db, regular_user)
    chapter = _make_chapter(db, manga, status="downloaded")
    r = client.post(f"/api/v1/queue/{chapter.id}/retry", headers=auth_headers)
    assert r.status_code == 400


def test_retry_idor(client, db, regular_user, second_user):
    manga = _make_manga(db, second_user, title="Other's Manga", anilist_id=7777)
    chapter = _make_chapter(db, manga, status="error")
    r = client.post(f"/api/v1/queue/{chapter.id}/retry", headers=_auth(regular_user))
    assert r.status_code == 404
