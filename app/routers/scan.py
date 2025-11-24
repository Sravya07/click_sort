import os
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, ScanSession
from app.models import ScanRequest, ScanStatusResponse
from app.services.scanner import scan_folder, get_scan_status, count_files

router = APIRouter(prefix="/scan", tags=["Scan"])

# Store for tracking background scan tasks
_active_scans = {}


def background_scan(folder_path: str, include_subfolders: bool):
    """Background task to scan folder."""
    try:
        result = scan_folder(folder_path, include_subfolders)
        _active_scans[folder_path] = result
    except Exception as e:
        _active_scans[folder_path] = {'error': str(e)}


@router.post("")
async def start_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start scanning a folder for media files.

    This endpoint initiates a background scan of the specified folder.
    The scan extracts:
    - EXIF metadata (date taken, camera info)
    - Perceptual hashes for duplicate detection
    - File hashes for exact match detection

    **Features:**
    - **Resume capability**: If a scan is interrupted, calling this endpoint
      again will resume from where it left off
    - **Incremental scanning**: Only processes new or modified files
    - **Background processing**: Large folders are scanned in the background

    **Supported formats:** JPG, JPEG, PNG, GIF, BMP, TIFF, WebP, HEIC, HEIF

    Returns session ID to track progress via `/scan/status/{session_id}`.
    """
    folder_path = request.folder_path

    if not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Folder not found: {folder_path}"
        )

    # Check for existing in-progress or interrupted scan
    existing = db.query(ScanSession).filter(
        ScanSession.folder_path == folder_path,
        ScanSession.status.in_(["in_progress", "interrupted"])
    ).first()

    if existing:
        if request.force_restart:
            # Cancel existing session and start fresh
            existing.status = "cancelled"
            existing.error_message = "Cancelled to start a fresh scan"
            db.commit()
        else:
            if existing.status == "interrupted":
                # Resume interrupted scan
                existing.status = "in_progress"
                existing.error_message = None
                db.commit()

            return {
                'message': 'Resuming existing scan session',
                'session_id': existing.id,
                'status': 'in_progress',
                'processed_files': existing.processed_files,
                'total_files': existing.total_files
            }

    # Count files for progress tracking
    total_files = count_files(folder_path, request.include_subfolders)

    if total_files == 0:
        return {
            'message': 'No media files found in folder',
            'session_id': None,
            'status': 'completed',
            'total_files': 0
        }

    # For small folders, scan synchronously
    if total_files <= 100:
        result = scan_folder(folder_path, request.include_subfolders)
        return {
            'message': 'Scan completed',
            'session_id': result['session_id'],
            'status': 'completed',
            **result
        }

    # For large folders, scan in background
    background_tasks.add_task(background_scan, folder_path, request.include_subfolders)

    # Create initial session record
    session = ScanSession(
        folder_path=folder_path,
        status="in_progress",
        total_files=total_files,
        processed_files=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        'message': f'Scan started for {total_files} files',
        'session_id': session.id,
        'status': 'in_progress',
        'total_files': total_files
    }


@router.get("/status/{session_id}", response_model=ScanStatusResponse)
async def get_scan_progress(
    session_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the status of a scan session.

    Returns progress information including:
    - Total and processed file counts
    - Percentage complete
    - Any error messages
    - Last processed file
    """
    status = get_scan_status(session_id)

    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Scan session {session_id} not found"
        )

    return ScanStatusResponse(**status)


@router.get("/sessions")
async def list_scan_sessions(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List recent scan sessions."""
    query = db.query(ScanSession)

    if status:
        query = query.filter(ScanSession.status == status)

    sessions = query.order_by(ScanSession.started_at.desc()).limit(limit).all()

    return {
        'sessions': [{
            'session_id': s.id,
            'folder_path': s.folder_path,
            'status': s.status,
            'total_files': s.total_files,
            'processed_files': s.processed_files,
            'progress_percent': round(s.processed_files / s.total_files * 100, 2) if s.total_files > 0 else 0,
            'started_at': s.started_at,
            'completed_at': s.completed_at
        } for s in sessions]
    }


@router.delete("/sessions/{session_id}")
async def cancel_scan(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Cancel an in-progress or interrupted scan session."""
    session = db.query(ScanSession).filter(ScanSession.id == session_id).first()

    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Scan session {session_id} not found"
        )

    if session.status not in ("in_progress", "interrupted"):
        return {
            'message': f'Session is already {session.status}',
            'session_id': session_id
        }

    session.status = "cancelled"
    session.error_message = "Scan was cancelled by user"
    db.commit()

    return {
        'message': 'Scan session cancelled',
        'session_id': session_id,
        'processed_files': session.processed_files
    }
