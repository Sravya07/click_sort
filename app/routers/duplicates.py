from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DuplicatesResponse, DuplicateGroupResponse, MediaFileResponse,
    DuplicateActionRequest
)
from app.services.duplicates import (
    find_duplicate_groups, get_duplicate_groups, apply_duplicate_action
)

router = APIRouter(prefix="/duplicates", tags=["Duplicates"])


@router.get("", response_model=DuplicatesResponse)
async def get_duplicates(
    folder_path: Optional[str] = Query(None, description="Limit to specific folder"),
    threshold: int = Query(10, ge=1, le=30, description="Similarity threshold (lower = stricter)"),
    rescan: bool = Query(False, description="Force rescan for duplicates"),
    status: Optional[str] = Query(None, description="Filter by status: pending, reviewed, resolved"),
    db: Session = Depends(get_db)
):
    """
    Get groups of potentially duplicate images.

    Duplicates are detected using perceptual hashing which is robust to:
    - Cropping
    - Resizing
    - Minor color adjustments
    - Filters

    The **threshold** parameter controls sensitivity:
    - Lower values (5-10): Very similar images only
    - Higher values (15-20): More permissive, catches edited versions
    - Default (10): Good balance for most use cases

    Returns groups of similar images for review.
    """
    if rescan:
        groups = find_duplicate_groups(db, folder_path=folder_path, threshold=threshold)
    else:
        groups = get_duplicate_groups(db, folder_path=folder_path, status=status)

        # If no existing groups, run initial scan
        if not groups:
            groups = find_duplicate_groups(db, folder_path=folder_path, threshold=threshold)

    # Convert to response model
    group_responses = []
    for g in groups:
        group_responses.append(DuplicateGroupResponse(
            group_id=g['group_id'],
            files=[MediaFileResponse(**f) for f in g['files']],
            similarity_score=g['similarity_score'],
            status=g['status']
        ))

    return DuplicatesResponse(
        total_groups=len(group_responses),
        groups=group_responses
    )


@router.get("/{group_id}")
async def get_duplicate_group(
    group_id: int,
    db: Session = Depends(get_db)
):
    """Get details of a specific duplicate group."""
    from app.database import DuplicateGroup, MediaFile

    group = db.query(DuplicateGroup).filter(DuplicateGroup.id == group_id).first()

    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")

    files = db.query(MediaFile).filter(
        MediaFile.duplicate_group_id == group_id,
        MediaFile.is_deleted == False
    ).all()

    return {
        'group_id': group.id,
        'status': group.status,
        'file_count': len(files),
        'files': [{
            'id': f.id,
            'file_path': f.file_path,
            'filename': f.filename,
            'file_size': f.file_size,
            'date_taken': f.date_taken,
            'is_favorite': f.is_favorite
        } for f in files]
    }


@router.post("/{group_id}/action")
async def apply_action_to_group(
    group_id: int,
    request: DuplicateActionRequest,
    db: Session = Depends(get_db)
):
    """
    Apply an action to files in a duplicate group.

    **Actions:**
    - `keep`: Keep all selected files, mark group as reviewed
    - `delete`: Move selected files to trash (keeps files specified by keep_file_id)
    - `favorite`: Add selected files to favorites folder (creates symlinks)
    - `decide_later`: Skip this group for now

    **Example - Delete duplicates keeping one:**
    ```json
    {
        "action": "delete",
        "file_ids": [1, 2, 3],
        "keep_file_id": 1
    }
    ```
    This deletes files 2 and 3, keeping file 1.

    **Example - Add to favorites:**
    ```json
    {
        "action": "favorite",
        "file_ids": [1, 2]
    }
    ```
    """
    from app.database import DuplicateGroup

    group = db.query(DuplicateGroup).filter(DuplicateGroup.id == group_id).first()

    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")

    result = apply_duplicate_action(
        db,
        action=request.action.value,
        file_ids=request.file_ids,
        keep_file_id=request.keep_file_id
    )

    return result


@router.post("/scan")
async def scan_for_duplicates(
    folder_path: Optional[str] = Query(None, description="Folder to scan"),
    threshold: int = Query(10, ge=1, le=30, description="Similarity threshold"),
    db: Session = Depends(get_db)
):
    """
    Force a new scan for duplicate images.

    This will analyze all scanned images and group them by similarity.
    """
    groups = find_duplicate_groups(db, folder_path=folder_path, threshold=threshold)

    return {
        'message': f'Found {len(groups)} duplicate groups',
        'total_groups': len(groups),
        'groups': groups[:10]  # Return first 10 for preview
    }
