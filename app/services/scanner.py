import os
import hashlib
from datetime import datetime
from typing import Optional, List, Tuple, Generator
from pathlib import Path

from PIL import Image, ExifTags
import imagehash
from sqlalchemy.orm import Session

from app.database import MediaFile, ScanSession, get_db, SessionLocal

SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'}

# Extensions to explicitly ignore (videos and other media)
IGNORED_EXTENSIONS = {
    # Video formats
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg',
    '.3gp', '.3g2', '.mts', '.m2ts', '.ts', '.vob', '.ogv', '.divx', '.xvid',
    # Audio formats
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.aiff', '.alac',
    # Document formats
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf',
    # Other
    '.zip', '.rar', '.7z', '.tar', '.gz', '.dmg', '.iso', '.exe', '.app',
    '.json', '.xml', '.html', '.css', '.js', '.py', '.md', '.csv',
}

BATCH_SIZE = 100  # Process files in batches for memory efficiency


def is_valid_image(file_path: str) -> bool:
    """
    Verify that a file is a valid image that can be processed.
    This catches files with image extensions that aren't actually images.
    """
    try:
        with Image.open(file_path) as img:
            img.verify()  # Verify it's a valid image
        return True
    except Exception:
        return False


def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    """Calculate MD5 hash of a file for exact duplicate detection."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_perceptual_hashes(file_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Calculate perceptual hashes for similarity detection."""
    try:
        img = Image.open(file_path)
        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        phash = str(imagehash.phash(img))
        dhash = str(imagehash.dhash(img))
        ahash = str(imagehash.average_hash(img))
        return phash, dhash, ahash
    except Exception as e:
        print(f"Error calculating perceptual hash for {file_path}: {e}")
        return None, None, None


def get_exif_date(file_path: str) -> Optional[datetime]:
    """Extract date taken from EXIF metadata."""
    try:
        img = Image.open(file_path)
        exif_data = img._getexif()
        if exif_data:
            for tag, value in exif_data.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                if decoded == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                elif decoded == "DateTime":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        print(f"EXIF read error for {file_path}: {e}")
    return None


def get_file_date(file_path: str) -> datetime:
    """Get date for a file - EXIF date or fall back to modification time."""
    exif_date = get_exif_date(file_path)
    if exif_date:
        return exif_date
    timestamp = os.path.getmtime(file_path)
    return datetime.fromtimestamp(timestamp)


def is_supported_image(file_path: Path) -> bool:
    """Check if a file is a supported image based on extension."""
    suffix = file_path.suffix.lower()
    # Explicitly check it's a supported image extension
    # and not an ignored extension (videos, audio, documents, etc.)
    return suffix in SUPPORTED_IMAGE_EXTENSIONS and suffix not in IGNORED_EXTENSIONS


def discover_files(folder_path: str, include_subfolders: bool = True) -> Generator[str, None, None]:
    """
    Discover all image files in a folder.

    Only returns files with supported image extensions.
    Ignores videos, audio files, documents, and other non-image files.
    """
    folder = Path(folder_path)

    if include_subfolders:
        for file_path in folder.rglob('*'):
            if file_path.is_file() and is_supported_image(file_path):
                yield str(file_path)
    else:
        for file_path in folder.glob('*'):
            if file_path.is_file() and is_supported_image(file_path):
                yield str(file_path)


def count_files(folder_path: str, include_subfolders: bool = True) -> int:
    """Count total image files in a folder."""
    return sum(1 for _ in discover_files(folder_path, include_subfolders))


def is_file_already_scanned(db: Session, file_path: str, file_size: int, modified_time: datetime) -> bool:
    """Check if a file has already been scanned and hasn't changed."""
    existing = db.query(MediaFile).filter(MediaFile.file_path == file_path).first()
    if existing:
        # Check if file has been modified since last scan
        if existing.file_size == file_size and existing.modified_time == modified_time:
            return True
    return False


def process_single_file(file_path: str) -> Optional[dict]:
    """
    Process a single image file and extract all metadata.

    Returns None if the file is not a valid image.
    """
    try:
        # Validate that this is actually a valid image file
        if not is_valid_image(file_path):
            print(f"Skipping invalid image file: {file_path}")
            return None

        stat = os.stat(file_path)
        file_size = stat.st_size
        modified_time = datetime.fromtimestamp(stat.st_mtime)

        # Calculate hashes
        file_hash = get_file_hash(file_path)
        phash, dhash, ahash = get_perceptual_hashes(file_path)

        # Get date information
        date_taken = get_file_date(file_path)

        return {
            'file_path': file_path,
            'filename': os.path.basename(file_path),
            'folder_path': os.path.dirname(file_path),
            'file_size': file_size,
            'file_hash': file_hash,
            'modified_time': modified_time,
            'date_taken': date_taken,
            'year': date_taken.year if date_taken else None,
            'month': date_taken.month if date_taken else None,
            'day': date_taken.day if date_taken else None,
            'phash': phash,
            'dhash': dhash,
            'ahash': ahash,
        }
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return None


