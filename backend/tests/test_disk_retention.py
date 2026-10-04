"""
Tests de retención de disco (roadmap #14):
- cleanup_old_files respeta CLEANUP_DAYS (0 = inmediato, <0 = desactivado)
- Cubre manga, cómics y libros (antes solo manga)
- Endpoint admin GET /system/disk-usage (uso por directorio + recuperable)
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import database as app_database
from app.services import scheduler as scheduler_module
from .conftest import _make_manga, _make_chapter, _make_comic, _make_issue, _make_book, _make_book_chapter


class _FakeSettings:
    def __init__(self, cleanup_days: int):
        self.CLEANUP_DAYS = cleanup_days


@pytest.fixture
def test_sessions(db, monkeypatch):
    """Apunta SessionLocal (app y scheduler) a la BD de tests."""
    from sqlalchemy.orm import sessionmaker
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=db.bind)
    monkeypatch.setattr(app_database, "SessionLocal", test_session)
    monkeypatch.setattr(scheduler_module, "SessionLocal", test_session)
    return test_session


@pytest.fixture
def sched(db, monkeypatch, tmp_path, test_sessions):
    """ContentScheduler con get_settings fake (CLEANUP_DAYS configurable)."""
    fake = _FakeSettings(cleanup_days=7)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: fake)
    from app.services.scheduler import ContentScheduler
    s = ContentScheduler(download_dir=str(tmp_path / "dl"), library_dir=str(tmp_path / "lib"))
    s._fake_settings = fake  # para ajustar CLEANUP_DAYS en cada test
    return s


def _run_cleanup(sched):
    asyncio.run(sched.cleanup_old_files())


def _touch(path, content=b"fake-archive-bytes"):
    path.write_bytes(content)
    return str(path)


# ── cleanup_old_files ──────────────────────────────────────────────────────────

def test_cleanup_removes_old_sent_manga_keeps_recent(db, sched, regular_user, tmp_path):
    manga = _make_manga(db, regular_user, title="Old Manga")
    old_ch = _make_chapter(db, manga, number=1)
    old_cbz = _touch(tmp_path / "old.cbz")
    old_epub = _touch(tmp_path / "old.epub")
    old_ch.file_path = old_cbz
    old_ch.converted_path = old_epub
    old_ch.sent_at = datetime.utcnow() - timedelta(days=10)  # > 7 días

    recent_ch = _make_chapter(db, manga, number=2)
    recent_cbz = _touch(tmp_path / "recent.cbz")
    recent_ch.file_path = recent_cbz
    recent_ch.sent_at = datetime.utcnow() - timedelta(days=1)  # < 7 días

    db.commit()
    _run_cleanup(sched)
    db.expire_all()

    assert not Path(old_cbz).exists()
    assert not Path(old_epub).exists()
    assert Path(recent_cbz).exists()

    fresh_old = db.get(old_ch.__class__, old_ch.id)
    fresh_recent = db.get(recent_ch.__class__, recent_ch.id)
    assert fresh_old.file_path is None and fresh_old.converted_path is None
    assert fresh_recent.file_path == recent_cbz


def test_cleanup_disabled_when_negative(db, sched, regular_user, tmp_path):
    sched._fake_settings.CLEANUP_DAYS = -1
    manga = _make_manga(db, regular_user, title="Kept Manga")
    ch = _make_chapter(db, manga, number=1)
    cbz = _touch(tmp_path / "kept.cbz")
    ch.file_path = cbz
    ch.sent_at = datetime.utcnow() - timedelta(days=30)

    db.commit()
    _run_cleanup(sched)
    db.expire_all()

    assert Path(cbz).exists()
    assert db.get(ch.__class__, ch.id).file_path == cbz


def test_cleanup_immediate_when_zero(db, sched, regular_user, tmp_path):
    sched._fake_settings.CLEANUP_DAYS = 0
    manga = _make_manga(db, regular_user, title="Instant Manga")
    ch = _make_chapter(db, manga, number=1)
    cbz = _touch(tmp_path / "instant.cbz")
    ch.file_path = cbz
    ch.sent_at = datetime.utcnow() - timedelta(hours=1)

    db.commit()
    _run_cleanup(sched)
    db.expire_all()

    assert not Path(cbz).exists()
    assert db.get(ch.__class__, ch.id).file_path is None


def test_cleanup_covers_comics_and_books(db, sched, regular_user, tmp_path):
    # Cómic enviado hace 10 días
    comic = _make_comic(db, regular_user, title="Old Comic")
    issue = _make_issue(db, comic, issue_number="1")
    cbr = _touch(tmp_path / "issue.cbr")
    epub = _touch(tmp_path / "issue.epub")
    issue.file_path = cbr
    issue.converted_path = epub
    issue.sent_at = datetime.utcnow() - timedelta(days=10)

    # Libro enviado hace 10 días
    book = _make_book(db, regular_user, title="Old Book")
    bc = _make_book_chapter(db, book, number=1)
    book_epub = _touch(tmp_path / "book.epub")
    bc.file_path = book_epub
    bc.sent_at = datetime.utcnow() - timedelta(days=10)

    db.commit()
    _run_cleanup(sched)
    db.expire_all()

    assert not Path(cbr).exists() and not Path(epub).exists() and not Path(book_epub).exists()
    assert db.get(issue.__class__, issue.id).file_path is None
    assert db.get(bc.__class__, bc.id).file_path is None


def test_cleanup_ignores_unsent_items(db, sched, regular_user, tmp_path):
    # Enviado hace 10 días pero SIN sent_at (aún no enviado) → no se toca
    manga = _make_manga(db, regular_user, title="Unsent Manga")
    ch = _make_chapter(db, manga, number=1)
    cbz = _touch(tmp_path / "unsent.cbz")
    ch.file_path = cbz  # sent_at = None

    # Convertido pero sin enviar (10 días) → no se toca
    ch2 = _make_chapter(db, manga, number=2)
    epub = _touch(tmp_path / "unsent.epub")
    ch2.converted_path = epub
    ch2.sent_at = None

    db.commit()
    _run_cleanup(sched)
    db.expire_all()

    assert Path(cbz).exists() and Path(epub).exists()
    assert db.get(ch.__class__, ch.id).file_path == cbz


def test_cleanup_pipe_separated_epubs(db, sched, regular_user, tmp_path):
    manga = _make_manga(db, regular_user, title="Multi Part")
    ch = _make_chapter(db, manga, number=1)
    part1 = _touch(tmp_path / "part1.epub")
    part2 = _touch(tmp_path / "part2.epub")
    ch.converted_path = f"{part1}|{part2}"
    ch.sent_at = datetime.utcnow() - timedelta(days=8)
    db.commit()

    _run_cleanup(sched)
    assert not Path(part1).exists() and not Path(part2).exists()


# ── Endpoint /system/disk-usage ───────────────────────────────────────────────

def test_disk_usage_admin(client, db, admin_headers, tmp_path):
    r = client.get("/api/v1/system/disk-usage", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"downloads", "library", "kindle", "reclaimable"}
    for section in ("downloads", "library", "kindle"):
        assert set(data[section].keys()) == {"path", "exists", "bytes", "mb", "files", "by_extension"}
    assert set(data["reclaimable"].keys()) == {"manga", "comics", "books", "cleanup_days"}
    assert isinstance(data["reclaimable"]["cleanup_days"], int)


def test_disk_usage_shows_reclaimable(client, db, admin_headers, regular_user, tmp_path):
    manga = _make_manga(db, regular_user, title="Sent Manga")
    ch = _make_chapter(db, manga, number=1)
    cbz = tmp_path / "sent.cbz"
    cbz.write_bytes(b"x" * 2048)
    ch.file_path = str(cbz)
    ch.sent_at = datetime.utcnow() - timedelta(days=1)
    db.commit()

    r = client.get("/api/v1/system/disk-usage", headers=admin_headers)
    data = r.json()
    assert data["reclaimable"]["manga"]["items"] == 1
    assert data["reclaimable"]["manga"]["bytes"] == 2048


def test_disk_usage_requires_admin(client, db, auth_headers):
    r = client.get("/api/v1/system/disk-usage", headers=auth_headers)
    assert r.status_code == 403


def test_disk_usage_requires_auth(client, db):
    r = client.get("/api/v1/system/disk-usage")
    assert r.status_code in (401, 403)
