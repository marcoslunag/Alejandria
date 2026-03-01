"""
Tests for reading status endpoints (manga, comics, books)
Verifies that items can be marked as read WITHOUT requiring a download.
"""
import pytest


@pytest.fixture
def manga_in_library(db, regular_user):
    from app.models.manga import Manga
    manga = Manga(title="Test Manga", slug="test-manga", anilist_id=999999,
                  user_id=regular_user.id, monitored=False, reading_status="not_started")
    db.add(manga); db.commit(); db.refresh(manga)
    return manga


def test_manga_set_reading_status_not_started(client, auth_headers, manga_in_library):
    resp = client.patch(f"/api/v1/manga/{manga_in_library.id}/reading-status",
                        json={"status": "not_started"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "not_started"


def test_manga_set_reading_status_reading(client, auth_headers, manga_in_library):
    resp = client.patch(f"/api/v1/manga/{manga_in_library.id}/reading-status",
                        json={"status": "reading"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "reading"


def test_manga_set_reading_status_completed(client, auth_headers, manga_in_library):
    resp = client.patch(f"/api/v1/manga/{manga_in_library.id}/reading-status",
                        json={"status": "completed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "completed"


def test_manga_reading_status_invalid_value(client, auth_headers, manga_in_library):
    resp = client.patch(f"/api/v1/manga/{manga_in_library.id}/reading-status",
                        json={"status": "invalid_value"}, headers=auth_headers)
    assert resp.status_code in (400, 422)


def test_manga_reading_status_ownership(client, admin_headers, manga_in_library):
    resp = client.patch(f"/api/v1/manga/{manga_in_library.id}/reading-status",
                        json={"status": "completed"}, headers=admin_headers)
    assert resp.status_code == 404


@pytest.fixture
def comic_in_library(db, regular_user):
    from app.models.comic import Comic
    comic = Comic(title="Test Comic", slug="test-comic", user_id=regular_user.id,
                  monitored=False, reading_status="not_started")
    db.add(comic); db.commit(); db.refresh(comic)
    return comic


def test_comic_set_reading_status_completed(client, auth_headers, comic_in_library):
    resp = client.patch(f"/api/v1/comics/{comic_in_library.id}/reading-status",
                        json={"status": "completed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "completed"


def test_comic_set_reading_status_reading(client, auth_headers, comic_in_library):
    resp = client.patch(f"/api/v1/comics/{comic_in_library.id}/reading-status",
                        json={"status": "reading"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "reading"


@pytest.fixture
def book_in_library(db, regular_user):
    from app.models.book import Book
    book = Book(title="Test Book", slug="test-book", google_books_id="TESTBOOK01",
                user_id=regular_user.id, reading_status="not_started")
    db.add(book); db.commit(); db.refresh(book)
    return book


def test_book_set_reading_status_completed(client, auth_headers, book_in_library):
    resp = client.patch(f"/api/v1/books/{book_in_library.id}/reading-status",
                        json={"status": "completed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "completed"


def test_book_set_reading_status_reading(client, auth_headers, book_in_library):
    resp = client.patch(f"/api/v1/books/{book_in_library.id}/reading-status",
                        json={"status": "reading"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["reading_status"] == "reading"
