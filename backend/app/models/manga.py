"""
Manga Model
Represents a manga series being monitored
Enhanced with Anilist metadata integration
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Manga(Base):
    """Manga model for storing manga series information with Anilist metadata"""

    __tablename__ = "manga"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(255), unique=True, index=True)

    # Download source (TomosManga, etc.)
    source_url = Column(String(500))  # URL where to download from
    source_type = Column(String(50), default='tomosmanga')  # Source identifier

    # Anilist integration (metadata source)
    anilist_id = Column(Integer, unique=True, index=True)  # Anilist ID
    mal_id = Column(Integer)  # MyAnimeList ID

    # Titles (multiple languages)
    title_romaji = Column(String(500))
    title_english = Column(String(500))
    title_native = Column(String(500))

    # Rich metadata from Anilist
    description = Column(Text)
    cover_image = Column(String(500))  # Main cover
    banner_image = Column(String(500))  # Banner image
    cover_color = Column(String(20))  # Hex color from cover

    # Manga info
    format = Column(String(50))  # MANGA, NOVEL, ONE_SHOT
    status = Column(String(50))  # FINISHED, RELEASING, NOT_YET_RELEASED
    start_date = Column(String(50))  # YYYY-MM-DD
    end_date = Column(String(50))  # YYYY-MM-DD
    chapters_total = Column(Integer)  # Expected total chapters
    volumes_total = Column(Integer)  # Expected total volumes

    # Categories and ratings
    genres = Column(JSON)  # Array of genres
    tags = Column(JSON)  # Array of tags
    average_score = Column(Float)  # 0-100 score from Anilist
    popularity = Column(Integer)  # Anilist popularity score

    # Authors and artists
    authors = Column(JSON)  # Array of author names
    artists = Column(JSON)  # Array of artist names

    # External links
    anilist_url = Column(String(500))
    country = Column(String(10))  # JP, KR, CN, etc.

    # System fields
    monitored = Column(Boolean, default=True, index=True)
    auto_download = Column(Boolean, default=True)  # Auto-download new chapters
    last_check = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Legacy field (keep for backward compatibility)
    @property
    def url(self):
        """Backward compatibility"""
        return self.source_url

    @property
    def cover_url(self):
        """Backward compatibility"""
        return self.cover_image

    # Relationships
    chapters = relationship(
        "Chapter",
        back_populates="manga",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Manga(id={self.id}, title='{self.title}', monitored={self.monitored})>"

    @property
    def total_chapters(self):
        """Get total number of chapters"""
        return self.chapters.count()

    @property
    def downloaded_chapters(self):
        """Get number of downloaded chapters"""
        return self.chapters.filter_by(status="downloaded").count()
