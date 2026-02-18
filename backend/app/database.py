"""
Database Configuration and Session Management
SQLAlchemy setup with PostgreSQL
"""

import secrets
import string
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Database dependency for FastAPI
    Yields database session and ensures cleanup
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _generate_password(length: int = 16) -> str:
    """Generate a random password"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _migrate_columns():
    """Add missing columns to existing tables (poor man's migration)"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'users' not in tables:
        return

    with engine.begin() as conn:
        # users table
        existing = {col['name'] for col in inspector.get_columns('users')}
        if 'is_admin' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            logger.info("Added is_admin column to users table")
        if 'must_change_password' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE"))
            logger.info("Added must_change_password column to users table")
        # Download quality preferences (Feature 4)
        if 'preferred_quality' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferred_quality VARCHAR(10) DEFAULT 'hq'"))
            logger.info("Added preferred_quality column to users table")
        if 'preferred_format' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferred_format VARCHAR(10) DEFAULT 'auto'"))
            logger.info("Added preferred_format column to users table")
        if 'max_file_size_mb' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN max_file_size_mb INTEGER DEFAULT 0"))
            logger.info("Added max_file_size_mb column to users table")
        if 'preferred_hosts' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferred_hosts TEXT DEFAULT '[]'"))
            logger.info("Added preferred_hosts column to users table")

        # download_queue table — exponential backoff (Feature 2)
        if 'download_queue' in tables:
            dq_cols = {col['name'] for col in inspector.get_columns('download_queue')}
            if 'next_retry_at' not in dq_cols:
                conn.execute(text("ALTER TABLE download_queue ADD COLUMN next_retry_at TIMESTAMP NULL"))
                logger.info("Added next_retry_at column to download_queue table")

        # Reading progress (Feature 3)
        if 'chapters' in tables:
            ch_cols = {col['name'] for col in inspector.get_columns('chapters')}
            if 'read_at' not in ch_cols:
                conn.execute(text("ALTER TABLE chapters ADD COLUMN read_at TIMESTAMP NULL"))
                logger.info("Added read_at column to chapters table")

        if 'book_chapters' in tables:
            bc_cols = {col['name'] for col in inspector.get_columns('book_chapters')}
            if 'read_at' not in bc_cols:
                conn.execute(text("ALTER TABLE book_chapters ADD COLUMN read_at TIMESTAMP NULL"))
                logger.info("Added read_at column to book_chapters table")

        if 'comic_issues' in tables:
            ci_cols = {col['name'] for col in inspector.get_columns('comic_issues')}
            if 'read_at' not in ci_cols:
                conn.execute(text("ALTER TABLE comic_issues ADD COLUMN read_at TIMESTAMP NULL"))
                logger.info("Added read_at column to comic_issues table")

        if 'manga' in tables:
            mg_cols = {col['name'] for col in inspector.get_columns('manga')}
            if 'reading_status' not in mg_cols:
                conn.execute(text("ALTER TABLE manga ADD COLUMN reading_status VARCHAR(20) DEFAULT 'not_started'"))
                logger.info("Added reading_status column to manga table")
            if 'last_read_chapter' not in mg_cols:
                conn.execute(text("ALTER TABLE manga ADD COLUMN last_read_chapter DOUBLE PRECISION NULL"))
                logger.info("Added last_read_chapter column to manga table")

        if 'comics' in tables:
            co_cols = {col['name'] for col in inspector.get_columns('comics')}
            if 'reading_status' not in co_cols:
                conn.execute(text("ALTER TABLE comics ADD COLUMN reading_status VARCHAR(20) DEFAULT 'not_started'"))
                logger.info("Added reading_status column to comics table")
            if 'last_read_issue' not in co_cols:
                conn.execute(text("ALTER TABLE comics ADD COLUMN last_read_issue VARCHAR(20) NULL"))
                logger.info("Added last_read_issue column to comics table")

        if 'books' in tables:
            bk_cols = {col['name'] for col in inspector.get_columns('books')}
            if 'reading_status' not in bk_cols:
                conn.execute(text("ALTER TABLE books ADD COLUMN reading_status VARCHAR(20) DEFAULT 'not_started'"))
                logger.info("Added reading_status column to books table")
            if 'last_read_chapter' not in bk_cols:
                conn.execute(text("ALTER TABLE books ADD COLUMN last_read_chapter INTEGER NULL"))
                logger.info("Added last_read_chapter column to books table")

        # Notifications (Feature 3 v3.0)
        if 'users' in tables:
            u_cols = {col['name'] for col in inspector.get_columns('users')}
            if 'last_notification_check' not in u_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_notification_check TIMESTAMP NULL"))
                logger.info("Added last_notification_check column to users table")


def init_db():
    """Initialize database tables and create admin user if not exists"""
    # Ensure all models are registered with Base before create_all
    from app.models import log_entry  # noqa: F401
    _migrate_columns()
    Base.metadata.create_all(bind=engine)
    _seed_admin()


def _seed_admin():
    """Create default admin user if no admin exists"""
    from app.models.user import User
    from app.core.security import hash_password

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            return

        password = _generate_password()
        admin = User(
            username="admin",
            email="admin@alejandria.local",
            password_hash=hash_password(password),
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )
        db.add(admin)
        db.commit()

        logger.warning("=" * 60)
        logger.warning("  ADMIN USER CREATED — FIRST TIME ONLY")
        logger.warning(f"  Username: admin")
        logger.warning(f"  ADMIN PASSWORD: {password}")
        logger.warning("  Change this password on first login!")
        logger.warning("  This message will not appear again.")
        logger.warning("=" * 60)
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()
