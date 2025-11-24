import os
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text, Index
from sqlalchemy.orm import sessionmaker, declarative_base

# Default database path in data/ folder
_default_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "photo_sorter.db")
DATABASE_PATH = os.environ.get("PHOTO_SORTER_DB", _default_db_path)
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class MediaFile(Base):
    """Represents a scanned media file with metadata and hashes."""
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, unique=True, nullable=False, index=True)
    filename = Column(String, nullable=False)
    folder_path = Column(String, nullable=False, index=True)

    # File metadata
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String, nullable=False)  # MD5 hash for exact duplicates
    modified_time = Column(DateTime, nullable=False)

    # EXIF metadata
    date_taken = Column(DateTime, nullable=True, index=True)
    year = Column(Integer, nullable=True, index=True)
    month = Column(Integer, nullable=True, index=True)
    day = Column(Integer, nullable=True, index=True)

    # Perceptual hashes for similarity detection
    phash = Column(String, nullable=True, index=True)  # Perceptual hash
    dhash = Column(String, nullable=True)  # Difference hash
    ahash = Column(String, nullable=True)  # Average hash

    # Status fields
    is_organized = Column(Boolean, default=False)
    is_favorite = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    duplicate_group_id = Column(Integer, nullable=True, index=True)

    # Timestamps
    scanned_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_media_date', 'year', 'month', 'day'),
    )


class DuplicateGroup(Base):
    """Represents a group of potentially duplicate images."""
    __tablename__ = "duplicate_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_hash = Column(String, nullable=False, index=True)  # Representative hash
    file_count = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending, reviewed, resolved
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanSession(Base):
    """Tracks scanning sessions for resume capability."""
    __tablename__ = "scan_sessions"

    id = Column(Integer, primary_key=True, index=True)
    folder_path = Column(String, nullable=False, index=True)
    status = Column(String, default="in_progress")  # in_progress, completed, failed
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    last_processed_file = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


def init_db():
    """Initialize the database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
