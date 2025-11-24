from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OrganizeRequest, OrganizeResponse, OrganizePreviewItem
from app.services.organizer import organize_by_date, preview_organization

router = APIRouter(prefix="/organize", tags=["Organize"])


@router.post("", response_model=OrganizeResponse)
async def organize_photos(
    request: OrganizeRequest,
    db: Session = Depends(get_db)
):
    """
    Organize photos by EXIF date into YEAR/Month folder structure.

    This endpoint moves photos from their current locations into a structured
    folder hierarchy based on when they were taken:

    ```
    folder_path/
    ├── 2023/
    │   ├── 01-January/
    │   │   ├── photo1.jpg
    │   │   └── photo2.jpg
    │   ├── 02-February/
    │   └── ...
    ├── 2024/
    │   └── ...
    └── favorites/  (symlinks to originals)
    ```

    **Features:**
    - Uses EXIF DateTimeOriginal when available
    - Falls back to file modification date if no EXIF
    - Handles filename collisions by appending counter
    - Preserves favorites as symlinks
    - Skips already-organized files

    **Dry Run:**
    Set `dry_run: true` to preview changes without moving files.
    """
    import os

    if not os.path.isdir(request.folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Folder not found: {request.folder_path}"
        )

    result = organize_by_date(db, request.folder_path, dry_run=request.dry_run)

    preview = None
    if result.get('preview'):
        preview = [OrganizePreviewItem(**p) for p in result['preview']]

    return OrganizeResponse(
        success=result['success'],
        message=result['message'],
        files_moved=result['files_moved'],
        files_skipped=result['files_skipped'],
        preview=preview
    )


@router.get("/preview")
async def preview_organize(
    folder_path: str = Query(..., description="Folder to organize"),
    db: Session = Depends(get_db)
):
    """
    Preview how files would be organized without moving them.

    Returns a list of source → destination path mappings.
    """
    import os

    if not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Folder not found: {folder_path}"
        )

    preview = preview_organization(db, folder_path)

    return {
        'folder_path': folder_path,
        'total_files': len(preview),
        'preview': preview
    }
