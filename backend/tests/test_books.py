"""Tests for book endpoints: CRUD, IDOR protection, reading status, EPUB reader."""
import pytest
from .conftest import _make_book, _make_book_chapter, _auth, _token, TestingSessionLocal
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.services.book_scrapers.base import BookScraperResult, DownloadLink, HostType


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


# ============================================================================
# El Hobbit fix: no perder la scraper_url de la búsqueda al añadir
# ============================================================================

def test_clean_book_search_title():
    """Quita paréntesis/corchetes que confunden a los scrapers."""
    from app.api.v1.books import _clean_book_search_title
    assert _clean_book_search_title("El Hobbit (edición revisada)") == "El Hobbit"
    assert _clean_book_search_title("Book [Vol 1] Edition") == "Book Edition"
    assert _clean_book_search_title("  Multiple   Spaces ") == "Multiple Spaces"
    # Si queda vacío, conserva el original
    assert _clean_book_search_title("(solo parentesis)") == "(solo parentesis)"


def test_add_book_from_google_books_saves_scraper_url(client, db, regular_user, auth_headers, monkeypatch):
    """Si la búsqueda matcheó un scraper, el endpoint guarda source_urls."""
    from app.api.v1 import books as books_module

    class _FakeGB:
        async def get_book_by_id(self, gb_id):
            return {
                "title": "El Hobbit (edición revisada)",
                "google_books_id": gb_id,
                "authors": ["J.R.R. Tolkien"],
                "categories": [],
            }

    async def noop_search(book_id, title):
        pass

    monkeypatch.setattr(books_module, "get_google_books_service", lambda: _FakeGB())
    monkeypatch.setattr(books_module, "_search_scrapers_for_book", noop_search)

    r = client.post(
        "/api/v1/books/from-google-books",
        json={
            "google_books_id": "hob1",
            "monitored": True,
            "auto_download": True,
            "scraper_source": "lectulandia",
            "scraper_url": "https://ww3.lectulandia.com/book/el-hobbit",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    book = db.query(Book).filter_by(google_books_id="hob1").first()
    assert book is not None
    assert book.source_urls == {"lectulandia": "https://ww3.lectulandia.com/book/el-hobbit"}


def test_add_book_from_google_books_without_scraper_url(client, db, regular_user, auth_headers, monkeypatch):
    """Sin scraper_url → source_urls vacío (comportamiento previo)."""
    from app.api.v1 import books as books_module

    class _FakeGB:
        async def get_book_by_id(self, gb_id):
            return {
                "title": "Some Book",
                "google_books_id": gb_id,
                "authors": ["Author"],
                "categories": [],
            }

    async def noop_search(book_id, title):
        pass

    monkeypatch.setattr(books_module, "get_google_books_service", lambda: _FakeGB())
    monkeypatch.setattr(books_module, "_search_scrapers_for_book", noop_search)

    r = client.post(
        "/api/v1/books/from-google-books",
        json={"google_books_id": "nb1", "monitored": True, "auto_download": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    book = db.query(Book).filter_by(google_books_id="nb1").first()
    assert book is not None
    assert book.source_urls in ({}, None)


async def test_search_scrapers_resolves_known_source_urls_without_researching(db, regular_user, monkeypatch):
    """Si el libro ya tiene source_urls, se resuelven directo sin re-buscar."""
    from app.api.v1 import books as books_module

    book = _make_book(
        db, regular_user,
        title="El Hobbit (edición revisada)", google_books_id="hob2",
    )
    book.source_urls = {"lectulandia": "https://ww3.lectulandia.com/book/el-hobbit"}
    db.commit()
    book_id = book.id

    searched = {"n": 0}

    async def fake_search(self, query, page=1):
        searched["n"] += 1
        return []

    async def fake_dl(self, url):
        return BookScraperResult(
            title="El Hobbit",
            source="lectulandia",
            source_url=url,
            success=True,
            download_links=[
                DownloadLink(url="https://example.com/hobbit.epub", host=HostType.DIRECT, quality_score=70)
            ],
        )

    monkeypatch.setattr(books_module.LectulandiaScraper, "search", fake_search)
    monkeypatch.setattr(books_module.LectulandiaScraper, "get_download_links", fake_dl)
    # La función crea su propia sesión; apuntamos a la del test.
    monkeypatch.setattr("app.database.SessionLocal", lambda: db)

    await books_module._search_scrapers_for_book(book_id, "El Hobbit (edición revisada)")

    # `db` fue cerrado por el finally de la función; usamos sesión nueva para verificar.
    verify = TestingSessionLocal()
    ch = verify.query(BookChapter).filter_by(book_id=book_id, number=1).first()
    assert ch is not None
    assert ch.download_url == "https://example.com/hobbit.epub"
    assert searched["n"] == 0  # no re-buscó
    b = verify.query(Book).filter_by(id=book_id).first()
    assert b.source_urls["lectulandia"] == "https://ww3.lectulandia.com/book/el-hobbit"
    verify.close()
