"""Tests for book endpoints: CRUD, IDOR protection, reading status, EPUB reader."""
import pytest
from .conftest import _make_book, _make_book_chapter, _auth, _token


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


# ============================================================================
# Web reader (roadmap #8) — streaming EPUB
# ============================================================================

def _make_epub_file(tmp_path, name="chapter.epub"):
    p = tmp_path / name
    p.write_bytes(b"PK\x03\x04 fake-epub-content")
    return p


def test_epub_endpoint_streams_file(client, db, regular_user, auth_headers, tmp_path):
    book = _make_book(db, regular_user)
    ch = _make_book_chapter(db, book, 1, status="downloaded")
    ch.file_path = str(_make_epub_file(tmp_path))
    db.commit()

    r = client.get(f"/api/v1/books/{book.id}/chapters/{ch.id}/epub", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/epub+zip")
    assert r.content == b"PK\x03\x04 fake-epub-content"


def test_epub_endpoint_token_query_param(client, db, regular_user, tmp_path):
    """El frontend usa header Bearer, pero el endpoint también acepta ?token= (estilo manga)."""
    book = _make_book(db, regular_user)
    ch = _make_book_chapter(db, book, 1, status="downloaded")
    ch.file_path = str(_make_epub_file(tmp_path))
    db.commit()

    r = client.get(
        f"/api/v1/books/{book.id}/chapters/{ch.id}/epub?token={_token(regular_user)}"
    )
    assert r.status_code == 200


def test_epub_endpoint_requires_auth(client, db, regular_user, tmp_path):
    book = _make_book(db, regular_user)
    ch = _make_book_chapter(db, book, 1, status="downloaded")
    ch.file_path = str(_make_epub_file(tmp_path))
    db.commit()

    r = client.get(f"/api/v1/books/{book.id}/chapters/{ch.id}/epub")
    assert r.status_code == 401


def test_epub_endpoint_idor(client, db, regular_user, second_user, tmp_path):
    book = _make_book(db, second_user)
    ch = _make_book_chapter(db, book, 1, status="downloaded")
    ch.file_path = str(_make_epub_file(tmp_path))
    db.commit()

    r = client.get(f"/api/v1/books/{book.id}/chapters/{ch.id}/epub", headers=_auth(regular_user))
    assert r.status_code == 404


def test_epub_endpoint_not_downloaded(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    ch = _make_book_chapter(db, book, 1, status="pending")
    r = client.get(f"/api/v1/books/{book.id}/chapters/{ch.id}/epub", headers=auth_headers)
    assert r.status_code == 404


def test_epub_endpoint_file_missing_on_disk(client, db, regular_user, auth_headers):
    book = _make_book(db, regular_user)
    ch = _make_book_chapter(db, book, 1, status="downloaded")
    ch.file_path = "/nonexistent/missing.epub"
    db.commit()

    r = client.get(f"/api/v1/books/{book.id}/chapters/{ch.id}/epub", headers=auth_headers)
    assert r.status_code == 404


def test_books_library_total_count_header(client, db, regular_user, auth_headers):
    """X-Total-Count para infinite scroll (roadmap #9)."""
    for i in range(1, 4):
        _make_book(db, regular_user, title=f"Pag Book {i}", google_books_id=f"pag{i}")

    r = client.get("/api/v1/books/library", params={"limit": 2}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers.get("x-total-count") == "3"
