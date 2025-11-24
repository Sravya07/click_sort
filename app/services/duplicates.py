import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

import imagehash
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import MediaFile, DuplicateGroup, SessionLocal


def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate hamming distance between two perceptual hashes."""
    if not hash1 or not hash2:
        return 64  # Maximum distance for 64-bit hash
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2
    except Exception:
        return 64


def find_duplicate_groups(db: Session, folder_path: Optional[str] = None,
                          threshold: int = 10) -> List[Dict]:
    """
    Find groups of potentially duplicate images based on perceptual hash similarity.

    Args:
        db: Database session
        folder_path: Optional folder to limit search to
        threshold: Maximum hamming distance to consider as duplicate (default 10)
                   Lower = more strict, Higher = more permissive

    Returns:
        List of duplicate groups with file information
    """
    # Query files with perceptual hashes
    query = db.query(MediaFile).filter(
        MediaFile.phash.isnot(None),
        MediaFile.is_deleted == False
    )

    if folder_path:
        query = query.filter(MediaFile.folder_path.startswith(folder_path))

    files = query.all()

    if not files:
        return []

    # Group by similar hashes
    processed = set()
    groups = []
    group_id = 0

    for i, file1 in enumerate(files):
        if file1.id in processed:
            continue

        similar_files = [file1]
        processed.add(file1.id)

        for file2 in files[i + 1:]:
            if file2.id in processed:
                continue

            # Compare perceptual hashes
            distance = hamming_distance(file1.phash, file2.phash)

            if distance <= threshold:
                similar_files.append(file2)
                processed.add(file2.id)

        # Only create groups with 2+ files
        if len(similar_files) > 1:
            group_id += 1

            # Calculate average similarity within group
            total_distance = 0
            comparisons = 0
            for j, f1 in enumerate(similar_files):
                for f2 in similar_files[j + 1:]:
                    total_distance += hamming_distance(f1.phash, f2.phash)
                    comparisons += 1

            avg_distance = total_distance / comparisons if comparisons > 0 else 0
            similarity_score = max(0, 100 - (avg_distance / 64 * 100))

            # Create or update duplicate group in DB
            existing_group = db.query(DuplicateGroup).filter(
                DuplicateGroup.group_hash == file1.phash
            ).first()

            if not existing_group:
                dup_group = DuplicateGroup(
                    group_hash=file1.phash,
                    file_count=len(similar_files),
                    status="pending"
                )
                db.add(dup_group)
                db.commit()
                db.refresh(dup_group)
                db_group_id = dup_group.id
            else:
                existing_group.file_count = len(similar_files)
                existing_group.updated_at = datetime.utcnow()
                db.commit()
                db_group_id = existing_group.id

            # Update files with group ID
            for f in similar_files:
                f.duplicate_group_id = db_group_id
            db.commit()

            groups.append({
                'group_id': db_group_id,
                'files': [{
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
                } for f in similar_files],
                'similarity_score': round(similarity_score, 2),
                'status': 'pending'
            })

    return groups


def get_duplicate_groups(db: Session, folder_path: Optional[str] = None,
                         status: Optional[str] = None) -> List[Dict]:
    """Get existing duplicate groups from database."""
    query = db.query(DuplicateGroup)

    if status:
        query = query.filter(DuplicateGroup.status == status)

    groups = query.all()
    result = []

    for group in groups:
        files_query = db.query(MediaFile).filter(
            MediaFile.duplicate_group_id == group.id,
            MediaFile.is_deleted == False
        )

        if folder_path:
            files_query = files_query.filter(MediaFile.folder_path.startswith(folder_path))

        files = files_query.all()

        if len(files) < 2:
            continue

        # Calculate similarity score
        total_distance = 0
        comparisons = 0
        for j, f1 in enumerate(files):
            for f2 in files[j + 1:]:
                total_distance += hamming_distance(f1.phash, f2.phash)
                comparisons += 1

        avg_distance = total_distance / comparisons if comparisons > 0 else 0
        similarity_score = max(0, 100 - (avg_distance / 64 * 100))

        result.append({
            'group_id': group.id,
            'files': [{
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
            } for f in files],
            'similarity_score': round(similarity_score, 2),
            'status': group.status
        })

    return result


def apply_duplicate_action(db: Session, action: str, file_ids: List[int],
                           keep_file_id: Optional[int] = None,
                           favorites_folder: Optional[str] = None) -> Dict:
    """
    Apply an action to duplicate files.

    Actions:
        - keep: Mark files as reviewed, no changes
        - delete: Move files to trash (system trash or .trash folder)
        - favorite: Move files to favorites folder
        - decide_later: Skip for now

    Returns:
        Result summary
    """
    files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()

    if not files:
        return {'success': False, 'message': 'No files found', 'affected': 0}

    affected = 0
    errors = []

    for file in files:
        try:
            if action == 'keep':
                # Just mark as reviewed
                affected += 1

            elif action == 'delete':
                # Skip the file we want to keep
                if keep_file_id and file.id == keep_file_id:
                    continue

                # Move to trash folder
                folder = os.path.dirname(file.file_path)
                trash_folder = os.path.join(folder, '.trash')
                os.makedirs(trash_folder, exist_ok=True)

                dest_path = os.path.join(trash_folder, file.filename)

                # Handle name collision
                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(file.filename)
                    dest_path = os.path.join(trash_folder, f"{base}_{file.id}{ext}")

                if os.path.exists(file.file_path):
                    shutil.move(file.file_path, dest_path)

                file.is_deleted = True
                file.file_path = dest_path
                affected += 1

            elif action == 'favorite':
                if not favorites_folder:
                    # Derive favorites folder from file location
                    parent_folder = os.path.dirname(file.folder_path)
                    if not parent_folder:
                        parent_folder = file.folder_path
                    favorites_folder = os.path.join(parent_folder, 'favorites')

                os.makedirs(favorites_folder, exist_ok=True)

                # Create symlink in favorites (keeps original in place)
                link_path = os.path.join(favorites_folder, file.filename)

                # Handle name collision
                if os.path.exists(link_path):
                    base, ext = os.path.splitext(file.filename)
                    link_path = os.path.join(favorites_folder, f"{base}_{file.id}{ext}")

                if os.path.exists(file.file_path) and not os.path.exists(link_path):
                    os.symlink(file.file_path, link_path)

                file.is_favorite = True
                affected += 1

            elif action == 'decide_later':
                # No file changes, just skip
                affected += 1

        except Exception as e:
            errors.append(f"Error processing {file.filename}: {str(e)}")

    # Update group status
    if files:
        group_ids = set(f.duplicate_group_id for f in files if f.duplicate_group_id)
        for gid in group_ids:
            group = db.query(DuplicateGroup).filter(DuplicateGroup.id == gid).first()
            if group:
                if action == 'decide_later':
                    group.status = 'pending'
                else:
                    group.status = 'resolved'

    db.commit()

    return {
        'success': len(errors) == 0,
        'message': 'Action applied successfully' if not errors else f'{len(errors)} errors occurred',
        'affected': affected,
        'errors': errors
    }