def create_scan_session(db: Session, folder_path: str, total_files: int) -> ScanSession:
    """Create a new scan session."""
    session = ScanSession(
        folder_path=folder_path,
        status="in_progress",
        total_files=total_files,
        processed_files=0,
        failed_files=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_resume_scan_session(db: Session, folder_path: str) -> Optional[ScanSession]:
    """Get an existing in-progress scan session for resume."""
    return db.query(ScanSession).filter(
        ScanSession.folder_path == folder_path,
        ScanSession.status == "in_progress"
    ).first()


def update_scan_session(db: Session, session: ScanSession, processed: int, failed: int,
                        last_file: str, status: str = None, error: str = None):
    """Update scan session progress."""
    session.processed_files = processed
    session.failed_files = failed
    session.last_processed_file = last_file
    if status:
        session.status = status
        if status == "completed":
            session.completed_at = datetime.utcnow()
    if error:
        session.error_message = error
    db.commit()


def scan_folder(folder_path: str, include_subfolders: bool = True,
                session_id: Optional[int] = None) -> dict:
    """
    Scan a folder for media files with resume capability.

    Returns scan statistics.
    """
    db = SessionLocal()
    try:
        # Count total files
        total_files = count_files(folder_path, include_subfolders)

        # Check for existing session to resume
        existing_session = get_or_resume_scan_session(db, folder_path)

        if existing_session:
            scan_session = existing_session
            start_after = existing_session.last_processed_file
        else:
            scan_session = create_scan_session(db, folder_path, total_files)
            start_after = None

        processed = scan_session.processed_files
        failed = scan_session.failed_files
        skipped = 0
        new_files = 0

        skip_mode = start_after is not None
        batch = []

        for file_path in discover_files(folder_path, include_subfolders):
            # Resume logic - skip files until we reach the last processed file
            if skip_mode:
                if file_path == start_after:
                    skip_mode = False
                continue

            try:
                stat = os.stat(file_path)
                file_size = stat.st_size
                modified_time = datetime.fromtimestamp(stat.st_mtime)

                # Check if already scanned (incremental scanning)
                if is_file_already_scanned(db, file_path, file_size, modified_time):
                    skipped += 1
                    processed += 1
                    continue

                # Process the file
                file_data = process_single_file(file_path)

                if file_data:
                    # Check if file exists in DB (update) or is new (insert)
                    existing = db.query(MediaFile).filter(MediaFile.file_path == file_path).first()

                    if existing:
                        for key, value in file_data.items():
                            setattr(existing, key, value)
                        existing.updated_at = datetime.utcnow()
                    else:
                        media_file = MediaFile(**file_data)
                        db.add(media_file)
                        new_files += 1

                    processed += 1
                else:
                    failed += 1

                # Commit in batches
                if processed % BATCH_SIZE == 0:
                    db.commit()
                    update_scan_session(db, scan_session, processed, failed, file_path)

            except Exception as e:
                print(f"Error scanning {file_path}: {e}")
                failed += 1

        # Final commit
        db.commit()
        update_scan_session(db, scan_session, processed, failed, "", status="completed")

        return {
            'session_id': scan_session.id,
            'status': 'completed',
            'total_files': total_files,
            'processed_files': processed,
            'new_files': new_files,
            'skipped_files': skipped,
            'failed_files': failed
        }

    except Exception as e:
        if 'scan_session' in locals():
            update_scan_session(db, scan_session, processed, failed, "",
                              status="failed", error=str(e))
        raise
    finally:
        db.close()


def get_scan_status(session_id: int) -> Optional[dict]:
    """Get the status of a scan session."""
    db = SessionLocal()
    try:
        session = db.query(ScanSession).filter(ScanSession.id == session_id).first()
        if not session:
            return None

        progress = (session.processed_files / session.total_files * 100) if session.total_files > 0 else 0

        return {
            'session_id': session.id,
            'folder_path': session.folder_path,
            'status': session.status,
            'total_files': session.total_files,
            'processed_files': session.processed_files,
            'failed_files': session.failed_files,
            'progress_percent': round(progress, 2),
            'last_processed_file': session.last_processed_file,
            'error_message': session.error_message,
            'started_at': session.started_at,
            'completed_at': session.completed_at
        }
    finally:
        db.close()
