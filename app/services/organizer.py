import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import MediaFile, SessionLocal


MONTH_NAMES = {
    1: '01-January',
    2: '02-February',
    3: '03-March',
    4: '04-April',
    5: '05-May',
    6: '06-June',
    7: '07-July',
    8: '08-August',
    9: '09-September',
    10: '10-October',
    11: '11-November',
    12: '12-December'
}


def get_destination_path(base_folder: str, date_taken: datetime, filename: str) -> str:
    """Generate destination path based on date: YEAR/Month/filename."""
    year = str(date_taken.year)
    month = MONTH_NAMES.get(date_taken.month, f"{date_taken.month:02d}")

    dest_folder = os.path.join(base_folder, year, month)
    return os.path.join(dest_folder, filename)


def preview_organization(db: Session, folder_path: str) -> List[Dict]:
    """
    Preview how files would be organized without actually moving them.

    Returns list of source -> destination mappings.
    """
    files = db.query(MediaFile).filter(
        MediaFile.folder_path.startswith(folder_path),
        MediaFile.is_deleted == False,
        MediaFile.is_organized == False,
        MediaFile.date_taken.isnot(None)
    ).all()

    preview = []

    for file in files:
        dest_path = get_destination_path(folder_path, file.date_taken, file.filename)

        # Only include if destination is different from current
        if dest_path != file.file_path:
            preview.append({
                'source_path': file.file_path,
                'destination_path': dest_path,
                'date_taken': file.date_taken
            })

    return preview


def organize_by_date(db: Session, folder_path: str, dry_run: bool = False) -> Dict:
    """
    Organize all photos in folder by date into YEAR/Month structure.

    Args:
        db: Database session
        folder_path: Root folder containing photos
        dry_run: If True, only preview changes without moving files

    Returns:
        Summary of organization results
    """
    files = db.query(MediaFile).filter(
        MediaFile.folder_path.startswith(folder_path),
        MediaFile.is_deleted == False,
        MediaFile.is_organized == False
    ).all()

    if dry_run:
        preview_items = []
        for file in files:
            if file.date_taken:
                dest_path = get_destination_path(folder_path, file.date_taken, file.filename)
                if dest_path != file.file_path:
                    preview_items.append({
                        'source_path': file.file_path,
                        'destination_path': dest_path,
                        'date_taken': file.date_taken
                    })

        return {
            'success': True,
            'message': f'Dry run: {len(preview_items)} files would be moved',
            'files_moved': 0,
            'files_skipped': len(files) - len(preview_items),
            'preview': preview_items
        }

    moved = 0
    skipped = 0
    errors = []

    for file in files:
        try:
            if not file.date_taken:
                skipped += 1
                continue

            dest_path = get_destination_path(folder_path, file.date_taken, file.filename)

            # Skip if already in correct location
            if dest_path == file.file_path:
                file.is_organized = True
                skipped += 1
                continue

            # Create destination directory
            dest_folder = os.path.dirname(dest_path)
            os.makedirs(dest_folder, exist_ok=True)

            # Handle filename collision
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(file.filename)
                counter = 1
                while os.path.exists(dest_path):
                    new_filename = f"{base}_{counter}{ext}"
                    dest_path = os.path.join(dest_folder, new_filename)
                    counter += 1

            # Move the file
            if os.path.exists(file.file_path):
                shutil.move(file.file_path, dest_path)

                # Update database
                file.file_path = dest_path
                file.folder_path = dest_folder
                file.is_organized = True
                moved += 1

                # If file is a favorite, ensure symlink exists in favorites folder
                if file.is_favorite:
                    favorites_folder = os.path.join(folder_path, 'favorites')
                    os.makedirs(favorites_folder, exist_ok=True)
                    link_path = os.path.join(favorites_folder, file.filename)

                    # Update symlink to point to new location
                    if os.path.islink(link_path):
                        os.remove(link_path)
                    if not os.path.exists(link_path):
                        os.symlink(dest_path, link_path)

            else:
                errors.append(f"File not found: {file.file_path}")
                skipped += 1

        except Exception as e:
            errors.append(f"Error moving {file.filename}: {str(e)}")
            skipped += 1

    db.commit()

    return {
        'success': len(errors) == 0,
        'message': f'Organized {moved} files into date folders' if not errors else f'{len(errors)} errors occurred',
        'files_moved': moved,
        'files_skipped': skipped,
        'errors': errors if errors else None
    }


def query_by_date(db: Session, year: Optional[int] = None,
                  month: Optional[int] = None, day: Optional[int] = None,
                  folder_path: Optional[str] = None) -> List[Dict]:
    """
    Query media files by date.

    Supports:
        - Just year: All files from that year
        - Year + month: All files from that month
        - Year + month + day: All files from that specific date
    """
    query = db.query(MediaFile).filter(MediaFile.is_deleted == False)

    if folder_path:
        query = query.filter(MediaFile.folder_path.startswith(folder_path))

    if year:
        query = query.filter(MediaFile.year == year)
    if month:
        query = query.filter(MediaFile.month == month)
    if day:
        query = query.filter(MediaFile.day == day)

    # Order by date
    query = query.order_by(MediaFile.date_taken.desc())

    files = query.all()

    return [{
        'id': f.id,
        'file_path': f.file_path,
        'filename': f.filename,
        'file_size': f.file_size,
        'date_taken': f.date_taken,
        'year': f.year,
        'month': f.month,
        'day': f.day,
        'is_favorite': f.is_favorite,
        'scanned_at': f.scanned_at
    } for f in files]
