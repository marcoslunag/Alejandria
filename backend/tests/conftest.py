"""
Test fixtures and configuration for Alejandría backend tests.
Uses SQLite in-memory DB to avoid needing a real PostgreSQL instance.
"""
import os
# Override env vars BEFORE any app imports (lru_cache reads them on first import)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only-32chars"
os.environ["DEBUG"] = "true"

import pytest
import asyncio
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.comic import Comic, ComicIssue
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.download import DownloadQueue
from app.core.security import hash_password, create_access_token

# ── SQLite in-memory database ──────────────────────────────────────────────────
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create fresh tables for each test, then tear down."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_rate_limiters():
    """Clear in-memory rate limiters between tests to prevent state leakage."""
    from app.api.v1 import auth as auth_module
    from app.api.v1 import upload as upload_module
    auth_module._login_attempts.clear()
    upload_module._upload_attempts.clear()
    yield
    auth_module._login_attempts.clear()
    upload_module._upload_attempts.clear()


@pytest.fixture(scope="function")
def client(db) -> Generator:
    """Test client with DB override."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helper: create users ───────────────────────────────────────────────────────

def _make_user(db, username="testuser", email="test@test.com",
               password="password123", is_admin=False, must_change_password=False,
               device_setup_completed=True):
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=is_admin,
        must_change_password=must_change_password,
        device_setup_completed=device_setup_completed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_token(user)}"}


@pytest.fixture
def regular_user(db):
    return _make_user(db)


@pytest.fixture
def admin_user(db):
    return _make_user(db, username="admin", email="admin@test.com",
                      password="adminpass", is_admin=True, device_setup_completed=True)


@pytest.fixture
def second_user(db):
    return _make_user(db, username="other", email="other@test.com",
                      password="otherpass")


@pytest.fixture
def regular_token(regular_user):
    return _token(regular_user)


@pytest.fixture
def admin_token(admin_user):
    return _token(admin_user)


@pytest.fixture
def auth_headers(regular_user):
    return _auth(regular_user)


@pytest.fixture
def admin_headers(admin_user):
    return _auth(admin_user)


# ── Helper: create manga ───────────────────────────────────────────────────────

def _make_manga(db, user, title="Test Manga", anilist_id=12345):
    m = Manga(
        title=title,
        slug=title.lower().replace(" ", "-"),
        user_id=user.id,
        anilist_id=anilist_id,
        monitored=True,
        auto_download=False,
        genres=[],
        tags=[],
        authors=[],
        artists=[],
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _make_chapter(db, manga, number=1.0, status="pending"):
    ch = Chapter(
        manga_id=manga.id,
        number=number,
        url=f"https://example.com/ch{number}",
        status=status,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _make_comic(db, user, title="Test Comic", comicvine_id=67890):
    c = Comic(
        title=title,
        slug=title.lower().replace(" ", "-"),
        user_id=user.id,
        comicvine_id=comicvine_id,
        monitored=True,
        auto_download=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_issue(db, comic, issue_number="1", status="pending"):
    issue = ComicIssue(
        comic_id=comic.id,
        issue_number=issue_number,
        status=status,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


def _make_book(db, user, title="Test Book", google_books_id="abc123"):
    b = Book(
        title=title,
        slug=title.lower().replace(" ", "-"),
        user_id=user.id,
        google_books_id=google_books_id,
        monitored=True,
        auto_download=False,
        authors=[],
        categories=[],
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _make_book_chapter(db, book, number=1, status="pending"):
    bc = BookChapter(
        book_id=book.id,
        number=number,
        status=status,
    )
    db.add(bc)
    db.commit()
    db.refresh(bc)
    return bc
