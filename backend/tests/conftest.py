"""
Test fixtures for Alejandría backend
Uses SQLite DB to avoid PostgreSQL dependency in tests.
Compatible with httpx >= 0.28 (uses ASGITransport).
"""
import os
import pytest
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure test environment BEFORE importing the app
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret-key-only-for-tests-not-real"
os.environ["DISABLE_SCHEDULER"] = "true"
os.environ["DEBUG"] = "true"

from app.database import Base, get_db
from app.main import app
from app.core.security import hash_password

SQLALCHEMY_TEST_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create tables once for the whole test session."""
    from app.models import log_entry  # noqa: ensure all models loaded
    import app.models.user  # noqa
    import app.models.manga  # noqa
    import app.models.chapter  # noqa
    import app.models.comic  # noqa
    import app.models.book  # noqa
    import app.models.book_chapter  # noqa
    import app.models.download  # noqa
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    import pathlib
    p = pathlib.Path("./test.db")
    if p.exists():
        p.unlink()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the login rate limiter between tests to prevent 429 errors."""
    from app.api.v1.auth import _login_attempts
    _login_attempts.clear()
    yield
    _login_attempts.clear()


@pytest.fixture
def db():
    """
    Per-test DB session. Commits are visible to the app (important for login tests).
    Cleans up created records after each test.
    """
    session = TestingSessionLocal()
    yield session
    # Rollback any uncommitted changes and clean up test data
    session.rollback()
    # Delete test users by username pattern to keep DB clean
    try:
        session.execute(text("DELETE FROM users WHERE username LIKE 'test%'"))
        session.execute(text("DELETE FROM manga WHERE slug LIKE 'test-%' OR slug LIKE '%test%'"))
        session.execute(text("DELETE FROM comics WHERE slug LIKE 'test-%' OR slug LIKE '%test%'"))
        session.execute(text("DELETE FROM books WHERE slug LIKE 'test-%' OR slug LIKE '%test%'"))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


@pytest.fixture
async def client():
    """
    Async HTTP test client using httpx.AsyncClient + ASGITransport.
    All tests using this fixture must be 'async def'.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
def admin_user(db):
    """Create an admin user in the test DB (committed, visible to app)."""
    from app.models.user import User
    # Remove if exists from prior failed test
    existing = db.query(User).filter(User.username == "testadmin").first()
    if existing:
        db.delete(existing)
        db.commit()
    user = User(
        username="testadmin",
        email="testadmin@test.local",
        password_hash=hash_password("testpass123"),
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def regular_user(db):
    """Create a regular user in the test DB (committed, visible to app)."""
    from app.models.user import User
    existing = db.query(User).filter(User.username == "testuser").first()
    if existing:
        db.delete(existing)
        db.commit()
    user = User(
        username="testuser",
        email="testuser@test.local",
        password_hash=hash_password("testpass123"),
        is_active=True,
        is_admin=False,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
async def admin_token(client, admin_user):
    """Get auth token for admin user."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testadmin",
        "password": "testpass123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
async def user_token(client, regular_user):
    """Get auth token for regular user."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "testpass123"
    })
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(user_token):
    """Authorization headers for regular user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
async def admin_headers(admin_token):
    """Authorization headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}
