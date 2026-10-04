"""Tests de los índices compuestos de BD (roadmap #11).

- chapters(manga_id, number) → listados de capítulos ordenados por número
- comic_issues(comic_id, issue_number) → listados de issues ordenados
- download_queue: status ya indexado; user_id no existe en la tabla (la cola
  se filtra por JOIN a Manga/Book/Comic.user_id), por lo que no aplica.
"""
from sqlalchemy import inspect

from app.models.chapter import Chapter
from app.models.comic import ComicIssue


def test_chapters_declares_composite_index():
    """El modelo Chapter declara el índice compuesto (manga_id, number)."""
    idx = {i.name: [c.name for c in i.columns] for i in Chapter.__table__.indexes}
    assert idx.get("ix_chapters_manga_id_number") == ["manga_id", "number"]


def test_comic_issues_declares_composite_index():
    """El modelo ComicIssue declara el índice compuesto (comic_id, issue_number)."""
    idx = {i.name: [c.name for c in i.columns] for i in ComicIssue.__table__.indexes}
    assert idx.get("ix_comic_issues_comic_id_issue_number") == ["comic_id", "issue_number"]


def test_composite_indexes_created_on_database(db):
    """Tras create_all los índices existen en la BD real (no solo declarados)."""
    insp = inspect(db.bind)

    chapters_idx = {i["name"]: i["column_names"] for i in insp.get_indexes("chapters")}
    assert chapters_idx.get("ix_chapters_manga_id_number") == ["manga_id", "number"]

    issues_idx = {i["name"]: i["column_names"] for i in insp.get_indexes("comic_issues")}
    assert issues_idx.get("ix_comic_issues_comic_id_issue_number") == ["comic_id", "issue_number"]


def test_download_queue_status_indexed(db):
    """download_queue.status tiene índice (la cola se consulta por status)."""
    insp = inspect(db.bind)
    names = {i["name"]: i["column_names"] for i in insp.get_indexes("download_queue")}
    assert any(cols == ["status"] for cols in names.values())
