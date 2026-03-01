"""Tests for book endpoints: CRUD, IDOR protection, reading status."""
import pytest
from .conftest import _make_book, _make_book_chapter, _auth


def test_get_books_library_empty(client, auth_headers):
    r = client.get("/api/v1/books/library", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_books_isolation(client, db, regular_user, second_user):
    _make_book(db, regular_user, title="My Book")
    _make_book(db, second_user, title="Their Book", google_books_id="xyz999")
    r = client.get("/api/v1/books/library", headers=_auth(regular_user))
    titles = [b["title"] for b in r.json()]
    assert "My Book" in titles
    assert "Their Book" not in titles


def test_get_book_detail(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    r = client.get(f"/api/v1/books/{book.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["title"] == book.title


def test_get_book_idor(client, db, regular_user, second_user):
    book = _make_book(db, second_user)
    r = client.get(f"/api/v1/books/{book.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_delete_book(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    r = client.delete(f"/api/v1/books/{book.id}", headers=auth_headers)
    assert r.status_code == 200


def test_delete_book_idor(client, db, regular_user, second_user):
    book = _make_book(db, second_user)
    r = client.delete(f"/api/v1/books/{book.id}", headers=_auth(regular_user))
    assert r.status_code == 404


def test_get_chapters(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    _make_book_chapter(db, book, 1)
    _make_book_chapter(db, book, 2)
    r = client.get(f"/api/v1/books/{book.id}/chapters", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_reading_status_book(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    for status in ("reading", "completed", "not_started"):
        r = client.patch(f"/api/v1/books/{book.id}/reading-status",
                         json={"status": status}, headers=auth_headers)
        assert r.status_code == 200


def test_reading_status_book_idor(client, db, regular_user, second_user):
    book = _make_book(db, second_user)
    r = client.patch(f"/api/v1/books/{book.id}/reading-status",
                     json={"status": "reading"}, headers=_auth(regular_user))
    assert r.status_code == 404


def test_completed_marks_all_chapters(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    ch1 = _make_book_chapter(db, book, 1, status="downloaded")
    ch2 = _make_book_chapter(db, book, 2, status="downloaded")
    r = client.patch(f"/api/v1/books/{book.id}/reading-status",
                     json={"status": "completed"}, headers=auth_headers)
    assert r.status_code == 200
    db.refresh(ch1)
    db.refresh(ch2)
    assert ch1.read_at is not None
    assert ch2.read_at is not None
