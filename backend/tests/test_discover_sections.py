"""
Tests para Discover 2.0 (roadmap #18): GET /recommendations/library-sections

Verifica:
- Auth requerido
- Biblioteca vacía → secciones vacías
- Separación: following (monitored) / continue_reading (reading) / recently_added
- Mapeo content_type (manga/comic/book) para ContentCard
- Aislamiento por usuario
- Orden por created_at desc
- Límite por sección
"""
import pytest
from datetime import datetime, timedelta

from .conftest import _make_manga, _make_comic, _make_book

URL = "/api/v1/recommendations/library-sections"


def _titles(section):
    return {item["title"] for item in section}


def test_sections_auth_required(client):
    # HTTPBearer() de FastAPI devuelve 403 cuando falta el header Authorization
    r = client.get(URL)
    assert r.status_code in (401, 403)


def test_sections_empty_library(client, auth_headers):
    r = client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"following": [], "continue_reading": [], "recently_added": []}


def test_sections_split(client, db, regular_user, auth_headers):
    # A: monitored + reading → following + continue_reading + recently_added
    a = _make_manga(db, regular_user, title="Manga A", anilist_id=1)
    a.reading_status = "reading"
    db.commit()
    # B: no monitoreado, no leyendo → solo recently_added
    b = _make_comic(db, regular_user, title="Comic B", comicvine_id=2)
    b.monitored = False
    db.commit()
    # C: monitoreado, completado → following + recently_added (NO continue_reading)
    c = _make_book(db, regular_user, title="Book C", google_books_id="c3")
    c.reading_status = "completed"
    db.commit()

    data = client.get(URL, headers=auth_headers).json()

    assert _titles(data["following"]) == {"Manga A", "Book C"}
    assert _titles(data["continue_reading"]) == {"Manga A"}
    assert _titles(data["recently_added"]) == {"Manga A", "Comic B", "Book C"}


def test_sections_content_type_mapping(client, db, regular_user, auth_headers):
    _make_manga(db, regular_user, title="Manga X", anilist_id=1)
    _make_comic(db, regular_user, title="Comic X", comicvine_id=2)
    _make_book(db, regular_user, title="Book X", google_books_id="b3")

    data = client.get(URL, headers=auth_headers).json()
    by_type = {i["content_type"]: i["title"] for i in data["recently_added"]}
    assert by_type == {"manga": "Manga X", "comic": "Comic X", "book": "Book X"}

    # Shape compatible con ContentCard
    item = data["recently_added"][0]
    for field in ("library_id", "title", "cover_image", "reading_status", "monitored", "in_library"):
        assert field in item
    assert item["in_library"] is True


def test_sections_only_own_items(client, db, regular_user, second_user, auth_headers):
    _make_manga(db, regular_user, title="Mio", anilist_id=1)
    _make_manga(db, second_user, title="De Otro", anilist_id=99999)

    data = client.get(URL, headers=auth_headers).json()
    all_titles = (
        _titles(data["following"])
        | _titles(data["continue_reading"])
        | _titles(data["recently_added"])
    )
    assert all_titles == {"Mio"}


def test_sections_sorted_by_created_at_desc(client, db, regular_user, auth_headers):
    old = _make_manga(db, regular_user, title="Old", anilist_id=1)
    new = _make_manga(db, regular_user, title="New", anilist_id=2)
    # Retrocede created_at del primero para garantizar el orden
    old.created_at = datetime.utcnow() - timedelta(days=10)
    db.commit()

    data = client.get(URL, headers=auth_headers).json()
    assert [i["title"] for i in data["recently_added"]] == ["New", "Old"]


def test_sections_limit(client, db, regular_user, auth_headers):
    for i in range(5):
        _make_manga(db, regular_user, title=f"M{i}", anilist_id=100 + i)

    data = client.get(URL + "?limit=3", headers=auth_headers).json()
    assert len(data["recently_added"]) <= 3
    assert len(data["following"]) <= 3
    assert len(data["continue_reading"]) <= 3
