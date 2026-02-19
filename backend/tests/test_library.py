"""
Tests for library list endpoints (manga, comics, books)
"""


async def test_manga_library_empty(client, auth_headers):
    """Empty library returns an empty list (not an error)."""
    resp = await client.get("/api/v1/manga/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_comics_library_empty(client, auth_headers):
    resp = await client.get("/api/v1/comics/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_books_library_empty(client, auth_headers):
    resp = await client.get("/api/v1/books/library", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


async def test_manga_library_contains_added_item(client, auth_headers, db, regular_user):
    """A manga added to DB appears in the user's library list."""
    from app.models.manga import Manga
    manga = Manga(
        title="Dragon Ball",
        slug="dragon-ball",
        anilist_id=123456,
        user_id=regular_user.id,
        monitored=False,
        reading_status="not_started",
    )
    db.add(manga)
    db.commit()

    resp = await client.get("/api/v1/manga/", headers=auth_headers)
    assert resp.status_code == 200
    titles = [m["title"] for m in resp.json()]
    assert "Dragon Ball" in titles


async def test_user_isolation(client, admin_headers, auth_headers, db, regular_user):
    """A manga owned by user A is NOT visible in user B's library."""
    from app.models.manga import Manga
    manga = Manga(
        title="Only Mine",
        slug="only-mine",
        anilist_id=777888,
        user_id=regular_user.id,
        monitored=False,
        reading_status="not_started",
    )
    db.add(manga)
    db.commit()

    # Admin (different user) should NOT see it
    resp = await client.get("/api/v1/manga/", headers=admin_headers)
    assert resp.status_code == 200
    titles = [m["title"] for m in resp.json()]
    assert "Only Mine" not in titles
